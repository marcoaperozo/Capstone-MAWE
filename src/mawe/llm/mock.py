"""Scripted mock provider.

This is the backend the whole test suite runs on.  It is deliberately not a
"return empty string" stub: it replays recorded, role-aware responses so the
pipeline exercises real parsing, real token accounting and real routing.

It also makes testable things a real model cannot be made to do on demand -
most importantly returning byte-identical code twice, which is the only way to
prove the no-progress exit condition fires.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence

from .base import LLMResponse, estimate_tokens

# --------------------------------------------------------------------------
# default script: a snake game that needs one fix before it passes review
# --------------------------------------------------------------------------

_DEFAULT_SPEC = {
    "summary": "Terminal snake game on a 20x20 grid.",
    "language": "python",
    "files": ["src/main.py"],
    "features": [
        "20x20 playing grid rendered in the terminal",
        "arrow-key movement",
        "food spawns at a random free cell",
        "snake grows by one segment when it eats",
        "game ends on wall collision or self collision",
        "current score is displayed",
    ],
    "constraints": ["standard library only", "single file"],
    "acceptance_criteria": [
        "the program runs without raising an exception",
        "the snake grows by exactly one segment per food eaten",
        "colliding with a wall ends the game",
        "colliding with the snake's own body ends the game",
        "the score is printed and increases on each food eaten",
    ],
}

_CODE_V1 = '''"""Terminal snake game (first draft)."""

import random

WIDTH = HEIGHT = 20


class Snake:
    def __init__(self):
        self.body = [(10, 10)]
        self.direction = (0, 1)
        self.score = 0

    def head(self):
        return self.body[0]

    def move(self, grow=False):
        x, y = self.head()
        dx, dy = self.direction
        self.body.insert(0, (x + dx, y + dy))
        if not grow:
            self.body.pop()

    def hits_wall(self):
        x, y = self.head()
        return not (0 <= x < WIDTH and 0 <= y < HEIGHT)


def spawn_food(snake):
    free = [(x, y) for x in range(WIDTH) for y in range(HEIGHT)
            if (x, y) not in snake.body]
    return random.choice(free)


def main():
    snake = Snake()
    food = spawn_food(snake)
    while True:
        grow = snake.head() == food
        snake.move(grow=grow)
        if grow:
            snake.score += 1
            food = spawn_food(snake)
        if snake.hits_wall():
            break
        print("Score:", snake.score)


if __name__ == "__main__":
    main()
'''

_CODE_V2 = _CODE_V1.replace(
    '''    def hits_wall(self):
        x, y = self.head()
        return not (0 <= x < WIDTH and 0 <= y < HEIGHT)
''',
    '''    def hits_wall(self):
        x, y = self.head()
        return not (0 <= x < WIDTH and 0 <= y < HEIGHT)

    def hits_self(self):
        return self.head() in self.body[1:]
''',
).replace(
    "        if snake.hits_wall():\n            break",
    "        if snake.hits_wall() or snake.hits_self():\n            break",
)


def _files_payload(code: str, path: str = "src/main.py") -> str:
    return json.dumps({"files": [{"path": path, "language": "python",
                                  "content": code}]})


def _review_payload(verdict: str, severity: Optional[str], issues: List[str],
                    passed: int, failed: int) -> str:
    return json.dumps({"verdict": verdict, "severity": severity,
                       "issues": issues, "tests_passed": passed,
                       "tests_failed": failed})


DEFAULT_SCRIPT: Dict[str, List[str]] = {
    "product_manager": [json.dumps(_DEFAULT_SPEC)],
    "developer": [_files_payload(_CODE_V1), _files_payload(_CODE_V2)],
    "reviewer": [
        _review_payload("reject", "major",
                        ["criterion 4 fails: self-collision never ends the game"],
                        4, 1),
        _review_payload("reject", "minor",
                        ["all 5 criteria pass; the name 'grow' shadows a local"],
                        5, 0),
    ],
}


# --------------------------------------------------------------------------

class MockProvider:
    """Replays `script[role]` in order; the last entry repeats if the loop
    runs longer than the script."""

    def __init__(self, script: Optional[Dict[str, Sequence[str]]] = None,
                 model: str = "mock-1"):
        self.name = "mock"
        self.model = model
        self.script = {k: list(v) for k, v in (script or DEFAULT_SCRIPT).items()}
        self.calls: List[str] = []
        self._cursor: Dict[str, int] = {}

    def complete(self, system: str, user: str, *, temperature: float = 0.2,
                 max_tokens: int = 4096) -> LLMResponse:
        role = self._role_of(system)
        self.calls.append(role)
        responses = self.script.get(role)
        if not responses:
            raise KeyError(
                f"MockProvider has no scripted responses for role {role!r}. "
                f"Known roles: {sorted(self.script)}")
        index = self._cursor.get(role, 0)
        text = responses[min(index, len(responses) - 1)]
        self._cursor[role] = index + 1
        return LLMResponse(
            text=text,
            prompt_tokens=estimate_tokens(system) + estimate_tokens(user),
            completion_tokens=estimate_tokens(text),
            model=self.model,
            meta={"role": role, "scripted_index": index},
        )

    @staticmethod
    def _role_of(system: str) -> str:
        """Agents tag their system prompt with a role marker so the mock can
        route without the caller passing extra arguments."""
        head = system[:200].lower()
        if "product manager" in head:
            return "product_manager"
        if "code reviewer" in head or "reviewer" in head:
            return "reviewer"
        if "developer" in head:
            return "developer"
        return "unknown"

    # convenience for tests -------------------------------------------------
    def call_count(self, role: Optional[str] = None) -> int:
        if role is None:
            return len(self.calls)
        return sum(1 for c in self.calls if c == role)


def stuck_developer_script() -> Dict[str, List[str]]:
    """Developer returns identical code every time -> no_progress exit."""
    return {
        "product_manager": [json.dumps(_DEFAULT_SPEC)],
        "developer": [_files_payload(_CODE_V1)],
        "reviewer": [_review_payload(
            "reject", "critical",
            ["criterion 1 fails: IndexError on the first move"], 0, 5)],
    }


def picky_reviewer_script(revisions: int = 8) -> Dict[str, List[str]]:
    """Reviewer never approves and the code does change -> iteration_cap."""
    return {
        "product_manager": [json.dumps(_DEFAULT_SPEC)],
        "developer": [_files_payload(_CODE_V1 + f"\n# revision {i}\n")
                      for i in range(1, revisions + 1)],
        "reviewer": [_review_payload(
            "reject", "major", ["criterion 4 still fails"], 4, 1)],
    }
