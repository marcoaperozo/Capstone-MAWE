"""Week 4: the Developer output contract and multi-file generation."""

import json

import pytest

from mawe.agents.developer import (
    DeveloperAgent,
    DeveloperError,
    find_placeholders,
    language_for,
    parse_files,
)
from mawe.config import Settings
from mawe.graph.workflow import hash_files
from mawe.llm import MockProvider
from mawe.sample_code import RUNNABLE_SAMPLES, dev_script

SETTINGS = Settings(max_iterations=5, sandbox_timeout_s=0)


def files_json(*files):
    return json.dumps({"files": list(files)})


def f(path="src/main.py", content="print('hi')\n", language="python"):
    return {"path": path, "language": language, "content": content}


# ------------------------------------------------------------- parsing
def test_parses_the_files_contract():
    files = parse_files(files_json(f(), f("src/util.py", "X = 1\n")))
    assert [x["path"] for x in files] == ["src/main.py", "src/util.py"]
    assert files[1]["content"] == "X = 1\n"


def test_infers_language_from_extension():
    files = parse_files(json.dumps({"files": [
        {"path": "src/app.js", "content": "console.log(1)"},
        {"path": "src/main.py", "content": "print(1)"},
    ]}))
    assert files[0]["language"] == "javascript"
    assert files[1]["language"] == "python"


@pytest.mark.parametrize("path,expected", [
    ("a.py", "python"), ("a.js", "javascript"), ("a.mjs", "javascript"),
    ("a.json", "json"), ("a.md", "markdown"), ("weird", "python"),
])
def test_language_for(path, expected):
    assert language_for(path) == expected


def test_falls_back_to_fenced_code_blocks():
    """A model that ignores the JSON contract still produces usable output."""
    text = "Here you go:\n\n```python\nprint('hello')\n```"
    files = parse_files(text, expected=["src/main.py"])
    assert files[0]["path"] == "src/main.py"
    assert "print('hello')" in files[0]["content"]


def test_empty_response_is_rejected():
    with pytest.raises(DeveloperError):
        parse_files("I'm not sure how to do that.")


def test_empty_file_content_is_rejected():
    with pytest.raises(DeveloperError, match="empty content"):
        parse_files(files_json(f(content="   ")))


def test_missing_path_is_rejected():
    with pytest.raises(DeveloperError, match="no path"):
        parse_files(json.dumps({"files": [{"content": "x"}]}))


def test_duplicate_paths_are_rejected():
    with pytest.raises(DeveloperError, match="duplicate"):
        parse_files(files_json(f(), f()))


# ------------------------------------------------- strict spec adherence
@pytest.mark.parametrize("marker", [
    "# ... rest of the file",
    "# rest of the code unchanged",
    "// your code here",
    "# TODO: implement",
    "... (unchanged)",
])
def test_placeholder_content_is_rejected(marker):
    """A truncated file is worse than no file: it looks runnable and is not."""
    with pytest.raises(DeveloperError, match="placeholder"):
        parse_files(files_json(f(content=f"def run():\n    {marker}\n")))


def test_find_placeholders_is_case_insensitive():
    assert find_placeholders("# TODO: Implement this")
    assert not find_placeholders("def implement(): return 1")


def test_developer_must_produce_every_file_the_spec_asks_for():
    provider = MockProvider({"developer": [files_json(f("src/main.py"))] * 3})
    agent = DeveloperAgent(provider, SETTINGS)
    update = agent.run({
        "spec": "{}",
        "spec_json": {"files": ["src/main.py", "src/storage.py"]},
        "language": "python",
    })
    assert update["errors"]
    assert "src/storage.py" in update["errors"][0]


def test_multi_file_output_is_accepted_when_complete():
    files = RUNNABLE_SAMPLES["Expression parser and evaluator"]["files"]
    provider = MockProvider(dev_script("Expression parser and evaluator"))
    update = DeveloperAgent(provider, SETTINGS).run({
        "spec": "{}",
        "spec_json": {"files": [x["path"] for x in files]},
        "language": "python",
    })
    assert "errors" not in update
    assert len(update["files"]) == 3


# ---------------------------------------------------------- repair round
def test_one_repair_round_recovers_from_bad_output():
    provider = MockProvider({"developer": ["not json at all", files_json(f())]})
    update = DeveloperAgent(provider, SETTINGS).run(
        {"spec": "{}", "spec_json": {}, "language": "python"})
    assert "errors" not in update
    assert provider.call_count("developer") == 2


def test_persistent_bad_output_is_recorded_not_raised():
    provider = MockProvider({"developer": ["nope", "still nope", "nope"]})
    update = DeveloperAgent(provider, SETTINGS).run(
        {"spec": "{}", "spec_json": {}, "language": "python"})
    assert update["errors"]
    assert update["iteration"] == 1
    assert provider.call_count("developer") == 2


# ------------------------------------------------- iteration and hashing
def test_iteration_increments_and_hash_is_recorded():
    provider = MockProvider({"developer": [files_json(f())]})
    update = DeveloperAgent(provider, SETTINGS).run(
        {"spec": "{}", "spec_json": {}, "language": "python",
         "iteration": 2, "seen_hashes": ["old"]})
    assert update["iteration"] == 3
    assert update["code_hash"] == hash_files(update["files"])
    assert update["seen_hashes"] == ["old", update["code_hash"]]


def test_identical_output_produces_the_same_hash_twice():
    """This is what the no-progress exit condition keys on."""
    hashes = []
    for _ in range(2):
        provider = MockProvider({"developer": [files_json(f())]})
        update = DeveloperAgent(provider, SETTINGS).run(
            {"spec": "{}", "spec_json": {}, "language": "python"})
        hashes.append(update["code_hash"])
    assert hashes[0] == hashes[1]


# --------------------------------------------------------- review prompt
def test_review_feedback_is_passed_back_with_numbered_items():
    captured = []

    class Capturing(MockProvider):
        def complete(self, system, user, **kw):
            captured.append(user)
            return super().complete(system, user, **kw)

    provider = Capturing({"developer": [files_json(f())]})
    DeveloperAgent(provider, SETTINGS).run({
        "spec": "SPEC HERE",
        "spec_json": {},
        "language": "python",
        "issues": ["criterion 4 fails: no self-collision check",
                   "criterion 5 fails: score never printed"],
        "severity": "major",
        "files": [f(content="old code\n")],
    })

    prompt = captured[0]
    assert "1. criterion 4 fails" in prompt
    assert "2. criterion 5 fails" in prompt
    assert "old code" in prompt, "the developer needs its previous version"
    assert "Severity: major" in prompt


def test_first_iteration_prompt_has_no_feedback_section():
    captured = []

    class Capturing(MockProvider):
        def complete(self, system, user, **kw):
            captured.append(user)
            return super().complete(system, user, **kw)

    provider = Capturing({"developer": [files_json(f())]})
    DeveloperAgent(provider, SETTINGS).run(
        {"spec": "SPEC", "spec_json": {}, "language": "python"})
    assert "REJECTED" not in captured[0]
