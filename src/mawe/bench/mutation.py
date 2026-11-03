"""Mutation testing the benchmark's own hidden tests.

Week 9.  "The hidden tests are thorough" is an assertion.  This turns it into a
number.

The method: take a reference solution that passes every hidden test, introduce
one small defect, and see whether any test notices.  A mutant that still passes
everything is a hole - some class of wrong program would be scored as a success
in Phase 4, and the headline "task success rate" would be measuring less than
it claims.

Two details keep the number honest:

**Only mutants that still parse are counted.**  A mutation that produces a
syntax error is killed by every test, which says nothing about the tests.  Each
candidate is compiled first - `compile()` for Python, `node --check` for
JavaScript - and discarded if it does not parse.

**A survivor is reported, not explained away.**  Some survivors are equivalent
mutants: the mutation changed the text without changing the behaviour any test
could observe, for instance altering a constant inside an error message that is
only ever written to stderr.  Those are a known limitation of mutation scoring
rather than a defect, so the score is reported with its survivors listed and
is not expected to be 100%.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .harness import score
from .solutions import SOURCES, files_for
from .tasks import TASKS, BenchTask

#: (name, pattern, replacement).  Each is a defect a careless implementation
#: would plausibly contain, not a random character edit: off-by-one bounds,
#: flipped comparisons, inverted conditions, swapped extremes.
OPERATORS: Tuple[Tuple[str, str, str], ...] = (
    ("<=  ->  <", r"<=", "<"),
    (">=  ->  >", r">=", ">"),
    ("<  ->  <=", r"(?<![<>=!])<(?![=<])", "<="),
    (">  ->  >=", r"(?<![<>=!-])>(?![=>])", ">="),
    ("==  ->  !=", r"(?<![!<>=])===?(?!=)", "!="),
    ("!=  ->  ==", r"!==?(?!=)", "=="),
    ("+ 1  ->  + 2", r"\+ 1\b", "+ 2"),
    ("- 1  ->  - 2", r"- 1\b", "- 2"),
    ("+= 1  ->  += 2", r"\+= 1\b", "+= 2"),
    ("and  ->  or", r"\band\b", "or"),
    ("or  ->  and", r"\bor\b", "and"),
    ("&&  ->  ||", r"&&", "||"),
    ("||  ->  &&", r"\|\|", "&&"),
    ("min  ->  max", r"\bmin\(", "max("),
    ("max  ->  min", r"\bmax\(", "min("),
    ("reversed dropped", r"\breversed\(", "iter("),
    ("sorted dropped", r"\bsorted\(", "list("),
    ("not dropped", r"\bnot \b", ""),
    ("0  ->  1", r"(?<![\w.])0(?![\w.])", "1"),
    ("1  ->  0", r"(?<![\w.])1(?![\w.])", "0"),
    ("2  ->  3", r"(?<![\w.])2(?![\w.])", "3"),
    ("break  ->  continue", r"\bbreak\b", "continue"),
    # Confusing two neighbouring library calls is as real a defect as an
    # off-by-one, and for a task whose solution is three straight-line
    # statements it is the *only* defect available: `word-count`'s reference
    # has no comparison, no loop and no literal to perturb, so without these
    # operators its tests went unmeasured.
    ("splitlines  ->  split", r"\bsplitlines\(", "split("),
    ("split  ->  splitlines", r"(?<!\.)\.split\(\)", ".splitlines()"),
    ("lower  ->  upper", r"\blower\(", "upper("),
    ("upper  ->  lower", r"\bupper\(", "lower("),
    ("abs  ->  int", r"\babs\(", "int("),
    ("startswith  ->  endswith", r"\bstartswith\(", "endswith("),
    ("toLowerCase  ->  toUpperCase", r"\btoLowerCase\(", "toUpperCase("),
    ("push  ->  unshift", r"\bpush\(", "unshift("),
    ("trim  ->  trimStart", r"\btrim\(\)", "trimStart()"),
    ("concat  ->  slice", r"\bconcat\(", "slice("),
)


@dataclass
class Mutant:
    task: BenchTask
    operator: str
    position: int
    source: str

    @property
    def label(self) -> str:
        return f"{self.task.slug}: {self.operator} @{self.position}"


@dataclass
class MutationResult:
    task: BenchTask
    killed: int = 0
    survived: List[Mutant] = field(default_factory=list)
    unparseable: int = 0

    @property
    def total(self) -> int:
        return self.killed + len(self.survived)

    @property
    def score(self) -> float:
        return self.killed / self.total if self.total else 0.0


def _parses(source: str, language: str) -> bool:
    if language == "python":
        try:
            compile(source, "<mutant>", "exec")
            return True
        except SyntaxError:
            return False

    # node --check is the only honest syntax gate for JavaScript, and it needs
    # the source on disk
    handle, path = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(source)
        done = subprocess.run(["node", "--check", path],
                              capture_output=True, timeout=20)
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)


def _strip_strings(source: str, language: str) -> List[Tuple[int, int]]:
    """Spans of string literals and comments, so mutations skip them.

    Changing a character inside an error message is not a defect a test could
    reasonably be expected to catch, and counting such mutants as survivors
    would understate the tests for no reason.
    """
    spans: List[Tuple[int, int]] = []
    pattern = (r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'|'
               r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|'
               r'#[^\n]*' if language == "python" else
               r'`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|'
               r'/\*(?:.|\n)*?\*/|//[^\n]*|'
               r'/(?:\\.|\[(?:\\.|[^\]\\])*\]|[^/\\\n])+/[gimsuy]*')
    for match in re.finditer(pattern, source):
        spans.append((match.start(), match.end()))
    return spans


def _inside(position: int, spans: Sequence[Tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def mutants_for(task: BenchTask, limit: Optional[int] = None) -> List[Mutant]:
    """Every single-edit mutant of a task's reference solution that parses.

    Deterministic: the operators run in a fixed order over fixed positions, so
    the same set comes out on every machine and the mutation score is
    reproducible.  `limit` spreads the cap evenly across operators rather than
    taking the first N, so a cap does not silently reduce the sample to
    whichever operator happens to match most often.
    """
    source = SOURCES[task.slug]
    skip = _strip_strings(source, task.language)

    grouped: List[List[Mutant]] = []
    for name, pattern, replacement in OPERATORS:
        found: List[Mutant] = []
        for match in re.finditer(pattern, source):
            if _inside(match.start(), skip):
                continue
            mutated = source[:match.start()] + replacement + source[match.end():]
            if mutated == source or not _parses(mutated, task.language):
                continue
            found.append(Mutant(task, name, match.start(), mutated))
        if found:
            grouped.append(found)

    if limit is None:
        return [m for group in grouped for m in group]

    # round-robin across operators until the cap is reached
    chosen: List[Mutant] = []
    index = 0
    while len(chosen) < limit and any(index < len(g) for g in grouped):
        for group in grouped:
            if index < len(group):
                chosen.append(group[index])
                if len(chosen) >= limit:
                    break
        index += 1
    return chosen


def run_task(task: BenchTask, limit: Optional[int] = 12,
             timeout_s: int = 10) -> MutationResult:
    result = MutationResult(task)
    for mutant in mutants_for(task, limit):
        outcome = score(files_for(task.slug, mutant.source), task,
                        timeout_s=timeout_s, stop_on_first_failure=True)
        if outcome.success:
            result.survived.append(mutant)
        else:
            result.killed += 1
    return result


def run_all(tasks: Sequence[BenchTask] = TASKS, limit: Optional[int] = 12,
            timeout_s: int = 10) -> List[MutationResult]:
    return [run_task(t, limit, timeout_s) for t in tasks]


def overall(results: Sequence[MutationResult]) -> Dict[str, float]:
    killed = sum(r.killed for r in results)
    total = sum(r.total for r in results)
    return {
        "mutants": float(total),
        "killed": float(killed),
        "survived": float(total - killed),
        "mutation_score": killed / total if total else 0.0,
    }
