"""Week 4: the sandbox executes generated code without trusting it."""

import os
import tempfile

import pytest

from mawe.sandbox.runner import (
    MAX_OUTPUT_CHARS,
    pick_entry_point,
    run_files,
    write_files,
)
from mawe.sample_code import RUNNABLE_SAMPLES


def py(content, path="src/main.py"):
    return [{"path": path, "language": "python", "content": content}]


# ------------------------------------------------- the milestone itself
@pytest.mark.parametrize("name", list(RUNNABLE_SAMPLES))
def test_generated_programs_actually_run(name):
    """'The Developer agent generates runnable code' - measured, not asserted."""
    sample = RUNNABLE_SAMPLES[name]
    for check in sample["checks"]:
        result = run_files(sample["files"], "python", timeout_s=15,
                           argv=check["argv"], stdin=check["stdin"])
        assert result["exit_code"] == 0, result["stderr"]
        assert result["stdout"].strip() == check["expect"], (
            f"{name} {check['argv']}: got {result['stdout']!r}")


def test_multi_file_project_resolves_its_own_imports():
    sample = RUNNABLE_SAMPLES["Expression parser and evaluator"]
    assert len(sample["files"]) == 3
    result = run_files(sample["files"], "python", timeout_s=15,
                       argv=["2 + 3 * 4"])
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "14"


# ----------------------------------------------------------- containment
def test_a_crash_is_a_result_not_an_exception():
    result = run_files(py("raise ValueError('boom')\n"), "python", timeout_s=10)
    assert result["exit_code"] != 0
    assert "ValueError" in result["stderr"]
    assert result["timed_out"] is False


def test_an_infinite_loop_is_killed_by_the_timeout():
    result = run_files(py("while True:\n    pass\n"), "python", timeout_s=2)
    assert result["timed_out"] is True
    assert "killed after 2s" in result["stderr"]


def test_nonzero_exit_is_reported():
    result = run_files(py("import sys\nsys.exit(3)\n"), "python", timeout_s=10)
    assert result["exit_code"] == 3


def test_huge_output_is_truncated():
    result = run_files(py("print('x' * 500000)\n"), "python", timeout_s=15)
    assert len(result["stdout"]) <= MAX_OUTPUT_CHARS + 200
    assert "truncated" in result["stdout"]


def test_code_runs_in_a_throwaway_directory():
    """Files the program writes must not land in the project."""
    result = run_files(
        py("import os\nopen('side_effect.txt','w').write('x')\n"
           "print(os.path.abspath('side_effect.txt'))\n"),
        "python", timeout_s=10)
    assert result["exit_code"] == 0
    leaked = result["stdout"].strip()
    assert not os.path.exists(leaked), "sandbox directory was not cleaned up"
    assert not os.path.exists("side_effect.txt")


@pytest.mark.parametrize("bad", ["../escape.py", "/abs.py", "src/../../x.py"])
def test_paths_that_escape_the_sandbox_are_refused(bad):
    with tempfile.TemporaryDirectory() as directory:
        with pytest.raises(ValueError, match="escapes the sandbox"):
            write_files([{"path": bad, "language": "python", "content": "x=1"}],
                        directory)


def test_nested_paths_inside_the_sandbox_are_allowed():
    with tempfile.TemporaryDirectory() as directory:
        written = write_files(
            [{"path": "a/b/c.py", "language": "python", "content": "x=1"}],
            directory)
        assert os.path.exists(written[0])


# --------------------------------------------------------- entry points
@pytest.mark.parametrize("paths,expected", [
    (["src/main.py"], "src/main.py"),
    (["main.py"], "main.py"),
    (["src/util.py", "src/main.py"], "src/main.py"),
    (["src/util.py"], "src/util.py"),           # only candidate
])
def test_entry_point_selection(paths, expected):
    files = [{"path": p, "language": "python", "content": ""} for p in paths]
    assert pick_entry_point(files, "python") == expected


def test_no_entry_point_is_reported_rather_than_crashing():
    result = run_files([{"path": "README.md", "language": "markdown",
                         "content": "# hi"}], "python", timeout_s=5)
    assert result["entry_point"] is None
    assert "no python entry point" in result["stderr"]


def test_empty_file_list_is_handled():
    result = run_files([], "python", timeout_s=5)
    assert result["exit_code"] is None
    assert "no files" in result["stderr"]


def test_stdin_is_delivered_to_the_program():
    result = run_files(py("import sys\nprint(sys.stdin.read().upper())\n"),
                       "python", timeout_s=10, stdin="hello")
    assert result["stdout"].strip() == "HELLO"


# --------------------------------------------- Sandbox: one project, many runs
def test_a_sandbox_runs_the_same_project_many_times():
    """Week 9 added this so the benchmark does not re-write a project once per
    hidden test; the point is that repeated runs see the same files."""
    from mawe.sandbox.runner import Sandbox

    source = "import sys\nprint(len(sys.argv) - 1)\n"
    with Sandbox(py(source), language="python", timeout_s=10) as box:
        assert box.usable
        first = box.run(argv=["a"])
        second = box.run(argv=["a", "b", "c"])
    assert first["stdout"].strip() == "1"
    assert second["stdout"].strip() == "3"


def test_a_sandbox_run_is_isolated_from_the_previous_one():
    """Each invocation is a fresh process, so state must not carry over."""
    from mawe.sandbox.runner import Sandbox

    source = ("import os\n"
              "print(os.path.exists('marker'))\n"
              "open('marker', 'w').close()\n")
    with Sandbox(py(source), language="python", timeout_s=10) as box:
        first = box.run()
        second = box.run()
    # the file persists in the directory, but the interpreter state does not
    assert first["stdout"].strip() == "False"
    assert second["stdout"].strip() == "True"


def test_an_unusable_sandbox_reports_instead_of_raising():
    from mawe.sandbox.runner import Sandbox

    with Sandbox([], language="python") as box:
        assert not box.usable
        assert "no files" in (box.setup_error or "")
        result = box.run()
    assert result["exit_code"] is None
    assert "no files" in result["stderr"]


def test_a_sandbox_directory_is_removed_on_exit():
    import os

    from mawe.sandbox.runner import Sandbox

    with Sandbox(py("print(1)\n"), language="python") as box:
        directory = box.directory
        assert directory and os.path.isdir(directory)
    assert not os.path.isdir(directory)


def test_a_per_run_timeout_overrides_the_sandbox_default():
    from mawe.sandbox.runner import Sandbox

    with Sandbox(py("while True:\n    pass\n"), language="python",
                 timeout_s=30) as box:
        result = box.run(timeout_s=2)
    assert result["timed_out"]
