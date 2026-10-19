"""Developer agent: specification (+ review feedback) -> source files.

Week 4 deliverable.  Produces complete multi-file output, refuses placeholder
content, and records a hash of the result so the graph can detect a developer
that is not making progress.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..graph.workflow import hash_files
from .base import Agent
from .parsing import ParseError, extract_code_blocks, extract_json
from .prompts import DEVELOPER

#: fragments that mean the model elided part of the file
PLACEHOLDER_MARKERS = (
    "# ... rest of",
    "# rest of the code",
    "// rest of the code",
    "# your code here",
    "// your code here",
    "<implementation>",
    "# TODO: implement",
    "// TODO: implement",
    "... (unchanged)",
)

EXTENSION_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".txt": "text",
}


class DeveloperError(ParseError):
    """Output parsed but does not satisfy the developer contract."""


def language_for(path: str, default: str = "python") -> str:
    for ext, lang in EXTENSION_LANGUAGE.items():
        if path.endswith(ext):
            return lang
    return default


def find_placeholders(content: str) -> List[str]:
    lowered = content.lower()
    return [m for m in PLACEHOLDER_MARKERS if m.lower() in lowered]


def parse_files(text: str, default_language: str = "python",
                expected: List[str] | None = None) -> List[Dict[str, str]]:
    """Parse the files contract, falling back to fenced code blocks."""
    files: List[Dict[str, str]] = []

    try:
        data = extract_json(text)
        raw_files = data.get("files")
    except ParseError:
        raw_files = None

    if isinstance(raw_files, list) and raw_files:
        for i, item in enumerate(raw_files):
            if not isinstance(item, dict):
                raise DeveloperError(f"files[{i}] is not an object")
            path = str(item.get("path") or "").strip()
            content = item.get("content")
            if not path:
                raise DeveloperError(f"files[{i}] has no path")
            if not isinstance(content, str) or not content.strip():
                raise DeveloperError(f"files[{i}] ({path}) has empty content")
            files.append({"path": path,
                          "language": str(item.get("language")
                                          or language_for(path, default_language)),
                          "content": content})
    else:
        # fallback: the model returned fenced code instead of the contract
        blocks = extract_code_blocks(text)
        if not blocks:
            raise DeveloperError(
                "response contained neither a files array nor a code block")
        names = expected or [f"src/main.{'js' if default_language == 'javascript' else 'py'}"]
        for i, block in enumerate(blocks):
            path = names[i] if i < len(names) else f"src/extra_{i}.txt"
            files.append({"path": path,
                          "language": block["language"] or default_language,
                          "content": block["content"]})

    seen = set()
    for f in files:
        if f["path"] in seen:
            raise DeveloperError(f"duplicate file path {f['path']!r}")
        seen.add(f["path"])
        placeholders = find_placeholders(f["content"])
        if placeholders:
            raise DeveloperError(
                f"{f['path']} contains placeholder text {placeholders[0]!r}; "
                f"the developer must emit the complete file")

    return files


class DeveloperAgent(Agent):
    role = "developer"
    system_prompt = DEVELOPER

    MAX_REPAIR_ATTEMPTS = 1

    def build_prompt(self, state: Dict[str, Any]) -> str:
        parts = ["SPECIFICATION:", state.get("spec", "")]

        issues = state.get("issues") or []
        if issues:
            parts += [
                "",
                "THE CODE REVIEWER REJECTED YOUR PREVIOUS VERSION.",
                f"Severity: {state.get('severity')}",
                f"Tests passed: {state.get('tests_passed', 0)}  "
                f"failed: {state.get('tests_failed', 0)}",
                "",
                "Address every one of these items:",
            ]
            parts += [f"{i}. {issue}" for i, issue in enumerate(issues, 1)]
            parts += ["",
                      "YOUR PREVIOUS FILES:",
                      self._render_previous(state.get("files") or [])]

        parts += ["", "Return the complete files JSON."]
        return "\n".join(parts)

    @staticmethod
    def _render_previous(files: List[Dict[str, str]]) -> str:
        return "\n\n".join(
            f"--- {f['path']} ---\n{f['content']}" for f in files) or "(none)"

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        spec_json = state.get("spec_json") or {}
        expected = spec_json.get("files") or None
        language = state.get("language", "python")
        iteration = int(state.get("iteration", 0)) + 1

        user_prompt = self.build_prompt(state)
        attempts = 0

        while True:
            raw = self.ask(user_prompt)
            try:
                files = parse_files(raw, default_language=language,
                                    expected=expected)
                missing = self._missing_files(files, expected)
                if missing:
                    raise DeveloperError(
                        "specification requires these files that were not "
                        f"produced: {', '.join(missing)}")
            except ParseError as exc:
                attempts += 1
                if attempts > self.MAX_REPAIR_ATTEMPTS:
                    return {
                        "iteration": iteration,
                        "errors": list(state.get("errors", [])) + [
                            f"developer output invalid: {exc}"],
                    }
                user_prompt = (f"{self.build_prompt(state)}\n\n"
                               f"Your previous answer was rejected: {exc}\n"
                               f"Return corrected JSON only.")
                continue

            digest = hash_files(files)
            return {
                "files": files,
                "code_hash": digest,
                "seen_hashes": list(state.get("seen_hashes", [])) + [digest],
                "iteration": iteration,
            }

    @staticmethod
    def _missing_files(files: List[Dict[str, str]],
                       expected: List[str] | None) -> List[str]:
        if not expected:
            return []
        produced = {f["path"] for f in files}
        return [p for p in expected if p not in produced]
