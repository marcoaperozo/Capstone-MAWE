"""Product Manager agent: user idea -> buildable specification.

Week 3 deliverable.  The spec is a typed contract, not prose, so the Developer
never has to interpret English and the Reviewer has a numbered checklist to
score against.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from .base import Agent
from .parsing import ParseError, as_str_list, extract_json
from .prompts import PRODUCT_MANAGER

MIN_CRITERIA = 3
MAX_CRITERIA = 8
VALID_LANGUAGES = ("python", "javascript")


@dataclass
class Specification:
    summary: str
    language: str
    files: List[str]
    features: List[str]
    constraints: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def numbered_criteria(self) -> str:
        return "\n".join(f"{i}. {c}"
                         for i, c in enumerate(self.acceptance_criteria, 1))

    def as_developer_brief(self) -> str:
        lines = [
            f"SUMMARY: {self.summary}",
            f"LANGUAGE: {self.language}",
            f"FILES TO PRODUCE: {', '.join(self.files)}",
            "",
            "FEATURES:",
        ]
        lines += [f"  - {f}" for f in self.features]
        if self.constraints:
            lines += ["", "CONSTRAINTS:"] + [f"  - {c}" for c in self.constraints]
        lines += ["", "ACCEPTANCE CRITERIA (all must hold):",
                  self.numbered_criteria()]
        return "\n".join(lines)


class SpecificationError(ParseError):
    """The spec parsed as JSON but violates the contract."""


def validate(spec: Specification) -> List[str]:
    """Return a list of contract violations; empty means valid.

    Kept separate from parsing so Week 9 can reuse it to score how often a
    real model produces a conforming spec on the first attempt.
    """
    problems: List[str] = []

    if not spec.summary.strip():
        problems.append("summary is empty")
    if spec.language not in VALID_LANGUAGES:
        problems.append(
            f"language {spec.language!r} is not one of {VALID_LANGUAGES}")
    if not spec.files:
        problems.append("files is empty; the developer needs at least one path")
    for path in spec.files:
        if path.startswith("/") or ".." in path:
            problems.append(f"file path {path!r} must be relative and inside the project")
    if not spec.features:
        problems.append("features is empty")

    n = len(spec.acceptance_criteria)
    if n < MIN_CRITERIA:
        problems.append(f"only {n} acceptance criteria; at least {MIN_CRITERIA} required")
    elif n > MAX_CRITERIA:
        problems.append(f"{n} acceptance criteria; at most {MAX_CRITERIA} allowed")
    for i, criterion in enumerate(spec.acceptance_criteria, 1):
        if len(criterion.strip()) < 10:
            problems.append(f"criterion {i} is too short to be testable: {criterion!r}")

    return problems


def parse_specification(text: str) -> Specification:
    data: Dict[str, Any] = extract_json(text)
    try:
        spec = Specification(
            summary=str(data.get("summary", "")).strip(),
            language=str(data.get("language", "python")).strip().lower(),
            files=as_str_list(data.get("files"), "files"),
            features=as_str_list(data.get("features"), "features"),
            constraints=as_str_list(data.get("constraints"), "constraints"),
            acceptance_criteria=as_str_list(
                data.get("acceptance_criteria"), "acceptance_criteria"),
        )
    except ParseError:
        raise
    except Exception as exc:  # defensive: unexpected shapes
        raise SpecificationError(f"could not build a Specification: {exc}") from exc
    return spec


class ProductManagerAgent(Agent):
    role = "product_manager"
    system_prompt = PRODUCT_MANAGER

    #: one retry with the violations fed back, then give up and record the error
    MAX_REPAIR_ATTEMPTS = 1

    def build_prompt(self, prompt: str, language: str) -> str:
        return (f"User idea:\n{prompt}\n\n"
                f"Target language: {language}\n\n"
                f"Produce the specification JSON.")

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        user_prompt = self.build_prompt(state["prompt"],
                                        state.get("language", "python"))
        attempts = 0
        errors: List[str] = []

        while True:
            raw = self.ask(user_prompt)
            try:
                spec = parse_specification(raw)
                problems = validate(spec)
            except ParseError as exc:
                spec, problems = None, [str(exc)]

            if not problems:
                return {
                    "spec": spec.to_json(),
                    "spec_json": asdict(spec),
                    "acceptance_criteria": spec.acceptance_criteria,
                    "language": spec.language,
                    **self._usage_update(state),
                }

            attempts += 1
            if attempts > self.MAX_REPAIR_ATTEMPTS:
                errors.append("product manager could not produce a valid "
                              "specification: " + "; ".join(problems))
                return {
                    "errors": list(state.get("errors", [])) + errors,
                    **self._usage_update(state),
                }

            # one repair round: show the model exactly what was wrong
            user_prompt = (
                f"{self.build_prompt(state['prompt'], state.get('language', 'python'))}\n\n"
                f"Your previous answer violated the contract:\n"
                + "\n".join(f"- {p}" for p in problems)
                + "\n\nReturn corrected JSON only.")

    def _usage_update(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {}
