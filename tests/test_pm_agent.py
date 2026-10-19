"""Week 3: the Product Manager output contract.

Milestone: the PM produces a valid specification on all five sample prompts,
and invalid output is either repaired or recorded as an error - never passed
downstream to the Developer.
"""

import json

import pytest

from mawe.agents.parsing import ParseError, extract_json
from mawe.agents.product_manager import (
    MAX_CRITERIA,
    MIN_CRITERIA,
    ProductManagerAgent,
    Specification,
    parse_specification,
    validate,
)
from mawe.config import Settings
from mawe.llm import MockProvider
from mawe.samples import SAMPLE_PROMPTS, pm_script

SETTINGS = Settings(max_iterations=5, sandbox_timeout_s=0)


def good_spec(**overrides):
    data = {
        "summary": "A terminal snake game.",
        "language": "python",
        "files": ["src/main.py"],
        "features": ["grid rendering", "arrow key movement"],
        "constraints": ["standard library only"],
        "acceptance_criteria": [
            "the program runs without raising an exception",
            "the snake grows by one segment per food eaten",
            "colliding with a wall ends the game",
        ],
    }
    data.update(overrides)
    return data


# ------------------------------------------------------- the five samples
@pytest.mark.parametrize("sample", SAMPLE_PROMPTS, ids=lambda s: s["name"])
def test_pm_produces_a_valid_spec_for_every_sample_prompt(sample):
    agent = ProductManagerAgent(MockProvider(pm_script(sample["spec"])), SETTINGS)
    update = agent.run({"prompt": sample["prompt"], "language": sample["language"]})

    assert "errors" not in update, update.get("errors")
    spec = parse_specification(update["spec"])
    assert validate(spec) == []
    assert spec.language == sample["language"]
    assert MIN_CRITERIA <= len(spec.acceptance_criteria) <= MAX_CRITERIA
    assert update["acceptance_criteria"] == spec.acceptance_criteria


@pytest.mark.parametrize("sample", SAMPLE_PROMPTS, ids=lambda s: s["name"])
def test_pm_repairs_a_malformed_first_answer(sample):
    """One repair round, with the violations fed back, recovers a valid spec."""
    provider = MockProvider(pm_script(sample["spec"], malformed_first=True))
    agent = ProductManagerAgent(provider, SETTINGS)
    update = agent.run({"prompt": sample["prompt"], "language": sample["language"]})

    assert "errors" not in update
    assert provider.call_count("product_manager") == 2
    assert validate(parse_specification(update["spec"])) == []


# --------------------------------------------------------------- validator
def test_a_well_formed_spec_has_no_violations():
    assert validate(Specification(**good_spec())) == []


@pytest.mark.parametrize("overrides,expected", [
    ({"summary": "   "}, "summary is empty"),
    ({"language": "rust"}, "not one of"),
    ({"files": []}, "files is empty"),
    ({"files": ["/etc/passwd"]}, "must be relative"),
    ({"files": ["../escape.py"]}, "must be relative"),
    ({"features": []}, "features is empty"),
    ({"acceptance_criteria": ["only one"]}, "at least"),
    ({"acceptance_criteria": [f"criterion number {i} is observable"
                              for i in range(MAX_CRITERIA + 1)]}, "at most"),
    ({"acceptance_criteria": ["it runs", "ok", "fine"]}, "too short"),
])
def test_validator_catches_contract_violations(overrides, expected):
    problems = validate(Specification(**good_spec(**overrides)))
    assert problems, f"expected a violation for {overrides}"
    assert any(expected in p for p in problems), problems


def test_path_traversal_is_rejected_before_it_reaches_the_sandbox():
    """The Developer writes these paths to disk, so the PM must not emit
    anything that escapes the project directory."""
    for bad in ["/abs/path.py", "../../etc/passwd", "src/../../x.py"]:
        problems = validate(Specification(**good_spec(files=[bad])))
        assert any("relative" in p for p in problems), bad


# ----------------------------------------------------------------- parsing
def test_parses_bare_json():
    spec = parse_specification(json.dumps(good_spec()))
    assert spec.summary.startswith("A terminal")


def test_parses_json_wrapped_in_prose_and_fences():
    text = ("Sure! Here is the specification:\n\n```json\n"
            + json.dumps(good_spec()) + "\n```\n\nLet me know if you want changes.")
    assert parse_specification(text).language == "python"


def test_parses_criteria_given_as_objects():
    """Models sometimes emit [{'id': 1, 'text': '...'}] instead of strings."""
    data = good_spec()
    data["acceptance_criteria"] = [
        {"id": 1, "text": "the program runs without raising an exception"},
        {"id": 2, "text": "the snake grows by one segment per food eaten"},
        {"id": 3, "text": "colliding with a wall ends the game"},
    ]
    spec = parse_specification(json.dumps(data))
    assert spec.acceptance_criteria[0].startswith("the program runs")
    assert validate(spec) == []


def test_language_is_normalised_to_lowercase():
    assert parse_specification(json.dumps(good_spec(language="Python"))).language == "python"


@pytest.mark.parametrize("text", ["", "   ", "I cannot help with that.", "not json {"])
def test_unparseable_output_raises(text):
    with pytest.raises(ParseError):
        parse_specification(text)


def test_extract_json_prefers_the_fenced_block():
    text = '{"decoy": 1}\n```json\n{"real": 2}\n```'
    assert extract_json(text) == {"real": 2}


# -------------------------------------------------------- failure handling
def test_persistently_invalid_output_is_recorded_as_an_error_not_an_exception():
    """After the repair round the PM gives up cleanly, so the graph can route
    to finalize instead of crashing the run."""
    broken = json.dumps(good_spec(acceptance_criteria=["too few"]))
    provider = MockProvider({"product_manager": [broken, broken, broken]})
    update = ProductManagerAgent(provider, SETTINGS).run(
        {"prompt": "anything", "language": "python"})

    assert "spec" not in update
    assert update["errors"]
    assert "could not produce a valid specification" in update["errors"][0]
    assert provider.call_count("product_manager") == 2  # original + one repair


def test_repair_prompt_tells_the_model_what_was_wrong():
    captured = []

    class Capturing(MockProvider):
        def complete(self, system, user, **kw):
            captured.append(user)
            return super().complete(system, user, **kw)

    broken = json.dumps(good_spec(acceptance_criteria=["too few"]))
    provider = Capturing({"product_manager": [broken, json.dumps(good_spec())]})
    ProductManagerAgent(provider, SETTINGS).run(
        {"prompt": "anything", "language": "python"})

    assert len(captured) == 2
    assert "violated the contract" in captured[1]
    assert "at least" in captured[1]


# ------------------------------------------------------- developer hand-off
def test_spec_renders_a_numbered_brief_for_the_developer():
    spec = Specification(**good_spec())
    brief = spec.as_developer_brief()
    assert "ACCEPTANCE CRITERIA" in brief
    assert "1. the program runs" in brief
    assert "src/main.py" in brief
