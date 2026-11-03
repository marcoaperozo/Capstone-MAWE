"""The documentation must not contradict the code.

Every error found in the final audit of this project was the same error: a
number written by hand into a document, correct when it was written, wrong
once the code moved. It happened to the test count three times, to the
compression figure once, and to the list of termination mechanisms once.

Prose cannot be checked automatically, but the specific things that drifted
can be, so they are. These tests are cheap - they read files and compare them
to values computed from the code - and they fail the moment a document starts
lying.

The rule they enforce is: **a figure that changes with the code belongs in a
generated document, not a hand-written one.** `docs/reports/FINAL-REPORT.md`
is generated from `findings.json` and may quote anything; the hand-written
guides may not quote a total test count at all.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Documents a person edits by hand. These describe the current state of the
#: project, so they must not contradict it.
HAND_WRITTEN = [
    "README.md",
    "docs/DEMO-GUIDE.md",
    "docs/architecture.md",
    "docs/results/README.md",
    "docs/SHOW-YOUR-PROFESSOR.md",
]

#: Generated from measurements; allowed to quote any figure.
GENERATED = ["docs/reports/FINAL-REPORT.md", "docs/reports/ABSTRACT.md"]

#: A verbatim record of the original proposal, and a script for a talk that
#: was already given. Neither describes the code as it stands now.
HISTORICAL = ["docs/MAWE-CONTEXT.md"]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def findings():
    path = ROOT / "docs" / "reports" / "findings.json"
    if not path.exists():
        pytest.skip("findings.json not generated; run week12_final_check.py")
    return json.loads(path.read_text(encoding="utf-8"))


# ===================================================== the count that drifted
@pytest.mark.parametrize("name", HAND_WRITTEN)
def test_no_hand_written_doc_states_a_total_test_count(name):
    """The figure that went wrong three times.

    A hand-written guide may say "the full suite"; it may not say "427
    tests", because the suite grows and the sentence does not.
    """
    text = read(name)
    offenders = []
    for match in re.finditer(r"(\d[\d,]{2,6})\s+(?:automated\s+)?tests?\b",
                             text):
        count = int(match.group(1).replace(",", ""))
        # the benchmark's 181 hidden tests are a property of the benchmark,
        # not of the suite, and do not change when a unit test is added
        if count == 181:
            continue
        line = text[:match.start()].count("\n") + 1
        offenders.append(f"{name}:{line} says {match.group(0)!r}")
    assert not offenders, (
        "hand-written docs must not hard-code a suite-wide test count:\n  "
        + "\n  ".join(offenders))


def test_the_generated_report_states_the_measured_count(findings):
    text = read(GENERATED[0])
    expected = findings["tests"]["total"]
    assert f"{expected} automated tests" in text, (
        f"the generated report should quote {expected}; regenerate it with "
        f"docs/reports/build_final_report.py")


# ===================================================== benchmark figures
def test_documented_benchmark_shape_matches_the_code():
    from mawe.bench import composition

    counts = composition()
    for name in HAND_WRITTEN + GENERATED:
        text = read(name)
        if "hidden test" not in text:
            continue
        for match in re.finditer(r"(\d+)\s+hidden tests", text):
            assert int(match.group(1)) == counts["tests"], (
                f"{name} says {match.group(0)!r}, the suite has "
                f"{counts['tests']}")


def test_documented_task_counts_match_the_code():
    from mawe.bench import composition

    counts = composition()
    for name in HAND_WRITTEN + GENERATED:
        for match in re.finditer(r"(\d+) tasks — (\d+) easy, (\d+) "
                                 r"medium, (\d+) hard", read(name)):
            total, easy, medium, hard = (int(g) for g in match.groups())
            assert (total, easy, medium, hard) == (
                counts["tasks"], counts["easy"], counts["medium"],
                counts["hard"]), f"{name}: {match.group(0)!r}"


# ===================================================== claims about the code
def test_no_document_claims_code_runs_in_docker():
    """Nothing executes in Docker, and a presentation script once said it did.

    That line would have been read aloud to an examiner. Docker is the stated
    hardening target and was never implemented; every result reports
    `isolation: "subprocess"`.
    """
    from mawe.sandbox.runner import Sandbox

    with Sandbox([{"path": "src/main.py", "language": "python",
                   "content": "print(1)\n"}]) as box:
        assert box.run()["isolation"] == "subprocess"

    claims = re.compile(
        r"(?:runs?|execut\w+|sandboxed?)[^.\n]{0,40}\bin(?:side)? a docker",
        re.IGNORECASE)
    for name in HAND_WRITTEN + GENERATED + ["docs/PRESENTATION-SCRIPT.md"]:
        text = read(name)
        found = claims.search(text)
        assert not found, f"{name} claims execution in Docker: {found.group(0)!r}"


def test_the_termination_reasons_documented_are_the_ones_implemented():
    """A guide said four mechanisms while the policy had five."""
    from mawe.graph.policy import APPROVED, UNRESOLVED

    implemented = {APPROVED, *UNRESOLVED}
    assert implemented == {"approved", "iteration_cap", "no_progress",
                           "oscillation", "repeated_issues", "error"}

    guide = read("docs/DEMO-GUIDE.md")
    for reason in ("iteration cap", "no progress", "oscillation",
                   "repeated issues"):
        assert reason.lower() in guide.lower(), \
            f"the demo guide does not mention the {reason!r} exit"


def test_the_real_providers_are_still_described_as_unrun():
    """If a live sweep is ever run, this test should be deleted - but it must
    not pass silently while the claim is still true and undocumented."""
    for name in ("README.md", "docs/architecture.md"):
        text = read(name).lower()
        assert ("never" in text and "api" in text), (
            f"{name} should state that the real adapters have not been run "
            f"against a live API")


# ===================================================== status tables
def test_no_live_doc_still_calls_a_finished_phase_unbuilt():
    stale = re.compile(r"not built|\bnext\b\s*\|", re.IGNORECASE)
    for name in HAND_WRITTEN:
        text = read(name)
        for match in stale.finditer(text):
            line = text[:match.start()].count("\n") + 1
            context = text.splitlines()[line - 1]
            # "next" is fine in prose; the status *column* of a table is not
            assert not context.strip().startswith("|"), (
                f"{name}:{line} still marks a delivered phase as pending: "
                f"{context.strip()[:90]!r}")


# ================================================= headline figures
def test_the_generated_documents_quote_the_current_figures(findings):
    """Catches a document that was not regenerated after the numbers moved.

    An earlier version of this test tried to find every percentage in every
    document and validate it. That was the wrong tool: it could not tell a
    measured result from a target, so it flagged H5's "at least 40%"
    threshold as a stale measurement, and its number regex split "91.4%" into
    "1.4%". Prose cannot be parsed reliably, so this checks the one thing
    that can be: the generated documents must contain the current figures
    somewhere.
    """
    mutation = findings["benchmark"]["mutation_score"] * 100
    reduction = findings["compression"]["best_reduction"] * 100

    expected = {
        "docs/reports/FINAL-REPORT.md": [
            f"{mutation:.1f}%", f"{reduction:.1f}%",
            f"{findings['tests']['total']} automated tests",
        ],
        "docs/reports/ABSTRACT.md": [
            f"{mutation:.0f}%", f"{reduction:.0f}%",
            f"{findings['benchmark']['hidden_tests']} hidden tests",
        ],
    }
    for name, figures in expected.items():
        text = read(name)
        missing = [f for f in figures if f not in text]
        assert not missing, (
            f"{name} is missing {missing}; regenerate it from findings.json")


# ================================================= the demo runbook
def test_every_script_the_runbook_names_exists():
    """A demo that opens with a missing file is the worst possible start."""
    runbook = read("docs/SHOW-YOUR-PROFESSOR.md")
    named = set(re.findall(r"python (scripts/\S+?\.py)", runbook))
    assert named, "the runbook should name at least one script"
    missing = [name for name in named if not (ROOT / name).exists()]
    assert not missing, f"the runbook calls scripts that do not exist: {missing}"


def test_the_runbook_names_the_gap_up_front():
    """The one thing the presenter has to say before being asked."""
    runbook = read("docs/SHOW-YOUR-PROFESSOR.md")
    opening = runbook[:runbook.index("## 1.")].lower()
    assert "real" in opening and "model" in opening, \
        "the runbook must state the live-model gap in its opening section"


def test_the_runbook_files_it_hands_over_exist():
    runbook = read("docs/SHOW-YOUR-PROFESSOR.md")
    for path in re.findall(r"`(docs/[\w./-]+\.(?:pdf|md))`", runbook):
        assert (ROOT / path).exists(), f"the runbook offers {path}, missing"
