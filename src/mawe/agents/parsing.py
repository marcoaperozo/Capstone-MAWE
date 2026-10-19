"""Defensive parsing of model output.

Models wrap JSON in prose, in ```json fences, or emit it bare.  Every agent
goes through here so a formatting slip becomes a typed error the graph can
record and route on, instead of an exception that kills the run.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

_FENCE = re.compile(r"```(?:json|JSON)?\s*\n(.*?)```", re.DOTALL)
_CODE_FENCE = re.compile(r"```(\w+)?\s*\n(.*?)```", re.DOTALL)


class ParseError(ValueError):
    """Model output did not match the agent's output contract."""


def extract_json(text: str) -> Dict[str, Any]:
    """Pull the first JSON object out of a model response."""
    if not text or not text.strip():
        raise ParseError("empty response")

    candidates: List[str] = []

    for match in _FENCE.finditer(text):
        candidates.append(match.group(1))

    stripped = text.strip()
    if stripped.startswith("{"):
        candidates.append(stripped)

    # last resort: the widest {...} span in the text
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first:last + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ParseError(
        f"no JSON object found in response (first 200 chars: {text[:200]!r})")


def extract_code_blocks(text: str) -> List[Dict[str, str]]:
    """Fallback for a model that returns fenced code instead of the JSON
    files contract.  Returns [{language, content}, ...]."""
    blocks = []
    for lang, body in _CODE_FENCE.findall(text):
        if (lang or "").lower() in {"json", ""} and body.strip().startswith("{"):
            continue
        blocks.append({"language": (lang or "python").lower(),
                       "content": body})
    return blocks


def as_str_list(value: Any, field: str) -> List[str]:
    """Coerce a field that should be a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                # models sometimes emit [{"id": 1, "text": "..."}]
                for key in ("text", "description", "criterion", "value", "name"):
                    if key in item and isinstance(item[key], str):
                        out.append(item[key])
                        break
            else:
                out.append(str(item))
        return out
    raise ParseError(f"field {field!r} should be a list of strings, "
                     f"got {type(value).__name__}")
