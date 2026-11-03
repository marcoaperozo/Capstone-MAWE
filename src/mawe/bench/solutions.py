"""Reference solutions, used only to validate the benchmark.

Week 9.  A benchmark nobody has solved is not a benchmark - it is a wish list.
Two things can be wrong with a task, and a reference solution is what catches
both:

* **The task is impossible, or the prompt contradicts the tests.**  If the
  reference cannot pass its own hidden tests, the task is broken and no
  condition could ever score on it.  A failure here would otherwise show up in
  Phase 4 as "all four conditions did badly", which looks like a finding and
  is actually a bug in the measuring instrument.
* **The tests are vacuous.**  Tests that pass for a program that does nothing
  measure nothing.  `mutation.py` mutates these references and checks the
  hidden tests notice, which turns "the tests look thorough" into a number.

These are **never** shown to an agent.  Nothing in `graph/`, `agents/` or
`engine.py` imports this module; it is reachable only from the validation
script and the tests.  The one-way dependency is itself asserted in
`tests/test_benchmark.py`, because the whole experiment is void if a reference
solution ever leaks into a prompt.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .tasks import BY_SLUG, BenchTask

# ============================================================ easy
FIZZBUZZ = '''import sys


def main(argv):
    if len(argv) != 1:
        print("usage: main.py N", file=sys.stderr)
        return 1
    try:
        n = int(argv[0])
    except ValueError:
        print("N must be an integer", file=sys.stderr)
        return 1
    if n < 1:
        print("N must be at least 1", file=sys.stderr)
        return 1
    for i in range(1, n + 1):
        if i % 15 == 0:
            print("FizzBuzz")
        elif i % 3 == 0:
            print("Fizz")
        elif i % 5 == 0:
            print("Buzz")
        else:
            print(i)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

WORD_COUNT = '''import sys

data = sys.stdin.read()
print("lines: {}".format(len(data.splitlines())))
print("words: {}".format(len(data.split())))
'''

SUM_ARGS = '''const args = process.argv.slice(2);
let total = 0;
for (const arg of args) {
  if (!/^[+-]?\\d+$/.test(arg)) {
    process.stderr.write("not an integer: " + arg + "\\n");
    process.exit(1);
  }
  total += parseInt(arg, 10);
}
console.log(String(total));
'''

REVERSE_WORDS = '''import sys

lines = sys.stdin.read().splitlines()
for line in lines:
    print(" ".join(reversed(line.split())))
'''

ROMAN_NUMERALS = '''const arg = process.argv[2];
if (arg === undefined || !/^\\d+$/.test(arg)) {
  process.stderr.write("usage: main.js N  (integer 1-3999)\\n");
  process.exit(1);
}
const n = parseInt(arg, 10);
if (n < 1 || n > 3999) {
  process.stderr.write("N must be between 1 and 3999\\n");
  process.exit(1);
}
const table = [
  [1000, "M"], [900, "CM"], [500, "D"], [400, "CD"],
  [100, "C"], [90, "XC"], [50, "L"], [40, "XL"],
  [10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"],
];
let rest = n;
let out = "";
for (const [value, numeral] of table) {
  while (rest >= value) {
    out += numeral;
    rest -= value;
  }
}
console.log(out);
'''

PALINDROME = '''import sys

if len(sys.argv) < 2:
    print("usage: main.py TEXT", file=sys.stderr)
    sys.exit(1)

cleaned = [c.lower() for c in sys.argv[1] if c.isalnum()]
print("yes" if cleaned == cleaned[::-1] else "no")
'''

GCD_LCM = '''const isWhole = (s) => s !== undefined && /^\\d+$/.test(s);
const a = process.argv[2];
const b = process.argv[3];
if (!isWhole(a) || !isWhole(b)) {
  process.stderr.write("usage: main.js A B  (non-negative integers)\\n");
  process.exit(1);
}
const x = parseInt(a, 10);
const y = parseInt(b, 10);
const gcd = (p, q) => (q === 0 ? p : gcd(q, p % q));
const g = gcd(x, y);
const l = x === 0 || y === 0 ? 0 : (x / g) * y;
console.log("gcd: " + g);
console.log("lcm: " + l);
'''

# ============================================================ medium
RPN = '''import sys

OPERATORS = ("+", "-", "*", "/")


def main():
    tokens = sys.stdin.read().split()
    if not tokens:
        print("empty expression", file=sys.stderr)
        return 1

    stack = []
    for token in tokens:
        if token in OPERATORS:
            if len(stack) < 2:
                print("stack underflow at " + token, file=sys.stderr)
                return 1
            right = stack.pop()
            left = stack.pop()
            if token == "+":
                stack.append(left + right)
            elif token == "-":
                stack.append(left - right)
            elif token == "*":
                stack.append(left * right)
            else:
                if right == 0:
                    print("division by zero", file=sys.stderr)
                    return 1
                quotient = abs(left) // abs(right)
                stack.append(quotient if (left < 0) == (right < 0)
                             else -quotient)
        else:
            try:
                stack.append(int(token))
            except ValueError:
                print("bad token: " + token, file=sys.stderr)
                return 1

    if len(stack) != 1:
        print("leftover operands", file=sys.stderr)
        return 1
    print(stack[0])
    return 0


sys.exit(main())
'''

CSV_STATS = '''import csv
import io
import sys


def render(value):
    return str(int(value)) if float(value).is_integer() else str(value)


def main(argv):
    if len(argv) != 1:
        print("usage: main.py COLUMN", file=sys.stderr)
        return 1
    column = argv[0]

    rows = [r for r in csv.reader(io.StringIO(sys.stdin.read()))
            if r and any(c.strip() for c in r)]
    if not rows:
        print("no input", file=sys.stderr)
        return 1

    header = [h.strip() for h in rows[0]]
    if column not in header:
        print("no such column: " + column, file=sys.stderr)
        return 1
    index = header.index(column)

    values = []
    for row in rows[1:]:
        if index >= len(row):
            print("row is missing the column", file=sys.stderr)
            return 1
        try:
            values.append(float(row[index].strip()))
        except ValueError:
            print("non-numeric value: " + row[index], file=sys.stderr)
            return 1

    if not values:
        print("no data rows", file=sys.stderr)
        return 1

    print("count: {}".format(len(values)))
    print("min: {}".format(render(min(values))))
    print("max: {}".format(render(max(values))))
    print("mean: {:.2f}".format(sum(values) / len(values)))
    return 0


sys.exit(main(sys.argv[1:]))
'''

BRACKETS = '''const fs = require("fs");

const line = fs.readFileSync(0, "utf8").split("\\n")[0].replace(/\\r$/, "");
const closers = { ")": "(", "]": "[", "}": "{" };
const openers = "([{";
const stack = [];
let bad = -1;

for (let i = 0; i < line.length; i++) {
  const ch = line[i];
  if (openers.includes(ch)) {
    stack.push(ch);
  } else if (ch in closers) {
    if (stack.length === 0 || stack.pop() !== closers[ch]) {
      bad = i;
      break;
    }
  }
}
if (bad === -1 && stack.length > 0) {
  bad = line.length;
}

console.log(bad === -1 ? "balanced" : "unbalanced at index " + bad);
'''

RLE = '''import sys


def encode(data):
    out = []
    i = 0
    while i < len(data):
        j = i
        while j < len(data) and data[j] == data[i]:
            j += 1
        out.append("{}{}".format(data[i], j - i))
        i = j
    return "".join(out)


def decode(data):
    out = []
    i = 0
    while i < len(data):
        char = data[i]
        j = i + 1
        while j < len(data) and data[j].isdigit():
            j += 1
        digits = data[i + 1:j]
        if not digits or int(digits) < 1:
            return None
        out.append(char * int(digits))
        i = j
    return "".join(out)


def main(argv):
    if len(argv) != 1 or argv[0] not in ("encode", "decode"):
        print("usage: main.py encode|decode", file=sys.stderr)
        return 1

    data = sys.stdin.read().split("\\n")[0]
    if argv[0] == "encode":
        print(encode(data))
        return 0

    result = decode(data)
    if result is None:
        print("malformed input", file=sys.stderr)
        return 1
    print(result)
    return 0


sys.exit(main(sys.argv[1:]))
'''

TOP_K_WORDS = '''import re
import sys
from collections import Counter


def main(argv):
    if len(argv) != 1:
        print("usage: main.py K", file=sys.stderr)
        return 1
    try:
        k = int(argv[0])
    except ValueError:
        print("K must be an integer", file=sys.stderr)
        return 1
    if k < 0:
        print("K must not be negative", file=sys.stderr)
        return 1

    words = re.findall(r"[A-Za-z0-9']+", sys.stdin.read().lower())
    ranked = sorted(Counter(words).items(), key=lambda kv: (-kv[1], kv[0]))
    for word, count in ranked[:k]:
        print("{}: {}".format(word, count))
    return 0


sys.exit(main(sys.argv[1:]))
'''

DATE_DIFF = '''const PATTERN = /^(\\d{4})-(\\d{2})-(\\d{2})$/;

function parse(text) {
  if (text === undefined) {
    return null;
  }
  const m = PATTERN.exec(text);
  if (!m) {
    return null;
  }
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 ||
      date.getUTCDate() !== day) {
    return null;
  }
  return date;
}

const a = parse(process.argv[2]);
const b = parse(process.argv[3]);
if (a === null || b === null) {
  process.stderr.write("usage: main.js YYYY-MM-DD YYYY-MM-DD\\n");
  process.exit(1);
}
console.log(String(Math.round(Math.abs(b - a) / 86400000)));
'''

MATRIX_SPIRAL = '''import sys


def main():
    lines = [line for line in sys.stdin.read().splitlines() if line.strip()]
    if not lines:
        print("")
        return 0

    grid = []
    for line in lines:
        row = []
        for token in line.split():
            try:
                row.append(int(token))
            except ValueError:
                print("not an integer: " + token, file=sys.stderr)
                return 1
        grid.append(row)

    width = len(grid[0])
    if any(len(row) != width for row in grid):
        print("rows are not all the same length", file=sys.stderr)
        return 1

    out = []
    top, bottom, left, right = 0, len(grid) - 1, 0, width - 1
    while top <= bottom and left <= right:
        for c in range(left, right + 1):
            out.append(grid[top][c])
        top += 1
        for r in range(top, bottom + 1):
            out.append(grid[r][right])
        right -= 1
        if top <= bottom:
            for c in range(right, left - 1, -1):
                out.append(grid[bottom][c])
            bottom -= 1
        if left <= right:
            for r in range(bottom, top - 1, -1):
                out.append(grid[r][left])
            left += 1

    print(" ".join(str(v) for v in out))
    return 0


sys.exit(main())
'''

INI_TO_JSON = '''const fs = require("fs");

const text = fs.readFileSync(0, "utf8");
const sections = new Map();
let current = null;

for (const raw of text.split(/\\r?\\n/)) {
  const line = raw.trim();
  if (line === "" || line.startsWith(";") || line.startsWith("#")) {
    continue;
  }
  const header = /^\\[(.+)\\]$/.exec(line);
  if (header) {
    current = header[1].trim();
    if (!sections.has(current)) {
      sections.set(current, new Map());
    }
    continue;
  }
  const eq = line.indexOf("=");
  if (eq === -1) {
    process.stderr.write("not a section or property: " + line + "\\n");
    process.exit(1);
  }
  if (current === null) {
    process.stderr.write("property before any section: " + line + "\\n");
    process.exit(1);
  }
  sections.get(current).set(line.slice(0, eq).trim(),
                            line.slice(eq + 1).trim());
}

const out = {};
for (const name of [...sections.keys()].sort()) {
  const inner = {};
  for (const key of [...sections.get(name).keys()].sort()) {
    inner[key] = sections.get(name).get(key);
  }
  out[name] = inner;
}
console.log(JSON.stringify(out, null, 2));
'''

# ============================================================ hard
JSON_QUERY = '''import json
import re
import sys

SEGMENT = re.compile(r"^([^\\[\\]\\.]+)((?:\\[\\d+\\])*)$")


def main(argv):
    if len(argv) != 1:
        print("usage: main.py PATH", file=sys.stderr)
        return 1

    try:
        value = json.loads(sys.stdin.read())
    except ValueError:
        print("standard input is not valid JSON", file=sys.stderr)
        return 1

    path = argv[0]
    if path.strip():
        for part in path.split("."):
            match = SEGMENT.match(part)
            if not match:
                print("malformed path segment: " + part, file=sys.stderr)
                return 1
            key, indices = match.group(1), match.group(2)
            if not isinstance(value, dict):
                print("cannot read key " + key + " from a non-object",
                      file=sys.stderr)
                return 1
            if key not in value:
                print("missing key: " + key, file=sys.stderr)
                return 1
            value = value[key]
            for index in re.findall(r"\\[(\\d+)\\]", indices):
                position = int(index)
                if not isinstance(value, list):
                    print("cannot index a non-array", file=sys.stderr)
                    return 1
                if position >= len(value):
                    print("index out of range: " + index, file=sys.stderr)
                    return 1
                value = value[position]

    print(json.dumps(value, separators=(",", ":")))
    return 0


sys.exit(main(sys.argv[1:]))
'''

FREE_SLOTS = '''import re
import sys

TIME = re.compile(r"^([01]\\d|2[0-3]):([0-5]\\d)$")
INTERVAL = re.compile(r"^(\\d{2}:\\d{2})-(\\d{2}:\\d{2})$")


def minutes(text):
    match = TIME.match(text)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def clock(total):
    return "{:02d}:{:02d}".format(total // 60, total % 60)


def main(argv):
    if len(argv) != 2:
        print("usage: main.py DAY_START DAY_END", file=sys.stderr)
        return 1

    start = minutes(argv[0])
    end = minutes(argv[1])
    if start is None or end is None:
        print("day boundaries must be HH:MM times", file=sys.stderr)
        return 1
    if end <= start:
        print("DAY_END must be after DAY_START", file=sys.stderr)
        return 1

    busy = []
    for raw in sys.stdin.read().splitlines():
        line = raw.strip()
        if not line:
            continue
        match = INTERVAL.match(line)
        if not match:
            print("malformed interval: " + line, file=sys.stderr)
            return 1
        begin = minutes(match.group(1))
        finish = minutes(match.group(2))
        if begin is None or finish is None:
            print("bad time in: " + line, file=sys.stderr)
            return 1
        if finish < begin:
            print("interval ends before it starts: " + line, file=sys.stderr)
            return 1
        begin, finish = max(begin, start), min(finish, end)
        if begin < finish:
            busy.append((begin, finish))

    busy.sort()
    merged = []
    for begin, finish in busy:
        if merged and begin <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], finish))
        else:
            merged.append((begin, finish))

    free = []
    cursor = start
    for begin, finish in merged:
        if begin > cursor:
            free.append((cursor, begin))
        cursor = max(cursor, finish)
    if cursor < end:
        free.append((cursor, end))

    if not free:
        print("none")
    else:
        for begin, finish in free:
            print("{}-{}".format(clock(begin), clock(finish)))
    return 0


sys.exit(main(sys.argv[1:]))
'''

EXPR_EVAL = '''const fs = require("fs");

function fail(message) {
  process.stderr.write(message + "\\n");
  process.exit(1);
}

const text = fs.readFileSync(0, "utf8");
const tokens = [];
let i = 0;
while (i < text.length) {
  const ch = text[i];
  if (/\\s/.test(ch)) {
    i += 1;
  } else if (/\\d/.test(ch)) {
    let j = i;
    while (j < text.length && /\\d/.test(text[j])) {
      j += 1;
    }
    tokens.push({ kind: "number", value: parseInt(text.slice(i, j), 10) });
    i = j;
  } else if ("+-*/()".includes(ch)) {
    tokens.push({ kind: ch });
    i += 1;
  } else {
    fail("unexpected character: " + ch);
  }
}
if (tokens.length === 0) {
  fail("empty expression");
}

let pos = 0;
const peek = () => (pos < tokens.length ? tokens[pos].kind : null);

function parseFactor() {
  const kind = peek();
  if (kind === "-") {
    pos += 1;
    return -parseFactor();
  }
  if (kind === "+") {
    pos += 1;
    return parseFactor();
  }
  if (kind === "number") {
    return tokens[pos++].value;
  }
  if (kind === "(") {
    pos += 1;
    const value = parseExpression();
    if (peek() !== ")") {
      fail("unbalanced parenthesis");
    }
    pos += 1;
    return value;
  }
  return fail("malformed expression");
}

function parseTerm() {
  let value = parseFactor();
  while (peek() === "*" || peek() === "/") {
    const op = tokens[pos++].kind;
    const right = parseFactor();
    if (op === "*") {
      value = value * right;
    } else {
      if (right === 0) {
        fail("division by zero");
      }
      value = Math.trunc(value / right);
    }
  }
  return value;
}

function parseExpression() {
  let value = parseTerm();
  while (peek() === "+" || peek() === "-") {
    const op = tokens[pos++].kind;
    const right = parseTerm();
    value = op === "+" ? value + right : value - right;
  }
  return value;
}

const result = parseExpression();
if (pos !== tokens.length) {
  fail("trailing input");
}
console.log(String(result));
'''

TEXT_JUSTIFY = '''import sys


def main(argv):
    if len(argv) != 1:
        print("usage: main.py WIDTH", file=sys.stderr)
        return 1
    try:
        width = int(argv[0])
    except ValueError:
        print("WIDTH must be an integer", file=sys.stderr)
        return 1
    if width < 1:
        print("WIDTH must be at least 1", file=sys.stderr)
        return 1

    words = sys.stdin.read().split()
    if not words:
        return 0

    longest = max(len(w) for w in words)
    if longest > width:
        print("word longer than the width: {} > {}".format(longest, width),
              file=sys.stderr)
        return 1

    lines = []
    current = []
    length = 0
    for word in words:
        if current and length + len(current) + len(word) > width:
            lines.append(current)
            current, length = [], 0
        current.append(word)
        length += len(word)
    if current:
        lines.append(current)

    rendered = []
    for index, line in enumerate(lines):
        if index == len(lines) - 1 or len(line) == 1:
            text = " ".join(line)
            rendered.append(text + " " * (width - len(text)))
            continue
        spaces = width - sum(len(w) for w in line)
        gaps = len(line) - 1
        base, extra = divmod(spaces, gaps)
        pieces = []
        for position, word in enumerate(line[:-1]):
            pieces.append(word)
            pieces.append(" " * (base + (1 if position < extra else 0)))
        pieces.append(line[-1])
        rendered.append("".join(pieces))

    print("\\n".join(rendered))
    return 0


sys.exit(main(sys.argv[1:]))
'''

SHORTEST_PATH = '''const fs = require("fs");

function fail(message) {
  process.stderr.write(message + "\\n");
  process.exit(1);
}

const lines = fs.readFileSync(0, "utf8")
  .split(/\\r?\\n/)
  .filter((line) => line.trim() !== "");
if (lines.length === 0) {
  fail("empty input");
}

const first = lines[0].trim().split(/\\s+/);
if (first.length !== 2) {
  fail("first line must name two nodes");
}
const start = first[0];
const end = first[1];

const adjacency = new Map();
const touch = (node) => {
  if (!adjacency.has(node)) {
    adjacency.set(node, []);
  }
};

for (const raw of lines.slice(1)) {
  const parts = raw.trim().split(/\\s+/);
  if (parts.length !== 3) {
    fail("malformed edge: " + raw.trim());
  }
  if (!/^\\d+$/.test(parts[2])) {
    fail("weight must be a non-negative integer: " + parts[2]);
  }
  const weight = parseInt(parts[2], 10);
  touch(parts[0]);
  touch(parts[1]);
  adjacency.get(parts[0]).push([parts[1], weight]);
  adjacency.get(parts[1]).push([parts[0], weight]);
}

if (!adjacency.has(start)) {
  fail("not a node of the graph: " + start);
}
if (!adjacency.has(end)) {
  fail("not a node of the graph: " + end);
}

function comparePaths(left, right) {
  const shared = Math.min(left.length, right.length);
  for (let i = 0; i < shared; i++) {
    if (left[i] !== right[i]) {
      return left[i] < right[i] ? -1 : 1;
    }
  }
  return left.length - right.length;
}

function better(candidate, known) {
  if (!known) {
    return true;
  }
  if (candidate.dist !== known.dist) {
    return candidate.dist < known.dist;
  }
  return comparePaths(candidate.path, known.path) < 0;
}

const best = new Map([[start, { dist: 0, path: [start] }]]);
const settled = new Set();

for (;;) {
  let node = null;
  for (const [name, entry] of best) {
    if (settled.has(name)) {
      continue;
    }
    if (node === null || better(entry, best.get(node))) {
      node = name;
    }
  }
  if (node === null) {
    break;
  }
  settled.add(node);
  const here = best.get(node);
  for (const [next, weight] of adjacency.get(node)) {
    const candidate = { dist: here.dist + weight,
                        path: here.path.concat([next]) };
    if (better(candidate, best.get(next))) {
      best.set(next, candidate);
    }
  }
}

const answer = best.get(end);
if (!answer || !settled.has(end)) {
  console.log("unreachable");
  process.exit(0);
}
console.log("dist: " + answer.dist);
console.log("path: " + answer.path.join(" -> "));
'''


SOURCES: Dict[str, str] = {
    "fizzbuzz": FIZZBUZZ,
    "word-count": WORD_COUNT,
    "sum-args": SUM_ARGS,
    "reverse-words": REVERSE_WORDS,
    "roman-numerals": ROMAN_NUMERALS,
    "palindrome": PALINDROME,
    "gcd-lcm": GCD_LCM,
    "rpn-calculator": RPN,
    "csv-column-stats": CSV_STATS,
    "balanced-brackets": BRACKETS,
    "run-length-encoding": RLE,
    "top-k-words": TOP_K_WORDS,
    "date-diff": DATE_DIFF,
    "matrix-spiral": MATRIX_SPIRAL,
    "ini-to-json": INI_TO_JSON,
    "json-query": JSON_QUERY,
    "meeting-free-slots": FREE_SLOTS,
    "expression-eval": EXPR_EVAL,
    "text-justify": TEXT_JUSTIFY,
    "shortest-path": SHORTEST_PATH,
}


def files_for(slug: str, source: Optional[str] = None
               ) -> List[Dict[str, str]]:
    """The reference solution as the engine would hand it to the sandbox."""
    task: BenchTask = BY_SLUG[slug]
    return [{
        "path": task.entry_path,
        "language": task.language,
        "content": SOURCES[slug] if source is None else source,
    }]


def all_files() -> Dict[str, List[Dict[str, str]]]:
    return {slug: files_for(slug) for slug in SOURCES}


#: a program that starts cleanly and does nothing useful.  Used to prove the
#: hidden tests are not vacuous: if this scores above zero on a task, that
#: task's tests are satisfied by a program that solves nothing.
DEGENERATE = {
    "python": "import sys\nsys.stdin.read()\n",
    "javascript": 'try { require("fs").readFileSync(0, "utf8"); } catch (e) {}\n',
}


def degenerate_files_for(slug: str) -> List[Dict[str, str]]:
    task: BenchTask = BY_SLUG[slug]
    return [{"path": task.entry_path, "language": task.language,
             "content": DEGENERATE[task.language]}]
