"""Week 11: the statistics, and the analysis built on them.

Wrong statistical code does not crash. It returns a plausible number, and a
write-up repeats it. So this file tests three different ways:

* **against SciPy**, on any machine that has it. SciPy is not a dependency,
  so these tests skip rather than fail where it is absent - but they are the
  reason the stdlib implementations can be trusted.
* **against hand-computable answers**, which cover the cases SciPy would
  agree with for the wrong reason.
* **against the design**, which is where the real risk lives: the unit of
  analysis, the choice of test per metric, and the multiple-comparison
  correction are all things that can be silently wrong while every number
  looks reasonable.
"""

import math
import random

import pytest

from mawe.bench import report as reporting
from mawe.bench import stats
from mawe.bench.experiment import RunRow

try:
    import scipy.stats as ss
except ImportError:                                        # pragma: no cover
    ss = None

needs_scipy = pytest.mark.skipif(ss is None, reason="SciPy not installed")


# ===================================================== descriptives
def test_descriptives_on_a_known_sample():
    data = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    assert stats.mean(data) == 5.0
    assert stats.variance(data) == pytest.approx(32 / 7)
    assert stats.stdev(data) == pytest.approx(math.sqrt(32 / 7))
    assert stats.median(data) == 4.5
    assert stats.median([3.0]) == 3.0


def test_descriptives_of_nothing_are_zero_not_an_exception():
    assert stats.mean([]) == 0.0
    assert stats.variance([]) == 0.0
    assert stats.stdev([1.0]) == 0.0
    assert stats.median([]) == 0.0


# ===================================================== special functions
@needs_scipy
@pytest.mark.parametrize("t,df", [(2.0, 10), (0.5, 5), (3.7, 19),
                                  (1.96, 1000), (0.1, 2), (0.0, 8)])
def test_student_t_matches_scipy(t, df):
    assert stats.student_t_two_sided_p(t, df) == \
        pytest.approx(2 * ss.t.sf(abs(t), df) if t else 1.0, abs=1e-12)


@needs_scipy
@pytest.mark.parametrize("df", [1, 5, 10, 19, 30, 120])
def test_t_critical_matches_scipy(df):
    assert stats.t_critical(df) == pytest.approx(ss.t.ppf(0.975, df),
                                                 abs=1e-9)


@needs_scipy
def test_normal_quantile_matches_scipy():
    for p in (0.5, 0.75, 0.975, 0.995, 0.025):
        assert stats.normal_quantile(p) == pytest.approx(ss.norm.ppf(p),
                                                         abs=1e-10)


def test_normal_quantile_rejects_an_impossible_probability():
    assert math.isnan(stats.normal_quantile(0.0))
    assert math.isnan(stats.normal_quantile(1.0))


def test_betainc_endpoints():
    assert stats.betainc(2.0, 3.0, 0.0) == 0.0
    assert stats.betainc(2.0, 3.0, 1.0) == 1.0
    # I_0.5(a, a) is 0.5 for any a, by symmetry
    assert stats.betainc(3.0, 3.0, 0.5) == pytest.approx(0.5, abs=1e-12)


def test_the_two_sided_normal_p_is_symmetric():
    assert stats.normal_two_sided_p(1.96) == pytest.approx(0.0499958, abs=1e-6)
    assert stats.normal_two_sided_p(-1.96) == stats.normal_two_sided_p(1.96)
    assert stats.normal_two_sided_p(0.0) == 1.0


# ===================================================== intervals
@needs_scipy
def test_mean_ci_matches_a_t_interval():
    random.seed(3)
    data = [random.gauss(10, 2) for _ in range(25)]
    estimate = stats.mean_ci(data)
    low, high = ss.t.interval(0.95, len(data) - 1, loc=stats.mean(data),
                              scale=stats.stdev(data) / math.sqrt(len(data)))
    assert estimate.low == pytest.approx(low, abs=1e-9)
    assert estimate.high == pytest.approx(high, abs=1e-9)
    assert estimate.n == 25
    assert estimate.method == "t"


@needs_scipy
@pytest.mark.parametrize("successes,trials", [(18, 20), (0, 20), (20, 20),
                                              (10, 20), (3, 7)])
def test_proportion_ci_matches_a_wilson_interval(successes, trials):
    mine = stats.proportion_ci(successes, trials)
    reference = ss.binomtest(successes, trials).proportion_ci(method="wilson")
    assert mine.low == pytest.approx(reference.low, abs=1e-12)
    assert mine.high == pytest.approx(reference.high, abs=1e-12)


def test_a_perfect_score_still_reports_uncertainty():
    """The reason the Wilson interval is used instead of the normal one.

    20 out of 20 is not proof of a 100% success rate, and the textbook normal
    interval would claim exactly that - zero width - which would be the most
    overconfident sentence in the report.
    """
    estimate = stats.proportion_ci(20, 20)
    assert estimate.value == 1.0
    assert estimate.low < 0.9, "a perfect score from n=20 is not certainty"
    # the closed form lands a float epsilon below 1; it matches SciPy to 3e-16
    assert estimate.high == pytest.approx(1.0, abs=1e-12)


def test_a_zero_score_reports_an_upper_bound():
    estimate = stats.proportion_ci(0, 20)
    assert estimate.low == 0.0
    assert 0.0 < estimate.high < 0.25


def test_degenerate_intervals_do_not_explode():
    assert stats.proportion_ci(0, 0).method == "degenerate"
    assert stats.mean_ci([]).method == "degenerate"
    assert stats.mean_ci([4.0]).value == 4.0
    assert stats.bootstrap_ci([4.0]).method == "degenerate"


def test_the_bootstrap_is_reproducible():
    random.seed(1)
    data = [random.gauss(0, 1) for _ in range(30)]
    first = stats.bootstrap_ci(data, resamples=500)
    second = stats.bootstrap_ci(data, resamples=500)
    assert (first.low, first.high) == (second.low, second.high)
    different = stats.bootstrap_ci(data, resamples=500, seed=99)
    assert (different.low, different.high) != (first.low, first.high)
    assert first.low < stats.mean(data) < first.high


def test_an_estimate_prints_its_interval():
    text = str(stats.Estimate(0.5, 0.4, 0.6, 20))
    assert "0.5" in text and "0.4" in text and "0.6" in text
    assert stats.Estimate(0.5, 0.4, 0.6, 20).margin == pytest.approx(0.1)


# ===================================================== paired tests
@needs_scipy
def test_paired_t_matches_scipy():
    random.seed(7)
    a = [random.gauss(0, 1) for _ in range(20)]
    b = [random.gauss(0.4, 1) for _ in range(20)]
    mine = stats.paired_t_test(a, b)
    reference = ss.ttest_rel(a, b)
    assert mine.statistic == pytest.approx(reference.statistic, abs=1e-12)
    assert mine.p_value == pytest.approx(reference.pvalue, abs=1e-12)


def test_paired_t_on_identical_samples_is_not_significant():
    data = [1.0, 2.0, 3.0]
    result = stats.paired_t_test(data, data)
    assert result.p_value == 1.0
    assert "identical" in result.detail
    assert not result.significant()


def test_paired_t_needs_matching_lengths():
    with pytest.raises(ValueError, match="same length"):
        stats.paired_t_test([1.0, 2.0], [1.0])


@needs_scipy
def test_wilcoxon_exact_matches_scipy_when_there_are_no_ties():
    random.seed(11)
    for _ in range(8):
        n = random.choice([6, 8, 10, 12, 15])
        while True:
            a = [round(random.uniform(0, 50), 4) for _ in range(n)]
            b = [round(random.uniform(0, 50), 4) for _ in range(n)]
            gaps = [abs(x - y) for x, y in zip(a, b, strict=True)]
            if len(set(gaps)) == n and 0 not in gaps:
                break
        mine = stats.wilcoxon_signed_rank(a, b)
        reference = ss.wilcoxon(a, b, method="exact")
        assert mine.detail == "exact"
        assert mine.statistic == pytest.approx(reference.statistic)
        assert mine.p_value == pytest.approx(reference.pvalue, abs=1e-12)


@needs_scipy
def test_wilcoxon_with_ties_matches_the_scipy_approximation():
    a = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    b = [2, 2, 4, 4, 6, 6, 8, 8, 10, 10, 12, 12]
    mine = stats.wilcoxon_signed_rank(a, b)
    reference = ss.wilcoxon(a, b, method="approx", correction=False,
                            zero_method="wilcox")
    assert mine.p_value == pytest.approx(reference.pvalue, abs=1e-12)
    assert "tie correction" in mine.detail


def test_wilcoxon_falls_back_to_the_approximation_when_ranks_are_tied():
    """The exact null distribution does not hold once ranks are averaged."""
    a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    b = [2.0, 1.0, 4.0, 3.0, 6.0, 5.0]       # every |difference| is 1
    result = stats.wilcoxon_signed_rank(a, b)
    assert "approximation" in result.detail


def test_wilcoxon_says_how_many_zero_pairs_it_discarded():
    a = [1.0, 2.0, 3.0, 4.0, 9.0]
    b = [1.0, 2.0, 3.0, 4.0, 1.0]           # four identical pairs
    result = stats.wilcoxon_signed_rank(a, b)
    assert result.n == 1, "n must be the non-zero pairs, not the total"
    assert "4 zero difference" in result.detail


def test_wilcoxon_on_entirely_identical_samples():
    data = [1.0, 2.0, 3.0]
    result = stats.wilcoxon_signed_rank(data, data)
    assert result.p_value == 1.0
    assert result.n == 0


def test_wilcoxon_accepts_differences_directly():
    paired = stats.wilcoxon_signed_rank([5.0, 7.0, 9.0], [1.0, 2.0, 3.0])
    direct = stats.wilcoxon_signed_rank([4.0, 5.0, 6.0])
    assert paired.p_value == direct.p_value


def test_the_rank_sum_distribution_is_symmetric_and_complete():
    counts = stats._rank_sum_distribution(5)
    assert sum(counts) == 2 ** 5
    assert counts == counts[::-1]


@needs_scipy
@pytest.mark.parametrize("k,n", [(3, 10), (0, 7), (5, 5), (12, 20), (1, 2)])
def test_the_binomial_p_matches_scipy(k, n):
    assert stats.binomial_two_sided_p(k, n) == \
        pytest.approx(ss.binomtest(k, n, 0.5).pvalue, abs=1e-14)


def test_the_binomial_p_includes_the_mirror_outcome():
    """A float comparison without slack drops the symmetric tail.

    P(X<=2) + P(X>=8) at n=10 is 0.109375; losing one side would halve it.
    """
    assert stats.binomial_two_sided_p(2, 10) == pytest.approx(0.109375)
    assert stats.binomial_two_sided_p(5, 10) == 1.0


# ===================================================== McNemar
def test_mcnemar_counts_only_the_discordant_pairs():
    a = [True] * 10 + [False] * 10
    b = [True] * 10 + [False] * 10
    a[15] = True        # one task only A solved
    result = stats.mcnemar_exact(a, b)
    assert result.n == 1, "19 agreeing pairs carry no information"
    assert result.statistic == 1.0
    assert result.p_value == 1.0


def test_mcnemar_detects_a_one_sided_disagreement():
    a = [True] * 8 + [False] * 12
    b = [False] * 20
    result = stats.mcnemar_exact(a, b)
    assert result.n == 8
    assert result.p_value == pytest.approx(2 ** -7)
    assert result.significant()


def test_mcnemar_on_perfect_agreement():
    flags = [True, False, True]
    result = stats.mcnemar_exact(flags, flags)
    assert result.p_value == 1.0
    assert result.n == 0
    assert "exactly the same" in result.detail


def test_mcnemar_needs_matching_lengths():
    with pytest.raises(ValueError, match="same length"):
        stats.mcnemar_exact([True], [True, False])


def test_mcnemar_is_the_right_test_for_binary_outcomes():
    """Why the report does not use Wilcoxon for task success.

    20 tasks, 3 of which one condition solves and the other does not. The
    signed-rank test drops the 17 agreeing pairs and then computes from n=3 -
    while its n field, if nobody looks, suggests a 20-task comparison. The
    discarding is not the error; reporting it as a 20-task result would be.
    McNemar makes the real sample size, 3, the headline.
    """
    a = [True] * 3 + [True] * 17
    b = [False] * 3 + [True] * 17

    mcnemar = stats.mcnemar_exact(a, b)
    wilcoxon = stats.wilcoxon_signed_rank([float(x) for x in a],
                                          [float(x) for x in b])
    assert mcnemar.n == 3
    assert wilcoxon.n == 3, "both end up at n=3; only one says so plainly"
    assert mcnemar.p_value == pytest.approx(0.25)
    assert "17 pairs" not in mcnemar.detail
    assert "20 pairs" in mcnemar.detail


# ===================================================== effect size
def test_cliffs_delta_spans_its_range():
    assert stats.cliffs_delta([3.0, 4.0], [1.0, 2.0]) == 1.0
    assert stats.cliffs_delta([1.0, 2.0], [3.0, 4.0]) == -1.0
    assert stats.cliffs_delta([1.0, 2.0], [1.0, 2.0]) == 0.0
    assert stats.cliffs_delta([], [1.0]) == 0.0


@pytest.mark.parametrize("delta,label", [
    (0.05, "negligible"), (0.2, "small"), (0.4, "medium"), (0.8, "large"),
    (-0.8, "large"),
])
def test_effect_sizes_are_labelled(delta, label):
    assert stats.interpret_delta(delta) == label


def test_rank_biserial_rejects_mismatched_lengths():
    """Without the check, zip truncates and returns a plausible number."""
    with pytest.raises(ValueError, match="same length"):
        stats.rank_biserial([1.0, 2.0, 3.0], [1.0, 2.0])


@pytest.mark.parametrize("function", [
    stats.paired_t_test, stats.wilcoxon_signed_rank, stats.rank_biserial,
])
def test_every_paired_function_validates_its_lengths(function):
    with pytest.raises(ValueError, match="same length"):
        function([1.0, 2.0], [1.0])


def test_rank_biserial_matches_its_definition():
    assert stats.rank_biserial([2.0, 3.0, 4.0], [1.0, 1.0, 1.0]) == 1.0
    assert stats.rank_biserial([1.0, 1.0], [1.0, 1.0]) == 0.0
    assert stats.rank_biserial([1.0, 2.0], [2.0, 1.0]) == 0.0


# ===================================================== multiple testing
def test_holm_adjusts_and_stays_monotone():
    adjusted = stats.holm_bonferroni([0.01, 0.04, 0.03])
    raw = [row[0] for row in adjusted]
    assert raw == [0.01, 0.04, 0.03], "order is preserved"
    values = sorted(row[1] for row in adjusted)
    assert values == sorted(values), "adjusted p-values are monotone"
    assert adjusted[0][1] == pytest.approx(0.03)      # 0.01 * 3
    assert adjusted[0][2] is True


def test_holm_is_not_more_conservative_than_bonferroni():
    p_values = [0.01, 0.02, 0.03]
    adjusted = stats.holm_bonferroni(p_values)
    for raw, value, _ in adjusted:
        assert value <= min(1.0, raw * len(p_values)) + 1e-12


def test_holm_caps_at_one():
    assert all(value <= 1.0 for _, value, _ in
               stats.holm_bonferroni([0.5, 0.6, 0.9]))


def test_holm_rejects_nothing_when_everything_is_large():
    assert not any(reject for _, _, reject in
                   stats.holm_bonferroni([0.2, 0.3, 0.4]))


def test_holm_on_an_empty_list():
    assert stats.holm_bonferroni([]) == []


# ===================================================== the report
def row(condition, task, repetition=1, success=True, pass_rate=1.0,
        tokens=100, difficulty="easy", iterations=1, reason="approved"):
    return RunRow(condition=condition, task=task, difficulty=difficulty,
                  language="python", repetition=repetition, success=success,
                  pass_rate=pass_rate, prompt_tokens=tokens,
                  completion_tokens=0, iterations=iterations,
                  termination_reason=reason, hidden_tests_total=5,
                  hidden_tests_passed=int(5 * pass_rate))


def test_repetitions_are_averaged_not_counted_as_observations():
    """The invariant the whole analysis rests on.

    Three runs of one task are one observation. Counting them as three would
    treble n and shrink every interval by about 1.7 without a single extra
    task having been attempted.
    """
    rows = [row("C", "fizzbuzz", r) for r in (1, 2, 3)]
    folded = reporting.fold_repetitions(rows)
    assert len(folded) == 1
    assert folded[0].repetitions == 3

    summary = reporting.summarise_condition(folded)
    assert summary.tasks == 1
    assert summary.success_rate.n == 1, "n is tasks, never runs"


def test_a_task_is_solved_only_on_a_majority_of_repetitions():
    one_of_three = reporting.fold_repetitions([
        row("C", "t", 1, success=True),
        row("C", "t", 2, success=False),
        row("C", "t", 3, success=False)])[0]
    assert not one_of_three.solved
    assert one_of_three.success_fraction == pytest.approx(1 / 3)
    assert one_of_three.instability

    two_of_three = reporting.fold_repetitions([
        row("C", "t", 1, success=True),
        row("C", "t", 2, success=True),
        row("C", "t", 3, success=False)])[0]
    assert two_of_three.solved
    assert two_of_three.instability


def test_consistent_repetitions_are_not_flagged_unstable():
    folded = reporting.fold_repetitions([row("C", "t", r) for r in (1, 2, 3)])
    assert not folded[0].instability
    assert folded[0].success_fraction == 1.0


def test_skipped_runs_are_excluded_rather_than_scored_as_failures():
    skipped = row("C", "jsthing", success=False)
    skipped.skipped = "no javascript interpreter"
    folded = reporting.fold_repetitions([row("C", "fizzbuzz"), skipped])
    assert [s.task for s in folded] == ["fizzbuzz"]


def test_a_condition_report_covers_every_column_the_table_needs():
    rows = [row("C", f"t{i}", pass_rate=1.0, tokens=200) for i in range(4)]
    item = reporting.summarise_condition(reporting.fold_repetitions(rows))
    assert item.solved == 4 and item.tasks == 4
    assert item.success_rate.value == 1.0
    assert item.pass_rate.value == 1.0
    assert item.tokens.value == 200
    assert item.cost_per_success == 0.0, "free is a cost, not missing data"
    assert item.termination_counts == {"approved": 4}
    assert item.name == "multi-agent engine"


def test_cost_per_success_is_none_when_nothing_succeeded():
    rows = [row("A", f"t{i}", success=False, pass_rate=0.2) for i in range(3)]
    item = reporting.summarise_condition(reporting.fold_repetitions(rows))
    assert item.solved == 0
    assert item.cost_per_success is None


def test_only_tasks_both_conditions_attempted_are_paired():
    left = reporting.fold_repetitions([row("C", "a"), row("C", "b")])
    right = reporting.fold_repetitions([row("A", "a", success=False,
                                            pass_rate=0.0)])
    comparison = reporting.compare(left, right, "success")
    assert comparison.test.n == 1, "task 'b' has no counterpart to pair with"


def test_comparing_with_no_shared_tasks_is_reported_not_raised():
    left = reporting.fold_repetitions([row("C", "a")])
    right = reporting.fold_repetitions([row("A", "z")])
    comparison = reporting.compare(left, right, "success")
    assert comparison.test.n == 0
    assert "no shared" in comparison.test.detail


def test_success_uses_mcnemar_and_other_metrics_use_wilcoxon():
    left = reporting.fold_repetitions([row("C", f"t{i}") for i in range(6)])
    right = reporting.fold_repetitions([
        row("A", f"t{i}", success=False, pass_rate=0.4) for i in range(6)])
    assert reporting.compare(left, right, "success").test.name == "mcnemar"
    assert reporting.compare(left, right, "pass_rate").test.name == "wilcoxon"
    assert reporting.compare(left, right, "tokens").test.name == "wilcoxon"


def test_several_comparisons_are_holm_corrected():
    by_condition = {}
    for label, ok in (("A", False), ("B", True), ("C", True)):
        rows = [row(label, f"t{i}", success=ok,
                    pass_rate=1.0 if ok else 0.3) for i in range(20)]
        by_condition[label] = reporting.fold_repetitions(rows)

    comparisons = reporting.compare_all(
        by_condition, [("C", "A"), ("B", "A"), ("C", "B")], "success")
    assert len(comparisons) == 3
    for item in comparisons:
        assert item.adjusted_p is not None
        assert item.adjusted_p >= item.test.p_value


def test_building_and_rendering_a_whole_report():
    rows = []
    for label, ok in (("A", False), ("B", True), ("C", True), ("C'", True)):
        for i in range(6):
            level = ["easy", "medium", "hard"][i % 3]
            rows.append(row(label, f"t{i}", success=ok, difficulty=level,
                            pass_rate=1.0 if ok else 0.5,
                            tokens=100 if label == "A" else 400))

    built = reporting.build(rows, metadata={"provider": "oracle",
                                            "model": "oracle-1"})
    assert set(built.conditions) == {"A", "B", "C", "C'"}
    assert built.conditions["A"].solved == 0
    assert built.conditions["C"].solved == 6

    text = reporting.render(built)
    assert "RESULTS" in text
    assert "McNemar" in text
    assert "unit of analysis: the task" in text
    assert "oracle-1" in text
    for level in ("easy", "medium", "hard"):
        assert level in text


def test_rendering_an_empty_report_does_not_raise():
    text = reporting.render(reporting.build([]))
    assert "RESULTS" in text
