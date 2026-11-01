"""Week 5: the Code Reviewer, and the guarantee that evidence beats opinion.

The point of these tests is that the Reviewer's verdict is not simply whatever
the model said. Executable acceptance checks are run in the sandbox first, and
where the model disagrees with what the program actually did, the measurement
wins.
"""

import json

import pytest

from mawe.agents.checks import (
    AcceptanceCheck,
    parse_checks,
    run_check,
    run_checks,
    summarise,
)
from mawe.agents.reviewer import ReviewerAgent, max_severity, normalise_severity
from mawe.config import Settings
from mawe.llm import MockProvider
from mawe.sample_code import (
    TEMPERATURE_MAIN,
    TEMPERATURE_MAIN_UNROUNDED,
    TEMPERATURE_SPEC,
)

LIVE = Settings(max_iterations=5, sandbox_timeout_s=15)
NO_SANDBOX = Settings(max_iterations=5, sandbox_timeout_s=0)


def files_for(code):
    return [{"path": "src/main.py", "language": "python", "content": code}]


def state_for(code, spec=TEMPERATURE_SPEC):
    return {
        "spec": json.dumps(spec),
        "spec_json": spec,
        "acceptance_criteria": spec["acceptance_criteria"],
        "language": "python",
        "files": files_for(code),
        "warnings": [],
    }


def review_saying(verdict, severity, issues=(), passed=0, failed=0):
    return {"reviewer": [json.dumps({
        "verdict": verdict, "severity": severity, "issues": list(issues),
        "tests_passed": passed, "tests_failed": failed})]}


# ===================================================== executable checks
def test_checks_parse_from_a_specification():
    checks = parse_checks(TEMPERATURE_SPEC["checks"])
    assert len(checks) == 3
    assert checks[0].criterion == 1
    assert checks[0].argv == ["100", "C"]
    assert checks[2].expect_exit == 1


def test_a_passing_check_passes():
    check = AcceptanceCheck(criterion=1, argv=["100", "C"],
                            expect_stdout="212.0")
    result = run_check(files_for(TEMPERATURE_MAIN), check)
    assert result.passed


def test_a_failing_check_reports_what_it_actually_got():
    check = AcceptanceCheck(criterion=2, argv=["100", "F"],
                            expect_stdout="37.8")
    result = run_check(files_for(TEMPERATURE_MAIN_UNROUNDED), check)
    assert not result.passed
    assert "37.777" in result.reason
    assert "37.8" in result.reason


@pytest.mark.parametrize("match,expected,ok", [
    ("exact", "212.0", True),
    ("exact", "212", False),
    ("contains", "212", True),
    ("regex", r"^\d+\.\d$", True),
    ("regex", r"^[a-z]+$", False),
])
def test_match_modes(match, expected, ok):
    check = AcceptanceCheck(criterion=1, argv=["100", "C"],
                            expect_stdout=expected, match=match)
    assert run_check(files_for(TEMPERATURE_MAIN), check).passed is ok


def test_exit_code_only_check():
    check = AcceptanceCheck(criterion=3, argv=["10", "K"], expect_exit=1)
    assert run_check(files_for(TEMPERATURE_MAIN), check).passed


def test_summary_counts_and_names_the_failing_criteria():
    results = run_checks(files_for(TEMPERATURE_MAIN_UNROUNDED),
                         parse_checks(TEMPERATURE_SPEC["checks"]))
    summary = summarise(results)
    assert summary["tests_passed"] == 2
    assert summary["tests_failed"] == 1
    assert summary["failed_criteria"] == [2]
    assert "FAIL" in summary["evidence"]


# ============================================== the reconciliation rules
def test_reviewer_cannot_approve_code_that_fails_a_check():
    """The headline guarantee. The model says approve; the program disagrees."""
    provider = MockProvider(review_saying("approve", "minor"))
    update = ReviewerAgent(provider, LIVE).run(
        state_for(TEMPERATURE_MAIN_UNROUNDED))

    assert update["verdict"] == "reject"
    assert update["severity"] in ("major", "critical")
    assert update["tests_failed"] == 1
    assert any("criteria 2" in i for i in update["issues"])
    assert any("overridden by the sandbox" in w for w in update["warnings"])


def test_reviewer_cannot_block_on_trivia_once_every_check_passes():
    """The other failure mode: an endless loop over style."""
    provider = MockProvider(review_saying(
        "reject", "major", ["variable name 'c_to_f' could be clearer"]))
    update = ReviewerAgent(provider, LIVE).run(state_for(TEMPERATURE_MAIN))

    assert update["tests_failed"] == 0
    assert update["severity"] == "minor"      # downgraded, so the loop ends
    assert any("downgraded to minor" in w for w in update["warnings"])


def test_counts_come_from_the_sandbox_not_from_the_model():
    provider = MockProvider(review_saying("approve", "minor",
                                          passed=999, failed=0))
    update = ReviewerAgent(provider, LIVE).run(state_for(TEMPERATURE_MAIN))
    assert update["tests_passed"] == 3        # not 999
    assert update["tests_failed"] == 0


def test_genuine_approval_is_left_alone():
    provider = MockProvider(review_saying("approve", "minor"))
    update = ReviewerAgent(provider, LIVE).run(state_for(TEMPERATURE_MAIN))
    assert update["verdict"] == "approve"
    assert update["tests_failed"] == 0
    assert not any("overridden" in w for w in update["warnings"])


def test_a_crash_is_escalated_to_critical():
    broken = "import sys\nraise RuntimeError('boom')\n"
    provider = MockProvider(review_saying("approve", "minor"))
    update = ReviewerAgent(provider, LIVE).run(state_for(broken))
    assert update["verdict"] == "reject"
    assert update["severity"] == "critical"


def test_malformed_model_output_falls_back_to_the_evidence():
    provider = MockProvider({"reviewer": ["I think it looks fine honestly"]})
    update = ReviewerAgent(provider, LIVE).run(
        state_for(TEMPERATURE_MAIN_UNROUNDED))
    assert update["verdict"] == "reject"
    assert update["tests_failed"] == 1
    assert any("malformed" in w for w in update["warnings"])


def test_malformed_output_with_passing_checks_still_approves():
    provider = MockProvider({"reviewer": ["looks good to me"]})
    update = ReviewerAgent(provider, LIVE).run(state_for(TEMPERATURE_MAIN))
    assert update["verdict"] == "approve"


def test_evidence_is_included_in_the_prompt_sent_to_the_model():
    captured = []

    class Capturing(MockProvider):
        def complete(self, system, user, **kw):
            captured.append(user)
            return super().complete(system, user, **kw)

    provider = Capturing(review_saying("reject", "major"))
    ReviewerAgent(provider, LIVE).run(state_for(TEMPERATURE_MAIN_UNROUNDED))
    prompt = captured[0]
    assert "SANDBOX EXECUTION EVIDENCE" in prompt
    assert "Criteria proven to fail: 2" in prompt


def test_without_a_sandbox_the_model_verdict_stands():
    """Sandbox disabled: no evidence, so no override. The engine degrades to
    model judgement rather than refusing to run."""
    provider = MockProvider(review_saying("approve", "minor"))
    update = ReviewerAgent(provider, NO_SANDBOX).run(
        state_for(TEMPERATURE_MAIN_UNROUNDED))
    assert update["verdict"] == "approve"


def test_spec_without_checks_still_reviews():
    spec = {k: v for k, v in TEMPERATURE_SPEC.items() if k != "checks"}
    provider = MockProvider(review_saying("reject", "major", ["criterion 2"]))
    update = ReviewerAgent(provider, LIVE).run(
        state_for(TEMPERATURE_MAIN_UNROUNDED, spec))
    assert update["verdict"] == "reject"
    assert update["severity"] == "major"


# ------------------------------------------------------------- severity
@pytest.mark.parametrize("raw,verdict,expected", [
    ("critical", "reject", "critical"),
    ("Blocker", "reject", "critical"),
    ("moderate", "reject", "major"),
    ("nit", "reject", "minor"),
    (None, "reject", "major"),
    (None, "approve", "minor"),
    ("nonsense", "reject", "major"),
])
def test_severity_normalisation(raw, verdict, expected):
    assert normalise_severity(raw, verdict) == expected


def test_max_severity_picks_the_worst():
    assert max_severity("minor", "critical", "major") == "critical"
    assert max_severity("minor", None) == "minor"
    assert max_severity(None, None) is None


# ------------------------------------------- check coverage bounds the override
def test_downgrade_only_applies_when_every_criterion_has_a_check():
    """Evidence can only override where evidence exists.

    The temperature spec has a check per criterion, so a blocking reject on
    passing code is safely downgraded. A spec with uncovered criteria must
    not be: the reviewer may be right about the one nobody tested.
    """
    partial = dict(TEMPERATURE_SPEC)
    partial["acceptance_criteria"] = TEMPERATURE_SPEC["acceptance_criteria"] + [
        "the program prints usage text when given no arguments"]
    # no check added for criterion 4

    provider = MockProvider(review_saying(
        "reject", "major", ["criterion 4 fails: no usage text"]))
    update = ReviewerAgent(provider, LIVE).run(
        state_for(TEMPERATURE_MAIN, partial))

    assert update["tests_failed"] == 0, "the three real checks still pass"
    assert update["severity"] == "major", "an uncovered criterion can block"
    assert any("have no check" in w for w in update["warnings"])


def test_full_coverage_still_downgrades():
    provider = MockProvider(review_saying("reject", "major", ["style nit"]))
    update = ReviewerAgent(provider, LIVE).run(state_for(TEMPERATURE_MAIN))
    assert update["severity"] == "minor"
    assert any("every criterion has an executable check" in w
               for w in update["warnings"])
