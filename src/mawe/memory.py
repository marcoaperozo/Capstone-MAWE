"""Context construction and compression.

Week 7.  Each iteration adds a specification, a full set of source files and a
review to the conversation.  Replaying all of it every round is what makes
long multi-agent runs expensive and eventually impossible: the context grows
roughly linearly in iterations while the token budget does not move.

The strategy, from the proposal:

* the **latest** specification, source files and review stay in full, because
  that is what the Developer is actually editing;
* everything older is compressed into a **progress log** - one line per past
  iteration recording what was produced and what the Reviewer said about it;
* the raw messages are still written to the database, so nothing is lost for
  the Phase 4 analysis, only dropped from the prompt.

Compression is **structured, not generative**.  A model-written summary costs
tokens, is non-deterministic and can silently drop the one detail that
mattered.  The fields a later iteration actually needs - which version was
tried, what its hash was, which criteria failed - are known in advance, so
they are recorded exactly and cheaply.  `LLMSummariser` is available for the
Phase 4 comparison between the two approaches.

Both the compressed and the uncompressed context are produced by rendering
them, so the reduction figure reported for RQ5 is a measurement rather than an
estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from .llm.base import LLMProvider, estimate_tokens


@dataclass
class IterationRecord:
    """What happened in one review/fix cycle."""

    iteration: int
    code_hash: str = ""
    files: List[str] = field(default_factory=list)
    total_lines: int = 0
    verdict: str = ""
    severity: Optional[str] = None
    issues: List[str] = field(default_factory=list)
    tests_passed: int = 0
    tests_failed: int = 0
    #: the actual file bodies, kept so the uncompressed baseline can be
    #: measured rather than estimated, and for the Phase 4 ablation
    file_bodies: List[Dict[str, str]] = field(default_factory=list, repr=False)

    def one_line(self, max_issues: int = 2) -> str:
        parts = [f"iteration {self.iteration}:",
                 f"{len(self.files)} file(s), {self.total_lines} lines",
                 f"[{self.code_hash[:10]}]"]
        if self.verdict:
            tail = f"-> {self.verdict}"
            if self.severity:
                tail += f"/{self.severity}"
            parts.append(tail)
        if self.tests_passed or self.tests_failed:
            parts.append(f"({self.tests_passed} checks passed, "
                         f"{self.tests_failed} failed)")
        line = " ".join(parts)
        if self.issues:
            shown = self.issues[:max_issues]
            bullets = "; ".join(i.splitlines()[0][:110] for i in shown)
            extra = (f" (+{len(self.issues) - len(shown)} more)"
                     if len(self.issues) > len(shown) else "")
            line += "\n    issues: " + bullets + extra
        return line


class Summariser(Protocol):
    name: str

    def summarise(self, records: Sequence[IterationRecord]) -> str:
        ...


class StructuredSummariser:
    """Deterministic, free, and lossless for the fields that matter."""

    name = "structured"

    def summarise(self, records: Sequence[IterationRecord]) -> str:
        if not records:
            return ""
        header = (f"PROGRESS LOG - iterations {records[0].iteration} to "
                  f"{records[-1].iteration}, compressed:")
        lines = [header] + [f"  {r.one_line()}" for r in records]
        rejected = [r for r in records if r.verdict == "reject"]
        if rejected:
            recurring = _recurring_issues(rejected)
            if recurring:
                lines.append("  recurring, still unresolved: "
                             + "; ".join(recurring[:3]))
        return "\n".join(lines)


class LLMSummariser:
    """Model-written prose summary. For the Phase 4 comparison."""

    name = "llm"

    SYSTEM = ("You compress the history of an automated software build. "
              "Report only what a developer needs in order to avoid repeating "
              "past mistakes. Be factual and stay under 120 words.")

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.tokens_spent = 0

    def summarise(self, records: Sequence[IterationRecord]) -> str:
        if not records:
            return ""
        raw = StructuredSummariser().summarise(records)
        response = self.provider.complete(self.SYSTEM, raw, temperature=0.0)
        self.tokens_spent += response.total_tokens
        return response.text.strip()


def _recurring_issues(records: Sequence[IterationRecord]) -> List[str]:
    counts: Dict[str, int] = {}
    for record in records:
        for issue in record.issues:
            key = issue.splitlines()[0][:110].strip().lower()
            counts[key] = counts.get(key, 0) + 1
    return [k for k, v in sorted(counts.items(), key=lambda kv: -kv[1]) if v > 1]


# --------------------------------------------------------------------------

@dataclass
class ContextStats:
    """What compression bought on one prompt build."""

    tokens_uncompressed: int
    tokens_compressed: int
    iterations_total: int
    iterations_kept_in_full: int
    iterations_compressed: int

    @property
    def tokens_saved(self) -> int:
        return max(0, self.tokens_uncompressed - self.tokens_compressed)

    @property
    def reduction(self) -> float:
        """Fraction of context tokens removed, 0.0 to 1.0."""
        if self.tokens_uncompressed <= 0:
            return 0.0
        return self.tokens_saved / self.tokens_uncompressed


class MemoryManager:
    """Builds the history section of a prompt within a token budget."""

    def __init__(self, token_budget: int = 12_000,
                 keep_full: int = 1,
                 summariser: Optional[Summariser] = None,
                 enabled: bool = True):
        self.token_budget = token_budget
        self.keep_full = max(0, keep_full)
        self.summariser = summariser or StructuredSummariser()
        self.enabled = enabled
        self.last_stats: Optional[ContextStats] = None

    # ------------------------------------------------------------------
    @staticmethod
    def record_from_state(state: Dict[str, Any]) -> IterationRecord:
        files = state.get("files") or []
        return IterationRecord(
            iteration=int(state.get("iteration", 0)),
            code_hash=state.get("code_hash", "") or "",
            files=[f["path"] for f in files],
            total_lines=sum(len(f["content"].splitlines()) for f in files),
            file_bodies=[dict(f) for f in files],
            verdict=state.get("verdict", "") or "",
            severity=state.get("severity"),
            issues=list(state.get("issues") or []),
            tests_passed=int(state.get("tests_passed") or 0),
            tests_failed=int(state.get("tests_failed") or 0),
        )

    @staticmethod
    def render_files(files: Sequence[Dict[str, str]]) -> str:
        if not files:
            return "(none)"
        return "\n\n".join(f"--- {f['path']} ---\n{f['content']}"
                           for f in files)

    # ------------------------------------------------------------------
    def _render_uncompressed(self, history: Sequence[IterationRecord],
                             rendered_latest: str,
                             latest_files: Sequence[Dict[str, str]]) -> str:
        """Every past version in full: what a naive implementation sends."""
        parts: List[str] = []
        for record in (history[:-1] if history else []):
            if record.file_bodies:
                parts.append(f"--- iteration {record.iteration} ---\n"
                             + self.render_files(record.file_bodies))
            if record.issues:
                bullets = "\n".join(f"  - {i}" for i in record.issues)
                parts.append(f"review of iteration {record.iteration} "
                             f"({record.verdict}/{record.severity}):\n"
                             + bullets)
        if latest_files:
            parts.append("YOUR PREVIOUS FILES:\n" + rendered_latest)
        return "\n\n".join(parts)

    def _compose(self, older: Sequence[IterationRecord], rendered_latest: str,
                 latest_files: Sequence[Dict[str, str]], dropped: int) -> str:
        parts: List[str] = []
        summary = self.summariser.summarise(older)
        if dropped:
            prefix = (f"[{dropped} earlier iteration(s) omitted to stay within "
                      f"the {self.token_budget}-token context budget]")
            parts.append(prefix + "\n" + summary if summary else prefix)
        elif summary:
            parts.append(summary)
        if latest_files:
            parts.append("YOUR PREVIOUS FILES (latest version only):\n"
                         + rendered_latest)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    def build_history(self, history: Sequence[IterationRecord],
                      latest_files: Sequence[Dict[str, str]]
                      ) -> Tuple[str, ContextStats]:
        """Return the history section of a prompt, plus what it cost.

        `history` is every completed iteration, oldest first.

        With compression on, the last `keep_full` iterations are represented by
        their actual source and everything older collapses into the progress
        log.  With it off - the Phase 4 ablation, condition C' - every past
        version is replayed in full.
        """
        rendered_latest = self.render_files(latest_files)
        uncompressed_section = self._render_uncompressed(
            history, rendered_latest, latest_files)
        uncompressed = estimate_tokens(uncompressed_section)

        if not self.enabled:
            stats = ContextStats(uncompressed, uncompressed, len(history),
                                 len(history), 0)
            self.last_stats = stats
            return uncompressed_section, stats

        if len(history) <= self.keep_full:
            section = ("YOUR PREVIOUS FILES:\n" + rendered_latest
                       if latest_files else "")
            stats = ContextStats(uncompressed, estimate_tokens(section),
                                 len(history),
                                 min(len(history), self.keep_full), 0)
            self.last_stats = stats
            return section, stats

        older = list(history[:-self.keep_full]) if self.keep_full \
            else list(history)
        section = self._compose(older, rendered_latest, latest_files, 0)

        # if even the compressed section is over budget, drop the oldest
        # entries from the log until it fits
        while older and estimate_tokens(section) > self.token_budget:
            older.pop(0)
            dropped = len(history) - self.keep_full - len(older)
            section = self._compose(older, rendered_latest, latest_files,
                                    dropped)

        stats = ContextStats(
            tokens_uncompressed=uncompressed,
            tokens_compressed=estimate_tokens(section),
            iterations_total=len(history),
            iterations_kept_in_full=self.keep_full,
            iterations_compressed=len(history) - self.keep_full,
        )
        self.last_stats = stats
        return section, stats

    # ------------------------------------------------------------------
    @classmethod
    def from_settings(cls, settings, enabled: Optional[bool] = None
                      ) -> "MemoryManager":
        if enabled is None:
            enabled = getattr(settings, "summarisation_enabled", True)
        return cls(
            token_budget=getattr(settings, "context_token_budget", 12_000),
            keep_full=getattr(settings, "keep_iterations_in_full", 1),
            enabled=enabled,
        )
