"""Week 6: the loop policy, including a randomised adversarial stress test.

The hand-written scenarios in test_loop_prevention.py cover the paths we
thought of. This file covers the ones we did not: it drives randomised review
sequences through the policy and asserts that every single one terminates
within a bounded number of steps.
"""

import random

import pytest

from mawe.graph.policy import (
    APPROVED,
    DEVELOP,
    ERROR,
    FINALIZE,
    ITERATION_CAP,
    NO_PROGRESS,
    OSCILLATION,
    REPEATED_ISSUES,
    UNRESOLVED,
    LoopPolicy,
    issue_signature,
)

POLICY = LoopPolicy()


def state(**kw):
    base = {"iteration": 1, "max_iterations": 5, "verdict": "reject",
            "severity": "major", "seen_hashes": ["h1"], "code_hash": "h1",
            "issue_history": [], "errors": []}
    base.update(kw)
    return base


# ------------------------------------------------------- the four detectors
def test_identical_code_twice_running_is_no_progress():
    d = POLICY.decide(state(seen_hashes=["h1", "h1"], code_hash="h1"))
    assert d.route == FINALIZE and d.reason == NO_PROGRESS


def test_a_version_seen_earlier_is_oscillation():
    d = POLICY.decide(state(seen_hashes=["a", "b", "a"], code_hash="a"))
    assert d.reason == OSCILLATION
    assert "cycling" in d.detail


def test_the_same_complaint_three_times_gives_up():
    sig = issue_signature(["criterion 4 fails"])
    d = POLICY.decide(state(seen_hashes=["a", "b", "c"], code_hash="c",
                            issue_history=[sig, sig, sig]))
    assert d.reason == REPEATED_ISSUES


def test_two_repeats_is_not_yet_enough():
    sig = issue_signature(["criterion 4 fails"])
    d = POLICY.decide(state(seen_hashes=["a", "b"], code_hash="b",
                            issue_history=[sig, sig]))
    assert d.route == DEVELOP


def test_cap_is_the_last_resort():
    d = POLICY.decide(state(iteration=5, seen_hashes=list("abcde"),
                            code_hash="e"))
    assert d.reason == ITERATION_CAP


# ------------------------------------------------------------- precedence
def test_approval_beats_every_detector():
    d = POLICY.decide(state(verdict="approve", severity=None,
                            iteration=99, seen_hashes=["a", "a"],
                            code_hash="a"))
    assert d.reason == APPROVED


def test_error_beats_everything():
    d = POLICY.decide(state(verdict="approve", errors=["pm failed"]))
    assert d.reason == ERROR


def test_no_progress_is_reported_in_preference_to_oscillation():
    """Consecutive repeats are the more specific diagnosis."""
    d = POLICY.decide(state(seen_hashes=["a", "b", "a", "a"], code_hash="a"))
    assert d.reason == NO_PROGRESS


# -------------------------------------------------------- issue signatures
@pytest.mark.parametrize("a,b", [
    (["criterion 4 fails"], ["Criterion 4 Fails"]),
    (["1. criterion 4 fails"], ["criterion 4 fails"]),
    (["2) criterion 4 fails"], ["criterion  4   fails"]),
    (["a", "b"], ["b", "a"]),
])
def test_cosmetic_rewording_is_still_the_same_complaint(a, b):
    assert issue_signature(a) == issue_signature(b)


def test_genuinely_different_complaints_differ():
    assert issue_signature(["criterion 4 fails"]) != \
           issue_signature(["criterion 5 fails"])


def test_empty_issue_list_has_an_empty_signature():
    assert issue_signature([]) == ""
    assert issue_signature(["", "   "]) == ""


def test_an_empty_signature_never_triggers_repeated_issues():
    """Approvals carry no issues; they must not look like a stuck loop."""
    d = POLICY.decide(state(seen_hashes=["a", "b", "c"], code_hash="c",
                            issue_history=["", "", "", ""]))
    assert d.reason != REPEATED_ISSUES


# --------------------------------------------------------- configurability
def test_detectors_can_be_switched_off_individually():
    lenient = LoopPolicy(detect_no_progress=False, detect_oscillation=False,
                         detect_repeated_issues=False)
    d = lenient.decide(state(seen_hashes=["a", "a"], code_hash="a"))
    assert d.route == DEVELOP, "only the cap should remain"
    d2 = lenient.decide(state(iteration=5, seen_hashes=["a", "a"],
                              code_hash="a"))
    assert d2.reason == ITERATION_CAP


def test_blocking_severities_are_configurable():
    strict = LoopPolicy(blocking_severities=("critical", "major", "minor"))
    assert strict.decide(state(severity="minor")).route == DEVELOP
    assert POLICY.decide(state(severity="minor")).reason == APPROVED


# =================================================== randomised stress test
def simulate(rng: random.Random, policy: LoopPolicy, rounds: int = 200):
    """Drive the policy with an adversarial reviewer and developer.

    Returns (steps, reason). Raises if the loop fails to terminate.
    """
    s = {"iteration": 0, "max_iterations": policy.max_iterations,
         "seen_hashes": [], "issue_history": [], "errors": []}

    for step in range(1, rounds + 1):
        s["iteration"] = step
        # developer: sometimes repeats, sometimes cycles, sometimes new code
        mode = rng.choice(["new", "repeat", "cycle"])
        if mode == "repeat" and s["seen_hashes"]:
            digest = s["seen_hashes"][-1]
        elif mode == "cycle" and s["seen_hashes"]:
            digest = rng.choice(s["seen_hashes"])
        else:
            digest = f"h{rng.randrange(10_000)}"
        s["seen_hashes"] = s["seen_hashes"] + [digest]
        s["code_hash"] = digest

        # reviewer: random verdict, severity and complaint set
        s["verdict"] = rng.choices(["reject", "approve"], weights=[95, 5])[0]
        s["severity"] = rng.choice(["critical", "major", "minor", None])
        issues = [f"criterion {rng.randrange(1, 4)} fails"
                  for _ in range(rng.randrange(0, 3))]
        s["issue_history"] = s["issue_history"] + [issue_signature(issues)]
        if rng.random() < 0.01:
            s["errors"] = ["random agent failure"]

        decision = policy.decide(s)
        if decision.terminal:
            return step, decision.reason

    raise AssertionError(
        f"loop did not terminate in {rounds} rounds; state={s}")


@pytest.mark.parametrize("seed", range(40))
def test_randomised_sequences_always_terminate(seed):
    steps, reason = simulate(random.Random(seed), POLICY)
    assert reason in (APPROVED,) + UNRESOLVED
    assert steps <= POLICY.max_iterations


def test_large_stress_sweep_never_exceeds_the_cap():
    """2000 randomised runs; the cap is an absolute bound, not a tendency."""
    rng = random.Random(1234)
    reasons = {}
    worst = 0
    for _ in range(2000):
        steps, reason = simulate(rng, POLICY)
        reasons[reason] = reasons.get(reason, 0) + 1
        worst = max(worst, steps)

    assert worst <= POLICY.max_iterations, f"a run reached {worst} iterations"
    assert sum(reasons.values()) == 2000
    # the sweep should be varied enough to exercise more than one exit
    assert len(reasons) >= 3, f"only saw {reasons}"


@pytest.mark.parametrize("cap", [1, 2, 3, 5, 8, 20])
def test_the_cap_bounds_every_randomised_run(cap):
    policy = LoopPolicy(max_iterations=cap)
    rng = random.Random(cap)
    for _ in range(200):
        steps, _reason = simulate(rng, policy)
        assert steps <= cap


def test_stress_sweep_with_all_detectors_disabled_still_terminates():
    """Worst case: only the hard cap is left."""
    policy = LoopPolicy(detect_no_progress=False, detect_oscillation=False,
                        detect_repeated_issues=False, max_iterations=5)
    rng = random.Random(7)
    for _ in range(500):
        steps, reason = simulate(rng, policy)
        assert steps <= 5
        assert reason in (APPROVED, ITERATION_CAP, ERROR)
