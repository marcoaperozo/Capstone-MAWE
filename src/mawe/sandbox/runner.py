"""Execute generated code without trusting it.

Week 4 deliverable.  Generated code never runs in the engine's process: it is
written to a throwaway directory and executed as a subprocess with a wall-clock
timeout, captured output and truncation.

Docker with no network is the hardening target (proposal section 8.3) and is
**not implemented**: every execution in this project goes through the
subprocess path below, which is why each result reports
`isolation: "subprocess"`. `docker_available()` only probes whether a daemon
could be reached, so that the gap is visible rather than assumed closed. This
is a resource limit and a containment boundary, not a security boundary.

Two entry points, same isolation:

* `run_files` - materialise the project, run it once, throw the directory away.
  This is what the Reviewer uses; it runs a handful of checks per review and
  the setup cost is irrelevant.
* `Sandbox` - materialise the project once and run it many times.  Week 9
  added this for the benchmark harness, where re-writing the same project for
  every hidden test was most of the wall clock.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional

MAX_OUTPUT_CHARS = 20_000

INTERPRETER = {
    "python": [sys.executable],
    "javascript": ["node"],
}

ENTRY_CANDIDATES = {
    "python": ("src/main.py", "main.py", "app.py"),
    "javascript": ("src/main.js", "main.js", "index.js", "app.js"),
}


def docker_available() -> bool:
    """True when a Docker daemon is reachable."""
    if not shutil.which("docker"):
        return False
    try:
        result = subprocess.run(["docker", "info"], capture_output=True,
                                timeout=5)
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def interpreter_available(language: str) -> bool:
    cmd = INTERPRETER.get(language)
    if not cmd:
        return False
    if language == "python":
        return True
    return shutil.which(cmd[0]) is not None


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n...[truncated {len(text) - MAX_OUTPUT_CHARS} chars]"


def pick_entry_point(files: List[Dict[str, str]], language: str) -> Optional[str]:
    paths = {f["path"] for f in files}
    for candidate in ENTRY_CANDIDATES.get(language, ()):
        if candidate in paths:
            return candidate
    suffix = ".py" if language == "python" else ".js"
    for f in files:
        if f["path"].endswith(suffix):
            return f["path"]
    return None


def write_files(files: List[Dict[str, str]], directory: str) -> List[str]:
    """Materialise the generated files, refusing any path that escapes the
    sandbox directory."""
    written = []
    root = os.path.realpath(directory)
    for f in files:
        target = os.path.realpath(os.path.join(root, f["path"]))
        if not target.startswith(root + os.sep) and target != root:
            raise ValueError(f"file path escapes the sandbox: {f['path']!r}")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(f["content"])
        written.append(target)
    return written


def _blank_result() -> Dict[str, Any]:
    return {
        "exit_code": None, "timed_out": False, "stdout": "", "stderr": "",
        "entry_point": None, "isolation": "subprocess",
    }


def _child_env(directory: str) -> Dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        # deny the obvious credential-shaped variables
        "HOME": directory,
    }


def _execute(command: List[str], directory: str, stdin: str, timeout_s: int,
             entry: Optional[str]) -> Dict[str, Any]:
    """Run one subprocess and describe what happened.  Never raises on program
    failure - a crash is a result the caller needs, not an exception."""
    result = _blank_result()
    result["entry_point"] = entry
    try:
        completed = subprocess.run(
            command, cwd=directory, env=_child_env(directory), input=stdin,
            capture_output=True, text=True, timeout=timeout_s,
            encoding="utf-8", errors="replace",
        )
        result["exit_code"] = completed.returncode
        result["stdout"] = _truncate(completed.stdout or "")
        result["stderr"] = _truncate(completed.stderr or "")
    except subprocess.TimeoutExpired as exc:
        result["timed_out"] = True
        result["exit_code"] = None
        result["stdout"] = _truncate((exc.stdout or b"").decode("utf-8", "replace")
                                     if isinstance(exc.stdout, bytes)
                                     else (exc.stdout or ""))
        result["stderr"] = (_truncate((exc.stderr or b"").decode("utf-8", "replace")
                                      if isinstance(exc.stderr, bytes)
                                      else (exc.stderr or ""))
                            + f"\n[killed after {timeout_s}s]")
    except OSError as exc:
        result["stderr"] = f"could not start the interpreter: {exc}"
    return result


class Sandbox:
    """A project materialised once, runnable many times.

    The benchmark harness runs every hidden test for a task against the same
    generated project.  Writing the files per invocation, as `run_files` does,
    dominated the wall clock once Phase 4 started running thousands of tests,
    so this keeps one directory alive for the life of the context manager.

    `setup_error` is set, and `run()` returns that error, when the project
    cannot be executed at all - no files, no entry point, no interpreter.
    Callers see a failed test rather than an exception, which is what the
    scoring harness wants: code that will not even start has simply failed.
    """

    def __init__(self, files: List[Dict[str, str]], language: str = "python",
                 timeout_s: int = 10) -> None:
        self.files = files
        self.language = language
        self.timeout_s = timeout_s
        self.entry_point: Optional[str] = None
        self.setup_error: Optional[str] = None
        self._tmp: Optional[tempfile.TemporaryDirectory] = None
        self.directory: Optional[str] = None

    # ------------------------------------------------------------------
    def __enter__(self) -> "Sandbox":
        if not self.files:
            self.setup_error = "no files to execute"
            return self

        self.entry_point = pick_entry_point(self.files, self.language)
        if self.entry_point is None:
            self.setup_error = (f"no {self.language} entry point found among "
                                f"{[f['path'] for f in self.files]}")
            return self

        if not interpreter_available(self.language):
            self.setup_error = (f"no interpreter available for "
                                f"{self.language}; install it to enable "
                                f"execution")
            return self

        self._tmp = tempfile.TemporaryDirectory(prefix="mawe-sandbox-")
        self.directory = self._tmp.name
        try:
            write_files(self.files, self.directory)
        except (ValueError, OSError) as exc:
            self.setup_error = f"could not materialise files: {exc}"
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None
            self.directory = None

    # ------------------------------------------------------------------
    @property
    def usable(self) -> bool:
        return self.setup_error is None

    def run(self, argv: Optional[List[str]] = None, stdin: str = "",
            timeout_s: Optional[int] = None) -> Dict[str, Any]:
        if self.setup_error is not None:
            result = _blank_result()
            result["entry_point"] = self.entry_point
            result["stderr"] = self.setup_error
            return result

        assert self.directory is not None and self.entry_point is not None
        command = INTERPRETER[self.language] + [self.entry_point] + \
            [str(a) for a in (argv or [])]
        return _execute(command, self.directory, stdin,
                        self.timeout_s if timeout_s is None else timeout_s,
                        self.entry_point)


def run_files(files: List[Dict[str, str]], language: str = "python",
              timeout_s: int = 10, argv: Optional[List[str]] = None,
              stdin: str = "") -> Dict[str, Any]:
    """Run the generated project once in a throwaway directory.

    Never raises on program failure - a crash is a result the Reviewer needs,
    not an exception.
    """
    with Sandbox(files, language=language, timeout_s=timeout_s) as box:
        return box.run(argv=argv, stdin=stdin)
