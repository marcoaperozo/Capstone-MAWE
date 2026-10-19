"""Reference implementations used by the Week 4 milestone check.

These are what the mock Developer returns.  They are real, runnable programs,
not illustrative snippets - the Week 4 check writes them into the sandbox,
executes them and asserts on the output, which is what makes "the Developer
agent generates runnable code" a measured claim rather than an assertion.
"""

from __future__ import annotations

from typing import Any, Dict, List

TEMPERATURE_MAIN = '''"""Convert between Celsius and Fahrenheit."""

import sys

USAGE = "usage: main.py <value> <C|F>"


def c_to_f(celsius):
    return celsius * 9.0 / 5.0 + 32.0


def f_to_c(fahrenheit):
    return (fahrenheit - 32.0) * 5.0 / 9.0


def main(argv):
    if len(argv) != 2:
        print(USAGE, file=sys.stderr)
        return 1

    raw, unit = argv[0], argv[1].strip().upper()
    try:
        value = float(raw)
    except ValueError:
        print("error: value must be a number", file=sys.stderr)
        return 1

    if unit == "C":
        print(round(c_to_f(value), 1))
    elif unit == "F":
        print(round(f_to_c(value), 1))
    else:
        print("error: unit must be C or F", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

PALINDROME_MAIN = '''"""Check whether a phrase is a palindrome."""

import sys


def normalise(phrase):
    return "".join(ch.lower() for ch in phrase if ch.isalnum())


def is_palindrome(phrase):
    cleaned = normalise(phrase)
    return cleaned == cleaned[::-1]


def main():
    phrase = sys.stdin.read()
    if is_palindrome(phrase):
        print("palindrome")
    else:
        print("not a palindrome")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

EXPR_LEXER = '''"""Tokeniser for arithmetic expressions."""


class LexError(ValueError):
    pass


OPERATORS = set("+-*/()")


def tokenize(text):
    tokens = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in OPERATORS:
            tokens.append((ch, ch))
            i += 1
            continue
        if ch.isdigit() or ch == ".":
            start = i
            seen_dot = False
            while i < len(text) and (text[i].isdigit() or text[i] == "."):
                if text[i] == ".":
                    if seen_dot:
                        raise LexError("malformed number")
                    seen_dot = True
                i += 1
            tokens.append(("NUMBER", text[start:i]))
            continue
        raise LexError("unexpected character: " + ch)
    tokens.append(("EOF", ""))
    return tokens
'''

EXPR_PARSER = '''"""Recursive-descent parser and evaluator.

Grammar:
    expression := term (("+" | "-") term)*
    term       := factor (("*" | "/") factor)*
    factor     := "-" factor | NUMBER | "(" expression ")"
"""

from lexer import tokenize


class ParseError(ValueError):
    pass


class Parser(object):
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos][0]

    def next(self):
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def expect(self, kind):
        if self.peek() != kind:
            raise ParseError("expected " + kind + " but found " + self.peek())
        return self.next()

    def parse(self):
        value = self.expression()
        if self.peek() != "EOF":
            raise ParseError("unexpected trailing input: " + self.peek())
        return value

    def expression(self):
        value = self.term()
        while self.peek() in ("+", "-"):
            op = self.next()[0]
            right = self.term()
            value = value + right if op == "+" else value - right
        return value

    def term(self):
        value = self.factor()
        while self.peek() in ("*", "/"):
            op = self.next()[0]
            right = self.factor()
            if op == "*":
                value = value * right
            else:
                if right == 0:
                    raise ParseError("division by zero")
                value = value / right
        return value

    def factor(self):
        kind = self.peek()
        if kind == "-":
            self.next()
            return -self.factor()
        if kind == "NUMBER":
            raw = self.next()[1]
            return float(raw) if "." in raw else int(raw)
        if kind == "(":
            self.next()
            value = self.expression()
            self.expect(")")
            return value
        raise ParseError("unexpected token: " + kind)


def evaluate(text):
    return Parser(tokenize(text)).parse()
'''

EXPR_MAIN = '''"""Evaluate an arithmetic expression given on the command line."""

import sys

from parser import ParseError, evaluate
from lexer import LexError


def main(argv):
    if not argv:
        print("usage: main.py \\"2 + 3 * 4\\"", file=sys.stderr)
        return 1
    try:
        print(evaluate(" ".join(argv)))
    except (ParseError, LexError) as exc:
        print("parse error: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''


#: name -> {files, checks}.  Each check runs the program and asserts on stdout.
RUNNABLE_SAMPLES: Dict[str, Dict[str, Any]] = {
    "Temperature converter": {
        "files": [
            {"path": "src/main.py", "language": "python", "content": TEMPERATURE_MAIN},
        ],
        "checks": [
            {"argv": ["100", "C"], "stdin": "", "expect": "212.0"},
            {"argv": ["32", "F"], "stdin": "", "expect": "0.0"},
            {"argv": ["-40", "C"], "stdin": "", "expect": "-40.0"},
        ],
    },
    "Palindrome checker": {
        "files": [
            {"path": "src/main.py", "language": "python", "content": PALINDROME_MAIN},
        ],
        "checks": [
            {"argv": [], "stdin": "A man, a plan, a canal: Panama", "expect": "palindrome"},
            {"argv": [], "stdin": "hello world", "expect": "not a palindrome"},
            {"argv": [], "stdin": "", "expect": "palindrome"},
        ],
    },
    "Expression parser and evaluator": {
        "files": [
            {"path": "src/lexer.py", "language": "python", "content": EXPR_LEXER},
            {"path": "src/parser.py", "language": "python", "content": EXPR_PARSER},
            {"path": "src/main.py", "language": "python", "content": EXPR_MAIN},
        ],
        "checks": [
            {"argv": ["2 + 3 * 4"], "stdin": "", "expect": "14"},
            {"argv": ["(2 + 3) * 4"], "stdin": "", "expect": "20"},
            {"argv": ["-5 + 3"], "stdin": "", "expect": "-2"},
            {"argv": ["10 / 4"], "stdin": "", "expect": "2.5"},
        ],
    },
}


def dev_script(name: str) -> Dict[str, List[str]]:
    """Mock Developer script returning the reference files for one sample."""
    import json
    files = RUNNABLE_SAMPLES[name]["files"]
    return {"developer": [json.dumps({"files": files})]}
