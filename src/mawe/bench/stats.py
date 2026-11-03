"""The statistics Phase 4 reports, in the standard library.

Week 11.  Two decisions are worth explaining, because both were deliberate.

**Why no SciPy.**  SciPy is installed on the machines this was written on but
is not a dependency of the project, and adding it so that CI can compute one
p-value is a poor trade.  Everything here is stdlib, and
``tests/test_stats.py`` checks it against SciPy on any machine that has it, so
the implementations are verified rather than merely plausible.

**Why not only the Wilcoxon signed-rank test.**  The proposal says "paired
t-test or Wilcoxon signed-rank", and for a continuous metric - tokens, pass
rate, latency - Wilcoxon is right and is implemented here.  For the headline
metric it is not.  Task success is binary per task, so almost every paired
difference is exactly zero, and the signed-rank test discards zeros: with 20
tasks and three disagreements it would be computing a p-value from n = 3 while
appearing to use all twenty.  The correct test for paired binary outcomes is
McNemar's, exactly, on the discordant pairs, so that is what the report uses
for success and what ``mcnemar_exact`` implements.  Using Wilcoxon there would
not have failed loudly; it would have produced a confident number from the
wrong denominator.

Everything is deterministic.  The bootstrap takes an explicit seed so a
reported interval can be reproduced exactly.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

# ======================================================= basic descriptives
def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def variance(values: Sequence[float]) -> float:
    """Sample variance, with Bessel's correction."""
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    return sum((v - mu) ** 2 for v in values) / (len(values) - 1)


def stdev(values: Sequence[float]) -> float:
    return math.sqrt(variance(values))


def median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


# ======================================================= special functions
def _log_beta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _betacf(a: float, b: float, x: float, iterations: int = 300) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, iterations + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.log(x) * a + math.log1p(-x) * b - _log_beta(a, b))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(math.log1p(-x) * b + math.log(x) * a
                          - _log_beta(b, a)) * _betacf(b, a, 1.0 - x) / b


def student_t_two_sided_p(t: float, df: float) -> float:
    """P(|T| >= |t|) for Student's t with `df` degrees of freedom."""
    if df <= 0:
        return float("nan")
    if t == 0:
        return 1.0
    return betainc(df / 2.0, 0.5, df / (df + t * t))


def t_critical(df: float, confidence: float = 0.95) -> float:
    """The two-sided critical value, by bisection on the exact p-value.

    A lookup table would be shorter and would stop being right the moment the
    design changes the number of tasks or repetitions.
    """
    if df <= 0:
        return float("nan")
    target = 1.0 - confidence
    low, high = 0.0, 1e4
    for _ in range(200):
        middle = (low + high) / 2.0
        if student_t_two_sided_p(middle, df) > target:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def normal_two_sided_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2.0))


def normal_quantile(p: float) -> float:
    """Inverse standard normal CDF, by bisection on `erfc`.

    Used by the Wilson interval.  An earlier version borrowed
    `t_critical(1e6)` for this, which is right to about six decimal places -
    harmless here, but a quantile that is only approximately the quantile is
    the sort of thing that gets copied somewhere it matters.
    """
    if not 0.0 < p < 1.0:
        return float("nan")
    low, high = -40.0, 40.0
    for _ in range(200):
        middle = (low + high) / 2.0
        cdf = 0.5 * math.erfc(-middle / math.sqrt(2.0))
        if cdf < p:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


# ======================================================= intervals
@dataclass(frozen=True)
class Estimate:
    """A point estimate with an interval and the n it came from."""

    value: float
    low: float
    high: float
    n: int
    method: str = "t"

    def __str__(self) -> str:
        return f"{self.value:.4g} [{self.low:.4g}, {self.high:.4g}]"

    @property
    def margin(self) -> float:
        return (self.high - self.low) / 2.0


def mean_ci(values: Sequence[float], confidence: float = 0.95) -> Estimate:
    """Mean with a t-based confidence interval."""
    n = len(values)
    mu = mean(values)
    if n < 2:
        return Estimate(mu, mu, mu, n, "degenerate")
    half = t_critical(n - 1, confidence) * stdev(values) / math.sqrt(n)
    return Estimate(mu, mu - half, mu + half, n, "t")


def proportion_ci(successes: int, trials: int,
                  confidence: float = 0.95) -> Estimate:
    """Wilson score interval for a proportion.

    Not the textbook normal interval: at the rates this experiment can
    produce - 20 of 20, or 0 of 20 - the normal interval collapses to zero
    width, which would report a success rate of 100% with no uncertainty at
    all from twenty observations.
    """
    if trials <= 0:
        return Estimate(0.0, 0.0, 0.0, 0, "degenerate")
    z = normal_quantile(1.0 - (1.0 - confidence) / 2.0)
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = (p + z * z / (2.0 * trials)) / denominator
    half = (z / denominator) * math.sqrt(
        p * (1.0 - p) / trials + z * z / (4.0 * trials * trials))
    return Estimate(p, max(0.0, centre - half), min(1.0, centre + half),
                    trials, "wilson")


def bootstrap_ci(values: Sequence[float], confidence: float = 0.95,
                 resamples: int = 10_000, seed: int = 20261101) -> Estimate:
    """Percentile bootstrap interval for the mean.

    Seeded, so a published interval can be reproduced exactly.
    """
    n = len(values)
    if n < 2:
        mu = mean(values)
        return Estimate(mu, mu, mu, n, "degenerate")
    rng = random.Random(seed)
    data = list(values)
    means = []
    for _ in range(resamples):
        means.append(mean([data[rng.randrange(n)] for _ in range(n)]))
    means.sort()
    tail = (1.0 - confidence) / 2.0
    low = means[int(tail * resamples)]
    high = means[min(resamples - 1, int((1.0 - tail) * resamples))]
    return Estimate(mean(data), low, high, n, "bootstrap")


# ======================================================= paired tests
@dataclass(frozen=True)
class TestResult:
    name: str
    statistic: float
    p_value: float
    n: int
    detail: str = ""

    def __str__(self) -> str:
        return (f"{self.name}: statistic={self.statistic:.4g}, "
                f"p={self.p_value:.4g}, n={self.n}"
                + (f" ({self.detail})" if self.detail else ""))

    def significant(self, alpha: float = 0.05) -> bool:
        return self.p_value < alpha


def paired_t_test(a: Sequence[float], b: Sequence[float]) -> TestResult:
    if len(a) != len(b):
        raise ValueError("paired samples must be the same length")
    differences = [x - y for x, y in zip(a, b, strict=True)]
    n = len(differences)
    if n < 2:
        return TestResult("paired t", float("nan"), float("nan"), n,
                          "fewer than two pairs")
    spread = stdev(differences)
    if spread == 0:
        return TestResult("paired t", 0.0, 1.0, n, "every pair is identical")
    t = mean(differences) / (spread / math.sqrt(n))
    return TestResult("paired t", t, student_t_two_sided_p(t, n - 1), n)


def _rank_sum_distribution(n: int) -> List[int]:
    """Counts of sign subsets of {1..n} by rank sum, for the exact Wilcoxon.

    Dynamic programming over rank sums rather than enumerating 2**n sign
    patterns, which would be a million iterations at n = 20 and unusable at
    n = 40.
    """
    total = n * (n + 1) // 2
    counts = [0] * (total + 1)
    counts[0] = 1
    for rank in range(1, n + 1):
        for value in range(total, rank - 1, -1):
            counts[value] += counts[value - rank]
    return counts


def _midranks(values: Sequence[float]) -> Tuple[List[float], bool]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    tied = False
    index = 0
    while index < len(order):
        stop = index
        while stop + 1 < len(order) and \
                values[order[stop + 1]] == values[order[index]]:
            stop += 1
        average = (index + stop) / 2.0 + 1.0
        if stop > index:
            tied = True
        for position in range(index, stop + 1):
            ranks[order[position]] = average
        index = stop + 1
    return ranks, tied


def wilcoxon_signed_rank(a: Sequence[float],
                         b: Optional[Sequence[float]] = None) -> TestResult:
    """Paired Wilcoxon signed-rank test, two-sided.

    Zero differences are dropped, which is Wilcoxon's own convention and the
    reason this test is the wrong one for binary outcomes - see the module
    docstring.  `n` in the result is the number of *non-zero* pairs, so the
    discarding is visible rather than implied.

    Exact when there are no ties among the absolute differences; otherwise the
    normal approximation with a tie correction, because the exact null
    distribution does not hold once ranks are averaged.
    """
    if b is not None:
        if len(a) != len(b):
            raise ValueError("paired samples must be the same length")
        differences = [x - y for x, y in zip(a, b, strict=True)]
    else:
        differences = list(a)

    dropped = sum(1 for d in differences if d == 0)
    nonzero = [d for d in differences if d != 0]
    n = len(nonzero)
    note = f"{dropped} zero difference(s) dropped" if dropped else ""

    if n == 0:
        return TestResult("wilcoxon", 0.0, 1.0, 0,
                          "every pair is identical" if dropped else "no data")
    if n < 2:
        return TestResult("wilcoxon", float("nan"), float("nan"), n,
                          (note + "; " if note else "")
                          + "too few non-zero pairs to test")

    ranks, tied = _midranks([abs(d) for d in nonzero])
    w_plus = sum(r for d, r in zip(nonzero, ranks, strict=True) if d > 0)
    w_minus = sum(r for d, r in zip(nonzero, ranks, strict=True) if d < 0)
    statistic = min(w_plus, w_minus)

    if not tied and n <= 40:
        counts = _rank_sum_distribution(n)
        total = float(sum(counts))
        at_or_below = sum(counts[:int(statistic) + 1])
        p = min(1.0, 2.0 * at_or_below / total)
        method = "exact"
    else:
        expected = n * (n + 1) / 4.0
        tie_term = 0.0
        if tied:
            groups: Dict[float, int] = {}
            for value in (abs(d) for d in nonzero):
                groups[value] = groups.get(value, 0) + 1
            tie_term = sum(t ** 3 - t for t in groups.values()) / 48.0
        spread = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0 - tie_term)
        if spread == 0:
            return TestResult("wilcoxon", statistic, 1.0, n, note)
        z = (statistic - expected) / spread
        p = min(1.0, normal_two_sided_p(z))
        method = "normal approximation" + (" with tie correction" if tied
                                           else "")

    detail = ", ".join(x for x in (note, method) if x)
    return TestResult("wilcoxon", statistic, p, n, detail)


def binomial_two_sided_p(successes: int, trials: int,
                         probability: float = 0.5) -> float:
    """Exact two-sided binomial p-value, by summing all outcomes no more
    likely than the observed one."""
    if trials <= 0:
        return 1.0

    def pmf(k: int) -> float:
        return (math.comb(trials, k) * probability ** k
                * (1.0 - probability) ** (trials - k))

    observed = pmf(successes)
    # the float comparison needs slack, or the observed outcome's mirror image
    # is excluded by a rounding error and the p-value comes out too small
    tolerance = observed * (1.0 + 1e-9)
    return min(1.0, sum(pmf(k) for k in range(trials + 1)
                        if pmf(k) <= tolerance))


def mcnemar_exact(a: Sequence[bool], b: Sequence[bool]) -> TestResult:
    """McNemar's test, exact, for paired binary outcomes.

    The right test for "did condition A and condition C succeed on the same
    tasks": only the tasks where they disagree carry information, and the
    question is whether the disagreements split evenly.

    The statistic reported is the number of tasks where `a` succeeded and `b`
    did not, and `n` is the number of discordant pairs - the real sample size,
    which is usually far smaller than the number of tasks and ought to be
    visible in the write-up.
    """
    if len(a) != len(b):
        raise ValueError("paired samples must be the same length")
    only_a = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    only_b = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    discordant = only_a + only_b
    if discordant == 0:
        return TestResult("mcnemar", 0.0, 1.0, 0,
                          "the two conditions succeeded on exactly the same "
                          "tasks")
    p = binomial_two_sided_p(only_a, discordant, 0.5)
    return TestResult("mcnemar", float(only_a), p, discordant,
                      f"{only_a} only-first, {only_b} only-second, "
                      f"{len(a)} pairs")


# ======================================================= effect size
def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """Non-parametric effect size in [-1, 1].

    Reported alongside the p-value because "significant" says nothing about
    size, and at n = 20 a significant result can still be tiny.
    """
    if not a or not b:
        return 0.0
    greater = sum(1 for x in a for y in b if x > y)
    less = sum(1 for x in a for y in b if x < y)
    return (greater - less) / (len(a) * len(b))


def interpret_delta(delta: float) -> str:
    size = abs(delta)
    if size < 0.147:
        return "negligible"
    if size < 0.33:
        return "small"
    if size < 0.474:
        return "medium"
    return "large"


def rank_biserial(a: Sequence[float], b: Sequence[float]) -> float:
    """Matched-pairs rank-biserial correlation: Wilcoxon's effect size.

    Validates the lengths like every other paired function here. Without the
    check, `zip` silently truncates to the shorter sequence and the function
    returns a plausible effect size computed from part of the data - the
    failure mode this whole module is written to avoid.
    """
    if len(a) != len(b):
        raise ValueError("paired samples must be the same length")
    differences = [x - y for x, y in zip(a, b, strict=True)]
    nonzero = [d for d in differences if d != 0]
    if not nonzero:
        return 0.0
    ranks, _ = _midranks([abs(d) for d in nonzero])
    total = sum(ranks)
    positive = sum(r for d, r in zip(nonzero, ranks, strict=True) if d > 0)
    negative = total - positive
    return (positive - negative) / total


# ======================================================= multiple testing
def holm_bonferroni(p_values: Sequence[float],
                    alpha: float = 0.05) -> List[Tuple[float, float, bool]]:
    """Holm-Bonferroni adjusted p-values and decisions.

    Phase 4 makes several paired comparisons from one sweep - C against A, C
    against B, C against C' - and reporting three uncorrected p-values from
    the same data inflates the chance that one of them is below 0.05.  Holm is
    uniformly more powerful than plain Bonferroni at the same guarantee, so
    there is no reason to use the latter.

    Returns (raw, adjusted, reject) in the order the p-values were given.
    """
    indexed = sorted(range(len(p_values)), key=lambda i: p_values[i])
    total = len(p_values)
    adjusted = [0.0] * total
    running = 0.0
    for position, index in enumerate(indexed):
        scaled = min(1.0, (total - position) * p_values[index])
        running = max(running, scaled)        # enforce monotonicity
        adjusted[index] = running
    return [(p_values[i], adjusted[i], adjusted[i] < alpha)
            for i in range(total)]
