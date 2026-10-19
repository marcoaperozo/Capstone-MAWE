"""Execute generated code without trusting it.

Week 4 deliverable.  Generated code never runs in the engine's process: it is
written to a throwaway directory and executed as a subprocess with a wall-clock
timeout, captured output and truncation.

Docker with no network is the Phase 2 hardening target (proposal section 8.3).
The subprocess runner is the portable fallback so CI works without a Docker
daemon; `docker_available()` reports which one is in use.
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


def run_files(files: List[Dict[str, str]], language: str = "python",
              timeout_s: int = 10, argv: Optional[List[str]] = None,
              stdin: str = "") -> Dict[str, Any]:
    """Run the generated project and report what happened.

    Never raises on program failure - a crash is a result the Reviewer needs,
    not an exception.
    """
    result: Dict[str, Any] = {
        "exit_code": None, "timed_out": False, "stdout": "", "stderr": "",
        "entry_point": None, "isolation": "subprocess",
    }

    if not files:
        result["stderr"] = "no files to execute"
        return result

    entry = pick_entry_point(files, language)
    result["entry_point"] = entry
    if entry is None:
        result["stderr"] = f"no {language} entry point found among " \
                           f"{[f['path'] for f in files]}"
        return result

    if not interpreter_available(language):
        result["stderr"] = (f"no interpreter available for {language}; "
                            f"install it to enable execution")
        return result

    with tempfile.TemporaryDirectory(prefix="mawe-sandbox-") as directory:
        try:
            write_files(files, directory)
        except (ValueError, OSError) as exc:
            result["stderr"] = f"could not materialise files: {exc}"
            return result

        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            # deny the obvious credential-shaped variables
            "HOME": directory,
        }
        command = INTERPRETER[language] + [entry] + list(argv or [])

        try:
            completed = subprocess.run(
                command, cwd=directory, env=env, input=stdin,
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
