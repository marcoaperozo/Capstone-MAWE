"""A provider that can answer any benchmark task, with controllable quality.

Week 10.  Not a model, and not pretending to be one: a fixture that lets the
*comparison machinery* be tested before a real API key is ever spent.

The problem it solves is specific.  Phase 4 will run four conditions over 20
tasks and report which scored better.  If any part of that pipeline is wrong -
the prompt never reaches the condition, the files never reach the harness, the
score never reaches the table - the sweep reports zeros for everything, which
looks exactly like "the models all did badly".  A fixture with a known answer
is the only way to tell those two apart.

So this provider returns, for whichever benchmark task it is being asked
about, one of:

``perfect``
    the reference solution.  Every condition should score 20/20; anything less
    is a bug in the pipeline, not a finding.
``flawed``
    a mutant of the reference - a single real defect, verified against the
    hidden tests so that it is one they actually catch.  Scores must drop.
``improving``
    the mutant first, the reference on any later attempt.  Conditions that
    iterate (B, C, C') should recover; condition A, which has one shot, should
    not.  This is what proves the comparison can see a difference at all.
``slow``
    a *different* defect on each of the first three attempts, then the
    reference.  Needed because the summarisation ablation only does anything
    once there are at least two completed iterations to compress: a run that
    finishes at iteration 2 has no older history, so C and C' send byte-
    identical prompts and the ablation looks like it has no effect.  Each
    defect differs from the last so that the engine's no-progress exit does
    not fire for the wrong reason.

It never reveals a hidden test.  The specification it writes for the Product
Manager role is derived from the task prompt only, which is the same text a
real model would see.  Leaking a hidden test here would quietly invalidate
every number the experiment produces, so the generated spec carries no
executable checks and the reviewer arm judges on the quality setting alone.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from ..llm.base import LLMResponse, estimate_tokens
from .mutation import mutants_for
from .solutions import SOURCES, files_for
from .tasks import TASKS, BenchTask, get

#: Stamped into the generated specification so that downstream roles - the
#: Developer and Reviewer, which see the spec rather than the original
#: request - can still be told which task they are working on.
MARKER = "MAWE-TASK:"

QUALITIES = ("perfect", "flawed", "improving", "slow")

#: how many defective attempts `slow` makes before getting it right
SLOW_ATTEMPTS = 3

_MUTANT_CACHE: Dict[str, Optional[str]] = {}
_VARIANT_CACHE: Dict[str, List[str]] = {}


#: how many mutants to try before giving up on finding a detectable one
CANDIDATE_MUTANTS = 12


def _is_detectably_broken(task: BenchTask, source: str) -> bool:
    from .harness import score                      # local: avoids a cycle

    return not score(files_for(task.slug, source), task,
                     stop_on_first_failure=True).success


def defective_source(task: BenchTask) -> Optional[str]:
    """One defective version of the reference that the hidden tests catch.

    Taking the first mutant is not enough, and the difference showed up as a
    wrong result rather than an error: roughly one task in ten has an
    equivalent first mutant - a textual change with no observable effect - so
    the "flawed" fixture handed condition A code that passed everything, and
    the sweep reported A succeeding on tasks it was supposed to fail.  Each
    candidate is therefore scored, and only a mutant the tests actually kill
    is used.
    """
    if task.slug in _MUTANT_CACHE:
        return _MUTANT_CACHE[task.slug]

    chosen = None
    for mutant in mutants_for(task, limit=CANDIDATE_MUTANTS):
        if _is_detectably_broken(task, mutant.source):
            chosen = mutant.source
            break
    _MUTANT_CACHE[task.slug] = chosen
    return chosen


def defective_variants(task: BenchTask,
                       count: int = SLOW_ATTEMPTS) -> List[str]:
    """`count` distinct defective versions of the reference.

    Distinctness matters: the engine exits a run whose code stops changing,
    so a fixture that handed back the same defect twice would terminate on
    `no_progress` and the run would be too short to exercise what is being
    measured.  Where a task has fewer mutants than requested, the extras are
    padded with a trailing comment - still defective, still different.
    """
    if task.slug in _VARIANT_CACHE:
        return _VARIANT_CACHE[task.slug]

    sources = []
    for mutant in mutants_for(task, limit=CANDIDATE_MUTANTS):
        if len(sources) >= count:
            break
        if _is_detectably_broken(task, mutant.source):
            sources.append(mutant.source)
    if sources:
        comment = "#" if task.language == "python" else "//"
        index = 0
        while len(sources) < count:
            sources.append(sources[index % len(sources)]
                           + f"{comment} revision {len(sources)}\n")
            index += 1
    _VARIANT_CACHE[task.slug] = sources[:count]
    return _VARIANT_CACHE[task.slug]


def identify(text: str) -> Optional[BenchTask]:
    """Work out which task a prompt is about.

    Baselines are handed the task prompt verbatim, so a prefix match finds it.
    The engine's Developer and Reviewer see the specification instead, which is
    why the spec carries an explicit marker.
    """
    stamped = re.search(MARKER + r"([a-z0-9-]+)", text)
    if stamped:
        try:
            return get(stamped.group(1))
        except KeyError:
            return None
    for task in TASKS:
        if task.prompt[:80] in text:
            return task
    return None


def specification_for(task: BenchTask) -> Dict[str, object]:
    """A plausible specification built only from what the prompt says.

    Criteria come from the prompt's own sentences.  No `checks` key: inventing
    executable checks here would either leak a hidden test or test something
    the prompt never promised, and both would corrupt the comparison.
    """
    sentences = [s.strip().replace("\n", " ")
                 for s in re.split(r"(?<=[.;])\s+", task.prompt)
                 if len(s.strip()) > 25]
    criteria = [s[:160] for s in sentences[:6]] or [
        f"the program satisfies the request: {task.title}"]
    return {
        "summary": f"{MARKER}{task.slug} - {task.title}",
        "language": task.language,
        "files": [task.entry_path],
        "features": [task.title],
        "constraints": ["a single runnable program at " + task.entry_path],
        "acceptance_criteria": criteria,
    }


class OracleProvider:
    """Answers every role for whichever benchmark task is being asked about.

    Usage totals are reported the same way every provider reports them, so the
    token and cost columns of a sweep driven by this fixture are real
    measurements of the *pipeline's* overhead even though they say nothing
    about a model.
    """

    def __init__(self, quality: str = "perfect", model: str = "oracle-1"):
        if quality not in QUALITIES:
            raise ValueError(f"quality must be one of {QUALITIES}, "
                             f"got {quality!r}")
        self.name = "oracle"
        self.model = model
        self.quality = quality
        self.calls: List[str] = []
        #: how many code answers have been given per task, so `improving`
        #: knows whether this is a first attempt or a retry
        self._attempts: Dict[str, int] = {}
        #: what the last code answer for each task actually was, so the
        #: reviewer and self-critic arms can be right about it
        self._delivered: Dict[str, str] = {}

    # ------------------------------------------------------------------
    def complete(self, system: str, user: str, *, temperature: float = 0.2,
                 max_tokens: int = 4096) -> LLMResponse:
        role = self._role_of(system)
        self.calls.append(role)
        task = identify(user)
        text = self._answer(role, task, user)
        return LLMResponse(
            text=text,
            prompt_tokens=estimate_tokens(system) + estimate_tokens(user),
            completion_tokens=estimate_tokens(text),
            model=self.model,
            meta={"role": role, "task": task.slug if task else None,
                  "quality": self.quality},
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _role_of(system: str) -> str:
        head = system[:220].lower()
        for phrase, role in (
            ("you are the product manager", "product_manager"),
            ("you are the developer", "developer"),
            ("you are the code reviewer", "reviewer"),
            ("you are an expert programmer working alone", "solo"),
            ("you are reviewing your own code", "self_critic"),
        ):
            if phrase in head:
                return role
        if "you compress the history" in head:
            return "summariser"
        return "unknown"

    def _source_for(self, task: BenchTask) -> str:
        reference = SOURCES[task.slug]
        attempt = self._attempts.get(task.slug, 0)
        self._attempts[task.slug] = attempt + 1

        def deliver(source: str) -> str:
            self._delivered[task.slug] = (
                "reference" if source == reference else "defective")
            return source

        if self.quality == "perfect":
            return deliver(reference)

        if self.quality == "slow":
            variants = defective_variants(task)
            if variants and attempt < len(variants):
                return deliver(variants[attempt])
            return deliver(reference)

        broken = defective_source(task)
        if broken is None:          # nothing mutable: fall back to correct
            return deliver(reference)
        if self.quality == "flawed":
            return deliver(broken)
        return deliver(broken if attempt == 0 else reference)   # improving

    def _answer(self, role: str, task: Optional[BenchTask], user: str) -> str:
        if task is None:
            # Not a benchmark prompt.  Say so in the contract's own shape
            # rather than raising, so a stray call cannot abort a sweep.
            if role in ("solo", "developer"):
                return json.dumps({"files": [{
                    "path": "src/main.py", "language": "python",
                    "content": "print('no benchmark task identified')\n"}]})
            if role == "product_manager":
                return json.dumps(specification_for(TASKS[0]))
            if role == "reviewer":
                return json.dumps({"verdict": "reject", "severity": "major",
                                   "issues": ["the task could not be "
                                              "identified"],
                                   "tests_passed": 0, "tests_failed": 1})
            if role == "self_critic":
                return json.dumps({"done": False,
                                   "issues": ["the task could not be "
                                              "identified"]})
            return "{}"

        if role == "product_manager":
            return json.dumps(specification_for(task))

        if role in ("solo", "developer"):
            return json.dumps({"files": [{
                "path": task.entry_path,
                "language": task.language,
                "content": self._source_for(task)}]})

        if role == "reviewer":
            # The oracle knows whether it handed over the reference, so it can
            # play a reviewer that is right - which is what isolates the
            # pipeline from reviewer quality.
            if self._delivered_reference(task, user):
                return json.dumps({"verdict": "approve", "severity": "minor",
                                   "issues": [], "tests_passed": 0,
                                   "tests_failed": 0})
            return json.dumps({
                "verdict": "reject", "severity": "major",
                "issues": [self._complaint(task)],
                "tests_passed": 0, "tests_failed": 1})

        if role == "self_critic":
            if self._delivered_reference(task, user):
                return json.dumps({"done": True, "issues": []})
            return json.dumps({"done": False,
                               "issues": [self._complaint(task)]})

        if role == "summariser":
            return "progress so far: one or more attempts have been made."

        return "{}"

    def _complaint(self, task: BenchTask) -> str:
        """A rejection that names a different defect each time.

        The engine stops a run whose reviewer keeps refiling the same
        complaint, which is correct behaviour and exactly wrong for a fixture
        meant to produce a long run.  Numbering the complaint keeps the
        fingerprints distinct.
        """
        attempt = self._attempts.get(task.slug, 0)
        return (f"attempt {attempt}: the program still mishandles one of the "
                f"cases the request describes")

    def _delivered_reference(self, task: BenchTask, user: str) -> bool:
        """Was the last code handed over for this task the reference?

        An earlier version of this inspected the prompt for a slice of the
        reference, which was wrong in a way worth recording: a single-edit
        mutant leaves the end of the file untouched, so the probe matched and
        the oracle approved defective code at the first iteration.  The
        fixture therefore could not demonstrate recovery, which was the one
        thing it existed to demonstrate.

        The oracle knows what it produced, so it records it instead of trying
        to recognise it.
        """
        return self._delivered.get(task.slug) == "reference"
