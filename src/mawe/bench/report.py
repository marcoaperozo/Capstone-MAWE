"""Turning a sweep into the tables and tests Phase 4 reports.

Week 11.  Separate from `experiment.py` on purpose: collection is expensive
and analysis is not, so a sweep is saved once and re-analysed as often as the
write-up needs.

The decision that shapes everything here is **the unit of analysis**.  A sweep
produces one row per (condition, task, repetition), so with 20 tasks and 3
repetitions there are 60 rows per condition - and it is tempting to run the
paired tests over all 60.  That would be wrong, and wrong in the direction
that manufactures significance: three runs of the same task are not three
independent observations, so treating them as such inflates n threefold and
shrinks every p-value and confidence interval accordingly.

So repetitions are averaged within a task first, and every test runs over the
20 tasks.  Repetitions do useful work - they measure how stable a condition is
on a task, which is reported separately as `instability` - but they are not
sample size.

For the headline binary metric a task counts as **solved** by a condition when
it succeeded in more than half of its repetitions.  That rule is stated
because it matters: with 3 repetitions it means "at least 2 of 3", and a
condition that solves a task once out of three does not get credit for it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .experiment import CONDITION_NAMES, RunRow
from .stats import (
    Estimate,
    TestResult,
    cliffs_delta,
    holm_bonferroni,
    interpret_delta,
    mcnemar_exact,
    mean,
    mean_ci,
    proportion_ci,
    wilcoxon_signed_rank,
)


# =========================================================== per-task folding
@dataclass
class TaskSummary:
    """One condition's behaviour on one task, across all repetitions."""

    condition: str
    task: str
    difficulty: str
    language: str
    repetitions: int
    solved: bool                  # majority of repetitions succeeded
    success_fraction: float       # how many repetitions succeeded
    pass_rate: float              # mean fraction of hidden tests passed
    tokens: float                 # mean total tokens
    iterations: float
    latency_s: float
    cost_usd: float
    errors: int
    termination_reasons: Tuple[str, ...]

    @property
    def instability(self) -> bool:
        """Did the repetitions disagree about whether this task was solved?"""
        return 0.0 < self.success_fraction < 1.0


def fold_repetitions(rows: Sequence[RunRow]) -> List[TaskSummary]:
    """Collapse repetitions so that each (condition, task) appears once."""
    grouped: Dict[Tuple[str, str], List[RunRow]] = defaultdict(list)
    for row in rows:
        if row.skipped:
            continue
        grouped[(row.condition, row.task)].append(row)

    summaries: List[TaskSummary] = []
    for (condition, task), group in sorted(grouped.items()):
        successes = sum(1 for r in group if r.success)
        fraction = successes / len(group)
        summaries.append(TaskSummary(
            condition=condition,
            task=task,
            difficulty=group[0].difficulty,
            language=group[0].language,
            repetitions=len(group),
            solved=fraction > 0.5,
            success_fraction=fraction,
            pass_rate=mean([r.pass_rate for r in group]),
            tokens=mean([float(r.total_tokens) for r in group]),
            iterations=mean([float(r.iterations) for r in group]),
            latency_s=mean([r.latency_s for r in group]),
            cost_usd=mean([r.cost_usd for r in group]),
            errors=sum(1 for r in group if r.error),
            termination_reasons=tuple(r.termination_reason for r in group),
        ))
    return summaries


# =========================================================== per condition
@dataclass
class ConditionReport:
    condition: str
    tasks: int
    solved: int
    success_rate: Estimate
    pass_rate: Estimate
    tokens: Estimate
    iterations: Estimate
    latency_s: Estimate
    total_cost: float
    cost_per_success: Optional[float]
    unstable_tasks: List[str] = field(default_factory=list)
    errors: int = 0
    termination_counts: Dict[str, int] = field(default_factory=dict)
    by_difficulty: Dict[str, Tuple[int, int]] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return CONDITION_NAMES.get(self.condition, self.condition)


def summarise_condition(summaries: Sequence[TaskSummary]) -> ConditionReport:
    condition = summaries[0].condition
    solved = sum(1 for s in summaries if s.solved)
    total_cost = sum(s.cost_usd for s in summaries)

    reasons: Dict[str, int] = defaultdict(int)
    for summary in summaries:
        for reason in summary.termination_reasons:
            reasons[reason or "(none)"] += 1

    difficulty: Dict[str, Tuple[int, int]] = {}
    for level in ("easy", "medium", "hard"):
        rows = [s for s in summaries if s.difficulty == level]
        if rows:
            difficulty[level] = (sum(1 for s in rows if s.solved), len(rows))

    return ConditionReport(
        condition=condition,
        tasks=len(summaries),
        solved=solved,
        success_rate=proportion_ci(solved, len(summaries)),
        pass_rate=mean_ci([s.pass_rate for s in summaries]),
        tokens=mean_ci([s.tokens for s in summaries]),
        iterations=mean_ci([s.iterations for s in summaries]),
        latency_s=mean_ci([s.latency_s for s in summaries]),
        total_cost=total_cost,
        cost_per_success=(total_cost / solved) if solved else None,
        unstable_tasks=[s.task for s in summaries if s.instability],
        errors=sum(s.errors for s in summaries),
        termination_counts=dict(sorted(reasons.items(),
                                       key=lambda kv: -kv[1])),
        by_difficulty=difficulty,
    )


# =========================================================== comparisons
@dataclass
class Comparison:
    """One condition against another, on one metric."""

    left: str
    right: str
    metric: str
    left_value: float
    right_value: float
    difference: Estimate
    test: TestResult
    effect: float
    effect_label: str
    adjusted_p: Optional[float] = None
    reject: Optional[bool] = None

    @property
    def label(self) -> str:
        return f"{self.left} vs {self.right} ({self.metric})"


def _aligned(left: Sequence[TaskSummary],
             right: Sequence[TaskSummary]) -> List[Tuple[TaskSummary,
                                                         TaskSummary]]:
    """Pair the two conditions task by task.

    Only tasks both conditions attempted are paired.  A condition that skipped
    a task - no interpreter for its language, say - must not silently become a
    zero for it, because that would read as a failure rather than an absence.
    """
    by_task = {s.task: s for s in right}
    return [(item, by_task[item.task]) for item in left
            if item.task in by_task]


def compare(left: Sequence[TaskSummary], right: Sequence[TaskSummary],
            metric: str = "success") -> Comparison:
    """Compare two conditions on one metric with the appropriate test.

    The test follows the metric, not the other way round:

    * ``success`` is binary per task, so McNemar's exact test on the
      discordant pairs.
    * everything else is continuous, so the Wilcoxon signed-rank test.
    """
    pairs = _aligned(left, right)
    if not pairs:
        empty = Estimate(0.0, 0.0, 0.0, 0, "degenerate")
        return Comparison(left[0].condition if left else "?",
                          right[0].condition if right else "?", metric,
                          0.0, 0.0, empty,
                          TestResult("none", float("nan"), float("nan"), 0,
                                     "no shared tasks"), 0.0, "negligible")

    left_name = pairs[0][0].condition
    right_name = pairs[0][1].condition

    if metric == "success":
        left_values = [1.0 if a.solved else 0.0 for a, _ in pairs]
        right_values = [1.0 if b.solved else 0.0 for _, b in pairs]
        test = mcnemar_exact([a.solved for a, _ in pairs],
                             [b.solved for _, b in pairs])
    else:
        left_values = [float(getattr(a, metric)) for a, _ in pairs]
        right_values = [float(getattr(b, metric)) for _, b in pairs]
        test = wilcoxon_signed_rank(left_values, right_values)

    differences = [x - y for x, y in zip(left_values, right_values,
                                         strict=True)]
    effect = cliffs_delta(left_values, right_values)
    return Comparison(
        left=left_name, right=right_name, metric=metric,
        left_value=mean(left_values), right_value=mean(right_values),
        difference=mean_ci(differences),
        test=test, effect=effect, effect_label=interpret_delta(effect))


def compare_all(by_condition: Dict[str, List[TaskSummary]],
                pairs: Sequence[Tuple[str, str]],
                metric: str = "success",
                alpha: float = 0.05) -> List[Comparison]:
    """Several comparisons from one sweep, with Holm correction applied.

    Running three tests on the same data and reporting three uncorrected
    p-values is how a sweep produces a finding it does not have.
    """
    comparisons = [compare(by_condition[a], by_condition[b], metric)
                   for a, b in pairs
                   if a in by_condition and b in by_condition]
    usable = [i for i, c in enumerate(comparisons)
              if c.test.p_value == c.test.p_value]        # drop NaN
    adjusted = holm_bonferroni([comparisons[i].test.p_value for i in usable],
                               alpha)
    for position, index in enumerate(usable):
        _, adjusted_p, reject = adjusted[position]
        comparisons[index].adjusted_p = adjusted_p
        comparisons[index].reject = reject
    return comparisons


# =========================================================== whole report
@dataclass
class Report:
    conditions: Dict[str, ConditionReport]
    summaries: Dict[str, List[TaskSummary]]
    success_comparisons: List[Comparison] = field(default_factory=list)
    pass_rate_comparisons: List[Comparison] = field(default_factory=list)
    token_comparisons: List[Comparison] = field(default_factory=list)
    repetitions: int = 1
    metadata: Dict = field(default_factory=dict)


DEFAULT_PAIRS = (("C", "A"), ("C", "B"), ("B", "A"), ("C", "C'"))


def build(rows: Sequence[RunRow],
          pairs: Sequence[Tuple[str, str]] = DEFAULT_PAIRS,
          metadata: Optional[Dict] = None) -> Report:
    summaries = fold_repetitions(rows)
    by_condition: Dict[str, List[TaskSummary]] = defaultdict(list)
    for summary in summaries:
        by_condition[summary.condition].append(summary)

    reports = {label: summarise_condition(rows_)
               for label, rows_ in by_condition.items() if rows_}
    repetitions = max((s.repetitions for s in summaries), default=1)

    return Report(
        conditions=reports,
        summaries=dict(by_condition),
        success_comparisons=compare_all(by_condition, pairs, "success"),
        pass_rate_comparisons=compare_all(by_condition, pairs, "pass_rate"),
        token_comparisons=compare_all(by_condition, pairs, "tokens"),
        repetitions=repetitions,
        metadata=metadata or {},
    )


# =========================================================== rendering
def _order(labels: Sequence[str]) -> List[str]:
    preferred = ["A", "B", "C", "C'"]
    return ([name for name in preferred if name in labels]
            + sorted(name for name in labels if name not in preferred))


def render(report: Report, width: int = 96) -> str:
    out: List[str] = []
    line = "=" * width

    out.append(line)
    out.append("RESULTS")
    out.append(line)
    if report.metadata:
        meta = report.metadata
        out.append(f"  provider {meta.get('provider', '?')} / "
                   f"model {meta.get('model', '?')} / "
                   f"temperature {meta.get('temperature', '?')}")
        out.append(f"  iteration cap {meta.get('max_iterations', '?')} / "
                   f"{report.repetitions} repetition(s) per task / "
                   f"pricing: {meta.get('pricing', {}).get('label', '?')}")
    out.append("  unit of analysis: the task. Repetitions are averaged "
               "within a task, never\n  counted as extra observations.")
    out.append("")

    # ------------------------------------------------ per condition
    out.append(f"  {'':<28}{'solved':>14}{'pass rate':>20}"
               f"{'tokens':>18}{'$/success':>12}")
    out.append("  " + "-" * (width - 4))
    for label in _order(list(report.conditions)):
        item = report.conditions[label]
        solved = f"{item.solved}/{item.tasks}"
        rate = (f"{item.pass_rate.value * 100:.1f}% "
                f"[{item.pass_rate.low * 100:.0f}-"
                f"{item.pass_rate.high * 100:.0f}]")
        tokens = f"{item.tokens.value:,.0f}"
        # 0.0 is a real cost - the fixture is free - so this must test for
        # None, not for truthiness, or a free run reads as "no data"
        per = ("n/a" if item.cost_per_success is None
               else f"${item.cost_per_success:.5f}")
        out.append(f"  {label + ' ' + item.name:<28}{solved:>14}{rate:>20}"
                   f"{tokens:>18}{per:>12}")

    # ------------------------------------------------ success rate with CI
    out.append("")
    out.append("  task success rate, with a 95% Wilson interval:")
    for label in _order(list(report.conditions)):
        item = report.conditions[label]
        out.append(f"    {label:<4}{item.success_rate.value * 100:>6.1f}%  "
                   f"[{item.success_rate.low * 100:.1f}%, "
                   f"{item.success_rate.high * 100:.1f}%]"
                   f"   n={item.tasks}")

    # ------------------------------------------------ difficulty
    levels = ("easy", "medium", "hard")
    if any(c.by_difficulty for c in report.conditions.values()):
        out.append("")
        out.append("  solved by difficulty:")
        out.append(f"    {'':<6}" + "".join(f"{x:>12}" for x in levels))
        for label in _order(list(report.conditions)):
            item = report.conditions[label]
            cells = ""
            for level in levels:
                got = item.by_difficulty.get(level)
                cells += f"{(f'{got[0]}/{got[1]}' if got else '-'):>12}"
            out.append(f"    {label:<6}{cells}")

    # ------------------------------------------------ stability
    unstable = {name: report.conditions[name].unstable_tasks
                for name in report.conditions
                if report.conditions[name].unstable_tasks}
    if report.repetitions > 1:
        out.append("")
        if unstable:
            out.append("  tasks where repetitions disagreed (counted by the "
                       "majority rule):")
            for label, tasks in unstable.items():
                out.append(f"    {label:<4}{', '.join(tasks)}")
        else:
            out.append("  every repetition agreed on every task.")

    # ------------------------------------------------ termination
    out.append("")
    out.append("  how runs ended:")
    for label in _order(list(report.conditions)):
        counts = report.conditions[label].termination_counts
        shown = ", ".join(f"{k} x{v}" for k, v in list(counts.items())[:5])
        out.append(f"    {label:<4}{shown}")

    # ------------------------------------------------ comparisons
    for title, comparisons in (
        ("task success (McNemar, exact, on discordant pairs)",
         report.success_comparisons),
        ("mean pass rate (Wilcoxon signed-rank)",
         report.pass_rate_comparisons),
        ("tokens (Wilcoxon signed-rank)", report.token_comparisons),
    ):
        if not comparisons:
            continue
        out.append("")
        out.append(line)
        out.append(f"  {title}")
        out.append(line)
        out.append(f"  {'comparison':<16}{'left':>10}{'right':>10}"
                   f"{'n':>5}{'p':>10}{'p adj':>10}{'effect':>22}")
        out.append("  " + "-" * (width - 4))
        for item in comparisons:
            adjusted = (f"{item.adjusted_p:.4f}"
                        if item.adjusted_p is not None else "-")
            marker = " *" if item.reject else ""
            out.append(
                f"  {item.left + ' vs ' + item.right:<16}"
                f"{item.left_value:>10.3f}{item.right_value:>10.3f}"
                f"{item.test.n:>5}{item.test.p_value:>10.4f}"
                f"{adjusted:>10}"
                f"{f'{item.effect:+.2f} {item.effect_label}':>20}{marker}")
        out.append("  * significant at 0.05 after Holm correction across the "
                   "comparisons above")
        for item in comparisons:
            if item.test.detail:
                out.append(f"    {item.left} vs {item.right}: "
                           f"{item.test.detail}")

    out.append("")
    out.append(line)
    return "\n".join(out)
