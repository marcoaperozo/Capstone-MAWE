"""Sample prompts used for the Week 3 specification check.

Five prompts across both target languages and three rough difficulty levels.
Each carries a reference specification, so the Product Manager contract can be
exercised deterministically against the mock provider before any API spend.

These later become the seed rows of `benchmark_tasks` for the Phase 4
evaluation; the hidden tests are added then.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

SAMPLE_PROMPTS: List[Dict[str, Any]] = [
    {
        "name": "Temperature converter",
        "difficulty": "easy",
        "language": "python",
        "prompt": "Build a command-line temperature converter between Celsius "
                  "and Fahrenheit.",
        "spec": {
            "summary": "CLI tool converting temperatures between Celsius and Fahrenheit.",
            "language": "python",
            "files": ["src/main.py"],
            "features": [
                "accepts a value and a unit as command-line arguments",
                "converts Celsius to Fahrenheit and Fahrenheit to Celsius",
                "prints the converted value rounded to one decimal place",
                "reports an error for an unrecognised unit",
            ],
            "constraints": ["standard library only"],
            "acceptance_criteria": [
                "running with '100 C' prints 212.0",
                "running with '32 F' prints 0.0",
                "the output is rounded to exactly one decimal place",
                "an unrecognised unit exits with a non-zero status and an error message",
            ],
        },
    },
    {
        "name": "Palindrome checker",
        "difficulty": "easy",
        "language": "python",
        "prompt": "Write a program that checks whether a phrase is a palindrome, "
                  "ignoring punctuation and capitalisation.",
        "spec": {
            "summary": "Checks whether a phrase reads the same forwards and backwards.",
            "language": "python",
            "files": ["src/main.py"],
            "features": [
                "reads a phrase from standard input",
                "strips punctuation and whitespace before comparing",
                "comparison is case-insensitive",
                "prints whether the phrase is a palindrome",
            ],
            "constraints": ["standard library only"],
            "acceptance_criteria": [
                "'A man, a plan, a canal: Panama' is reported as a palindrome",
                "'hello world' is reported as not a palindrome",
                "an empty input is reported as a palindrome",
                "capitalisation does not change the result",
            ],
        },
    },
    {
        "name": "Todo CLI with file persistence",
        "difficulty": "medium",
        "language": "python",
        "prompt": "Build a to-do list command-line tool that saves tasks to a "
                  "file so they survive between runs.",
        "spec": {
            "summary": "CLI to-do list persisting tasks to a JSON file.",
            "language": "python",
            "files": ["src/main.py", "src/storage.py"],
            "features": [
                "add a task with a description",
                "list all tasks with an index and a done marker",
                "mark a task done by index",
                "delete a task by index",
                "tasks persist to a JSON file between runs",
            ],
            "constraints": ["standard library only", "the data file is created if missing"],
            "acceptance_criteria": [
                "a task added in one invocation is listed in the next invocation",
                "marking a task done changes its marker in the listing",
                "deleting a task removes it from the listing",
                "listing with no tasks prints an empty-list message rather than failing",
                "an out-of-range index prints an error and exits non-zero",
            ],
        },
    },
    {
        "name": "Markdown to HTML converter",
        "difficulty": "medium",
        "language": "javascript",
        "prompt": "Write a Node script that converts a subset of Markdown "
                  "(headings, bold, italics, links, lists) to HTML.",
        "spec": {
            "summary": "Node script converting a Markdown subset to HTML.",
            "language": "javascript",
            "files": ["src/main.js", "src/convert.js"],
            "features": [
                "converts ATX headings level 1 to 6",
                "converts bold and italic emphasis",
                "converts inline links",
                "converts unordered lists",
                "reads from a file path argument and writes HTML to stdout",
            ],
            "constraints": ["no external npm packages", "Node 20 or newer"],
            "acceptance_criteria": [
                "'# Title' becomes '<h1>Title</h1>'",
                "'**bold**' becomes '<strong>bold</strong>'",
                "'[text](http://example.com)' becomes an anchor with that href",
                "a dash-prefixed list becomes a ul with one li per item",
                "plain paragraphs are wrapped in p tags",
            ],
        },
    },
    {
        "name": "Expression parser and evaluator",
        "difficulty": "hard",
        "language": "python",
        "prompt": "Build an arithmetic expression parser and evaluator "
                  "supporting precedence, parentheses and unary minus.",
        "spec": {
            "summary": "Recursive-descent parser and evaluator for arithmetic expressions.",
            "language": "python",
            "files": ["src/main.py", "src/lexer.py", "src/parser.py"],
            "features": [
                "tokenises integers, floats and operators",
                "supports + - * / with correct precedence",
                "supports parentheses to override precedence",
                "supports unary minus",
                "reports a clear error for malformed input",
            ],
            "constraints": ["standard library only", "no use of eval"],
            "acceptance_criteria": [
                "'2 + 3 * 4' evaluates to 14",
                "'(2 + 3) * 4' evaluates to 20",
                "'-5 + 3' evaluates to -2",
                "'10 / 4' evaluates to 2.5",
                "'2 +' raises a parse error rather than crashing with a traceback",
            ],
        },
    },
]


def pm_script(spec: Dict[str, Any], malformed_first: bool = False) -> Dict[str, List[str]]:
    """Build a mock script for the Product Manager.

    With `malformed_first`, the first response violates the contract so the
    repair round can be exercised.
    """
    responses: List[str] = []
    if malformed_first:
        broken = dict(spec)
        broken["acceptance_criteria"] = spec["acceptance_criteria"][:1]
        responses.append("Here is the specification you asked for:\n\n```json\n"
                         + json.dumps(broken) + "\n```")
    responses.append(json.dumps(spec))
    return {"product_manager": responses}


def as_benchmark_rows() -> List[Dict[str, Any]]:
    """Shape these prompts the way `benchmark_tasks` stores them."""
    return [
        {
            "name": s["name"],
            "prompt": s["prompt"],
            "difficulty": s["difficulty"],
            "language": s["language"],
            "hidden_tests": "",  # added in Phase 4
        }
        for s in SAMPLE_PROMPTS
    ]
