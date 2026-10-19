"""Week 2: the four loop-prevention mechanisms.

`route_after_review` is a pure function of the state, so every branch is tested
here without an LLM.  These are the tests behind the claim that the loop
always terminates.
"""

import pytest

from mawe.graph.workflow import (
    APPROVED,
    ERROR,
    ITERATION_CAP,
    NO_PROGRESS,
    hash_files,
    route_after_review,
    termination_reason,
)

BLOCKING = ("critical", "major")


def state(**kw):
    base = {
        "iteration": 1,
        "max_iterations": 5,
        "verdict": "reject",
        "severity": "major",
        "seen_hashes": ["h1"],
        "code_hash": "h1",
        "errors": [],
    }
    base.update(kw)
    return base


# --------------------------------------------------- mechanism 0: approval
def test_approve_goes_straight_to_finalize():
    s = state(verdict="approve", severity=None)
    assert route_after_review(s, BLOCKING) == "finalize"
    assert termination_reason(s, BLOCKING) == APPROVED


# ----------------------------------------- mechanism 2: severity threshold
@pytest.mark.parametrize("severity", ["minor", None])
def test_non_blocking_severity_approves_with_notes(severity):
    s = state(verdict="reject", severity=severity)
    assert route_after_review(s, BLOCKING) == "finalize"
    assert termination_reason(s, BLOCKING) == APPROVED


@pytest.mark.parametrize("severity", ["critical", "major"])
def test_blocking_severity_sends_it_back_to_the_developer(severity):
    s = state(verdict="reject", severity=severity)
    assert route_after_review(s, BLOCKING) == "develop"


# --------------------------------------- mechanism 3: no-progress detection
def test_repeated_code_hash_exits_the_loop():
    s = state(seen_hashes=["h1", "h1"], code_hash="h1")
    assert route_after_review(s, BLOCKING) == "finalize"
    assert termination_reason(s, BLOCKING) == NO_PROGRESS


def test_changed_code_keeps_iterating():
    s = state(seen_hashes=["h1", "h2"], code_hash="h2")
    assert route_after_review(s, BLOCKING) == "develop"


def test_no_progress_is_checked_before_the_cap():
    """A stuck developer should be caught immediately, not after five rounds."""
    s = state(iteration=2, max_iterations=5,
              seen_hashes=["h1", "h1"], code_hash="h1")
    assert termination_reason(s, BLOCKING) == NO_PROGRESS


# ------------------------------------------- mechanism 1: hard iteration cap
def test_iteration_cap_stops_a_reviewer_that_never_approves():
    s = state(iteration=5, max_iterations=5,
              seen_hashes=["a", "b", "c", "d", "e"], code_hash="e")
    assert route_after_review(s, BLOCKING) == "finalize"
    assert termination_reason(s, BLOCKING) == ITERATION_CAP


def test_below_the_cap_still_iterates():
    s = state(iteration=4, max_iterations=5,
              seen_hashes=["a", "b", "c", "d"], code_hash="d")
    assert route_after_review(s, BLOCKING) == "develop"


@pytest.mark.parametrize("cap", [1, 2, 3, 5, 10])
def test_cap_is_configurable(cap):
    s = state(iteration=cap, max_iterations=cap,
              seen_hashes=[f"h{i}" for i in range(cap)], code_hash=f"h{cap-1}")
    assert route_after_review(s, BLOCKING) == "finalize"


# ------------------------------------------- mechanism 4: fallback on error
def test_agent_error_routes_to_finalize_rather_than_hanging():
    s = state(errors=["product manager produced an invalid specification"])
    assert route_after_review(s, BLOCKING) == "finalize"
    assert termination_reason(s, BLOCKING) == ERROR


# ------------------------------------------------------- the headline claim
def test_every_reachable_state_terminates():
    """Exhaustive sweep: no combination of review outcomes loops forever."""
    for iteration in range(0, 8):
        for severity in ("critical", "major", "minor", None):
            for verdict in ("approve", "reject"):
                for repeated in (True, False):
                    hashes = ["h", "h"] if repeated else ["h1", "h2"]
                    s = state(iteration=iteration, max_iterations=5,
                              verdict=verdict, severity=severity,
                              seen_hashes=hashes, code_hash=hashes[-1])
                    route = route_after_review(s, BLOCKING)
                    assert route in ("develop", "finalize")
                    if route == "develop":
                        # continuing is only allowed while there is headroom
                        assert iteration < 5
                        assert verdict == "reject"
                        assert severity in BLOCKING
                        assert not repeated


# ----------------------------------------------------------------- hashing
def test_hash_is_order_independent_and_content_sensitive():
    a = [{"path": "a.py", "content": "x"}, {"path": "b.py", "content": "y"}]
    b = [{"path": "b.py", "content": "y"}, {"path": "a.py", "content": "x"}]
    c = [{"path": "a.py", "content": "x"}, {"path": "b.py", "content": "z"}]
    assert hash_files(a) == hash_files(b)
    assert hash_files(a) != hash_files(c)


def test_hash_distinguishes_path_from_content():
    """Guards against a naive concatenation where moving text between the
    path and the body produces the same digest."""
    a = [{"path": "ab", "content": "c"}]
    b = [{"path": "a", "content": "bc"}]
    assert hash_files(a) != hash_files(b)
