"""The benchmark suite: 20 tasks with hidden tests.

Week 9, and the thing that makes Phase 4 an experiment rather than a demo.

Three properties matter, and each one is here for a reason the proposal calls
out:

**The tests are hidden.**  `BenchTask.prompt` is the *only* field any agent is
ever shown.  `tests` is never rendered into a prompt, which is what decouples
scoring from the LLM reviewer - the proposal's stated answer to "the reviewer
is fallible".  A run can be approved by the Reviewer and still score zero.

**The contract is explicit.**  Each prompt states the invocation, the exact
output format and the error behaviour.  That is not hand-holding: if the prompt
left the output format open, a correct program could fail a string comparison
and we would be measuring guesswork about formatting rather than correctness.
The difficulty lives in the algorithm, not in divining the I/O shape.

**Nothing depends on byte counts of stdin.**  Text is handed to the child
process through a pipe, and the newline translation differs between the
developer machines and the Linux CI runner.  Tests assert on words, lines and
values, never on the length of the raw input.

Difficulty follows the proposal: 7 easy, 8 medium, 5 hard, across Python and
JavaScript.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

DIFFICULTIES = ("easy", "medium", "hard")
LANGUAGES = ("python", "javascript")


@dataclass(frozen=True)
class HiddenTest:
    """One assertion about a program, never shown to any agent.

    Deliberately the same shape as `agents.checks.AcceptanceCheck`: a hidden
    test and an acceptance check make the same kind of claim about a program.
    They are separate types because they have opposite visibility rules - an
    acceptance check is written *into* the prompt by the Product Manager, and a
    hidden test must never appear in one.
    """

    name: str
    argv: Tuple[str, ...] = ()
    stdin: str = ""
    expect_stdout: Optional[str] = None
    match: str = "exact"                  # exact | contains | regex
    expect_exit: Optional[int] = 0

    def describe(self) -> str:
        call = " ".join(self.argv) if self.argv else "(no arguments)"
        if self.stdin:
            first = self.stdin.splitlines()[0] if self.stdin.strip() else ""
            call += f"  <stdin: {first[:30]!r}...>" if len(self.stdin) > 30 \
                else f"  <stdin: {self.stdin!r}>"
        return call


@dataclass(frozen=True)
class BenchTask:
    slug: str
    title: str
    difficulty: str
    language: str
    prompt: str
    tests: Tuple[HiddenTest, ...]

    def __post_init__(self) -> None:
        if self.difficulty not in DIFFICULTIES:
            raise ValueError(f"{self.slug}: bad difficulty {self.difficulty!r}")
        if self.language not in LANGUAGES:
            raise ValueError(f"{self.slug}: bad language {self.language!r}")
        if len(self.tests) < 3:
            raise ValueError(f"{self.slug}: needs at least 3 hidden tests")

    @property
    def entry_path(self) -> str:
        return "src/main.py" if self.language == "python" else "src/main.js"


def _t(name, argv=(), stdin="", out=None, match="exact", exit_code=0):
    return HiddenTest(name=name, argv=tuple(argv), stdin=stdin,
                      expect_stdout=out, match=match, expect_exit=exit_code)


# ============================================================ easy (7)
FIZZBUZZ = BenchTask(
    slug="fizzbuzz",
    title="FizzBuzz to N",
    difficulty="easy",
    language="python",
    prompt="""Write a Python command-line program.

Usage: main.py N

Print the integers from 1 to N inclusive, one per line, except that multiples
of 3 print "Fizz", multiples of 5 print "Buzz", and multiples of both print
"FizzBuzz".

If N is missing, not an integer, or less than 1, print an error message to
stderr and exit with status 1. Otherwise exit with status 0.""",
    tests=(
        _t("first five", ["5"], out="1\n2\nFizz\n4\nBuzz"),
        _t("n=1", ["1"], out="1"),
        _t("fifteen ends in FizzBuzz", ["15"], out="FizzBuzz", match="contains"),
        _t("fifteen has 15 lines", ["15"],
           out=r"\A1\n2\nFizz\n4\nBuzz\nFizz\n7\n8\nFizz\nBuzz\n11\nFizz\n13\n14\nFizzBuzz\Z",
           match="regex"),
        _t("missing argument", [], exit_code=1),
        _t("not a number", ["abc"], exit_code=1),
        _t("zero is rejected", ["0"], exit_code=1),
    ),
)

WORD_COUNT = BenchTask(
    slug="word-count",
    title="Count lines and words on standard input",
    difficulty="easy",
    language="python",
    prompt="""Write a Python command-line program.

Read all of standard input and print exactly two lines:

    lines: L
    words: W

L is the number of lines in the input. W is the number of whitespace-separated
words. Empty input gives 0 and 0. Exit with status 0.""",
    tests=(
        _t("one line", stdin="hello world\n", out="lines: 1\nwords: 2"),
        _t("empty input", stdin="", out="lines: 0\nwords: 0"),
        _t("two lines", stdin="a b c\nd e\n", out="lines: 2\nwords: 5"),
        _t("runs of spaces are one separator",
           stdin="   spaced    out   \n", out="lines: 1\nwords: 2"),
        _t("no trailing newline", stdin="one two", out="lines: 1\nwords: 2"),
    ),
)

SUM_ARGS = BenchTask(
    slug="sum-args",
    title="Sum the integer arguments",
    difficulty="easy",
    language="javascript",
    prompt="""Write a Node.js command-line program.

Usage: main.js [N ...]

Print the sum of the integer arguments on one line. With no arguments print 0.

If any argument is not a valid integer, print an error message to stderr and
exit with status 1. Otherwise exit with status 0.""",
    tests=(
        _t("three numbers", ["1", "2", "3"], out="6"),
        _t("no arguments", [], out="0"),
        _t("negatives cancel", ["-5", "5"], out="0"),
        _t("one number", ["10"], out="10"),
        _t("rejects a non-integer", ["4", "x"], exit_code=1),
        _t("rejects a float", ["1.5"], exit_code=1),
    ),
)

REVERSE_WORDS = BenchTask(
    slug="reverse-words",
    title="Reverse the words on each line",
    difficulty="easy",
    language="python",
    prompt="""Write a Python command-line program.

Read all of standard input. For each line, print the same words in reverse
order, separated by single spaces. Leading, trailing and repeated spaces in the
input are not preserved. Blank lines print as blank lines. Exit with status 0.""",
    tests=(
        _t("two words", stdin="hello world\n", out="world hello"),
        _t("two lines", stdin="one two three\nfour five\n",
           out="three two one\nfive four"),
        _t("single word", stdin="single\n", out="single"),
        _t("extra spaces collapse", stdin="  a   b  \n", out="b a"),
        _t("empty input", stdin="", out=""),
    ),
)

ROMAN_NUMERALS = BenchTask(
    slug="roman-numerals",
    title="Integer to Roman numeral",
    difficulty="easy",
    language="javascript",
    prompt="""Write a Node.js command-line program.

Usage: main.js N

Print the Roman numeral for the integer N in uppercase, using the standard
subtractive forms (IV, IX, XL, XC, CD, CM).

N must be an integer from 1 to 3999 inclusive. If it is missing, not an
integer, or out of range, print an error message to stderr and exit with
status 1. Otherwise exit with status 0.""",
    tests=(
        _t("one", ["1"], out="I"),
        _t("fifty-eight", ["58"], out="LVIII"),
        _t("subtractive forms", ["1994"], out="MCMXCIV"),
        _t("maximum", ["3999"], out="MMMCMXCIX"),
        _t("four hundred", ["400"], out="CD"),
        _t("zero is rejected", ["0"], exit_code=1),
        _t("four thousand is rejected", ["4000"], exit_code=1),
        _t("rejects a non-integer", ["xiv"], exit_code=1),
        _t("rejects a missing argument", [], exit_code=1),
    ),
)

PALINDROME = BenchTask(
    slug="palindrome",
    title="Palindrome check ignoring case and punctuation",
    difficulty="easy",
    language="python",
    prompt="""Write a Python command-line program.

Usage: main.py TEXT

Print "yes" if TEXT is a palindrome and "no" if it is not. Compare only
alphanumeric characters and ignore case.

If the argument is missing, print an error message to stderr and exit with
status 1. Otherwise exit with status 0.""",
    tests=(
        _t("classic phrase", ["A man, a plan, a canal: Panama"], out="yes"),
        _t("not a palindrome", ["hello"], out="no"),
        _t("mixed case", ["RaceCar"], out="yes"),
        _t("two letters differ", ["ab"], out="no"),
        _t("digits count", ["12321"], out="yes"),
        _t("missing argument", [], exit_code=1),
    ),
)

GCD_LCM = BenchTask(
    slug="gcd-lcm",
    title="Greatest common divisor and least common multiple",
    difficulty="easy",
    language="javascript",
    prompt="""Write a Node.js command-line program.

Usage: main.js A B

Print exactly two lines:

    gcd: G
    lcm: L

G is the greatest common divisor of the non-negative integers A and B, and L is
their least common multiple. Treat gcd(0, n) as n, and define the lcm as 0
whenever either input is 0.

If an argument is missing, not an integer, or negative, print an error message
to stderr and exit with status 1. Otherwise exit with status 0.""",
    tests=(
        _t("twelve and eighteen", ["12", "18"], out="gcd: 6\nlcm: 36"),
        _t("coprime", ["7", "13"], out="gcd: 1\nlcm: 91"),
        _t("zero", ["0", "5"], out="gcd: 5\nlcm: 0"),
        _t("equal inputs", ["9", "9"], out="gcd: 9\nlcm: 9"),
        _t("both zero", ["0", "0"], out="gcd: 0\nlcm: 0"),
        _t("rejects a non-integer", ["x", "1"], exit_code=1),
        _t("rejects a second non-integer", ["1", "x"], exit_code=1),
        _t("rejects a negative", ["-4", "2"], exit_code=1),
    ),
)

# ========================================================== medium (8)
RPN = BenchTask(
    slug="rpn-calculator",
    title="Reverse Polish notation calculator",
    difficulty="medium",
    language="python",
    prompt="""Write a Python command-line program.

Read one reverse-Polish expression from standard input: whitespace-separated
integers and the operators + - * /. Print the integer result on one line.

All arithmetic is on integers. Division truncates toward zero, so 7 2 / is 3
and -7 2 / is -3.

Print an error message to stderr and exit with status 1 if the expression is
empty, if an operator finds fewer than two operands on the stack, if more than
one value remains at the end, if a token is neither an integer nor an operator,
or if a division by zero occurs. Otherwise exit with status 0.""",
    tests=(
        _t("simple addition", stdin="3 4 +\n", out="7"),
        _t("nested expression", stdin="5 1 2 + 4 * + 3 -\n", out="14"),
        _t("division truncates down", stdin="7 2 /\n", out="3"),
        _t("division truncates toward zero", stdin="-7 2 /\n", out="-3"),
        _t("single value", stdin="42\n", out="42"),
        _t("stack underflow", stdin="1 +\n", exit_code=1),
        _t("leftover operands", stdin="1 2 3 +\n", exit_code=1),
        _t("division by zero", stdin="4 0 /\n", exit_code=1),
        _t("empty expression", stdin="\n", exit_code=1),
        _t("bad token", stdin="1 2 ^\n", exit_code=1),
    ),
)

CSV_STATS = BenchTask(
    slug="csv-column-stats",
    title="Statistics for one CSV column",
    difficulty="medium",
    language="python",
    prompt="""Write a Python command-line program.

Usage: main.py COLUMN

Read a comma-separated table from standard input. The first line is a header
row of column names. Print exactly four lines of statistics for the named
column:

    count: N
    min: MIN
    max: MAX
    mean: MEAN

MIN and MAX are printed as integers when the value is a whole number and
otherwise with its decimals as parsed. MEAN is always printed with exactly two
decimal places.

Print an error message to stderr and exit with status 1 if the column name is
missing or not in the header, if the table has no data rows, or if any value in
that column is not a number. Otherwise exit with status 0.""",
    tests=(
        _t("three rows", ["score"], stdin="name,score\na,10\nb,20\nc,30\n",
           out="count: 3\nmin: 10\nmax: 30\nmean: 20.00"),
        _t("one row", ["v"], stdin="v\n5\n",
           out="count: 1\nmin: 5\nmax: 5\nmean: 5.00"),
        _t("mean needs rounding", ["v"], stdin="v\n1\n2\n",
           out="count: 2\nmin: 1\nmax: 2\nmean: 1.50"),
        _t("second column", ["b"], stdin="a,b\n1,9\n2,3\n",
           out="count: 2\nmin: 3\nmax: 9\nmean: 6.00"),
        _t("unknown column", ["nope"], stdin="a,b\n1,2\n", exit_code=1),
        _t("row shorter than the column", ["b"],
           stdin="a,b\n1,2\n3\n", exit_code=1),
        _t("no data rows", ["a"], stdin="a,b\n", exit_code=1),
        _t("non-numeric value", ["a"], stdin="a\n1\nx\n", exit_code=1),
    ),
)

BRACKETS = BenchTask(
    slug="balanced-brackets",
    title="Find the first unbalanced bracket",
    difficulty="medium",
    language="javascript",
    prompt="""Write a Node.js command-line program.

Read one line from standard input, ignoring the trailing newline. The line
contains the bracket characters ( ) [ ] { } and possibly other characters,
which are ignored.

If every bracket is correctly matched and nested, print "balanced".

Otherwise print:

    unbalanced at index N

N is the 0-based index of the first closing bracket that does not match the
most recent unclosed opening bracket, or that has no opening bracket at all. If
the line ends while brackets are still open, N is the length of the line.

Exit with status 0 either way.""",
    tests=(
        _t("all three kinds", stdin="([]{})\n", out="balanced"),
        _t("empty line", stdin="\n", out="balanced"),
        _t("mismatched pair", stdin="(]\n", out="unbalanced at index 1"),
        _t("unclosed at end", stdin="(()\n", out="unbalanced at index 3"),
        _t("closer with no opener", stdin=")\n", out="unbalanced at index 0"),
        _t("other characters ignored", stdin="a(b[c]d)e\n", out="balanced"),
        _t("wrong nesting order", stdin="([)]\n", out="unbalanced at index 2"),
    ),
)

RLE = BenchTask(
    slug="run-length-encoding",
    title="Run-length encode and decode",
    difficulty="medium",
    language="python",
    prompt="""Write a Python command-line program.

Usage: main.py encode
       main.py decode

Read one line from standard input, ignoring the trailing newline.

In encode mode, replace each run of identical characters with the character
followed by the length of the run, so "aaabbc" becomes "a3b2c1". Every
character gets a count, including runs of length 1.

In decode mode, reverse that transformation.

Print an error message to stderr and exit with status 1 if the mode is missing
or is not "encode" or "decode", or if decode input is malformed - a character
not followed by a positive integer count. Empty input produces empty output in
both modes. Otherwise exit with status 0.""",
    tests=(
        _t("encode runs", ["encode"], stdin="aaabbc\n", out="a3b2c1"),
        _t("encode singles", ["encode"], stdin="abc\n", out="a1b1c1"),
        _t("decode", ["decode"], stdin="a3b2c1\n", out="aaabbc"),
        _t("decode multi-digit", ["decode"], stdin="a12\n", out="aaaaaaaaaaaa"),
        _t("encode empty", ["encode"], stdin="\n", out=""),
        _t("round trip", ["decode"], stdin="x1y1z1\n", out="xyz"),
        _t("missing mode", [], exit_code=1),
        _t("bad mode", ["sideways"], exit_code=1),
        _t("malformed decode", ["decode"], stdin="a\n", exit_code=1),
        _t("zero count is malformed", ["decode"], stdin="a0\n", exit_code=1),
    ),
)

TOP_K_WORDS = BenchTask(
    slug="top-k-words",
    title="The k most frequent words",
    difficulty="medium",
    language="python",
    prompt="""Write a Python command-line program.

Usage: main.py K

Read all of standard input and print the K most frequent words, one per line,
formatted as:

    word: count

A word is a maximal run of letters, digits and apostrophes. Compare words in
lower case. Order by descending count, and break ties by the word in ascending
alphabetical order. If K is larger than the number of distinct words, print
them all. K may be 0, which prints nothing.

If K is missing, not an integer, or negative, print an error message to stderr
and exit with status 1. Otherwise exit with status 0.""",
    tests=(
        _t("top two", ["2"], stdin="the cat the dog the bird cat\n",
           out="the: 3\ncat: 2"),
        _t("case is folded", ["1"], stdin="Hello, hello world!\n",
           out="hello: 2"),
        _t("ties are alphabetical", ["3"], stdin="b a c\n",
           out="a: 1\nb: 1\nc: 1"),
        _t("k above the vocabulary", ["10"], stdin="one two\n",
           out="one: 1\ntwo: 1"),
        _t("k is zero", ["0"], stdin="a b c\n", out=""),
        _t("apostrophes stay in the word", ["1"], stdin="don't don't stop\n",
           out="don't: 2"),
        _t("ranks by count before alphabet", ["3"],
           stdin="zebra zebra zebra apple apple mango\n",
           out="zebra: 3\napple: 2\nmango: 1"),
        _t("negative k", ["-1"], exit_code=1),
        _t("missing k", [], exit_code=1),
    ),
)

DATE_DIFF = BenchTask(
    slug="date-diff",
    title="Days between two dates",
    difficulty="medium",
    language="javascript",
    prompt="""Write a Node.js command-line program.

Usage: main.js YYYY-MM-DD YYYY-MM-DD

Print the number of whole days between the two dates as a non-negative integer,
regardless of which order they are given in.

Print an error message to stderr and exit with status 1 if either argument is
missing or is not a valid calendar date in YYYY-MM-DD form. Otherwise exit with
status 0.""",
    tests=(
        _t("within a month", ["2024-01-01", "2024-01-31"], out="30"),
        _t("leap february", ["2024-03-01", "2024-02-01"], out="29"),
        _t("non-leap february", ["2023-03-01", "2023-02-01"], out="28"),
        _t("same day", ["2024-01-01", "2024-01-01"], out="0"),
        _t("across a year", ["2023-12-31", "2024-01-01"], out="1"),
        _t("rejects nonsense", ["bad", "2024-01-01"], exit_code=1),
        _t("rejects an impossible date", ["2023-02-30", "2023-03-01"],
           exit_code=1),
        _t("rejects an impossible month", ["2023-13-01", "2023-03-01"],
           exit_code=1),
        _t("rejects a missing second date", ["2023-01-01"], exit_code=1),
    ),
)

MATRIX_SPIRAL = BenchTask(
    slug="matrix-spiral",
    title="Spiral order traversal",
    difficulty="medium",
    language="python",
    prompt="""Write a Python command-line program.

Read a matrix from standard input: one row per line, integers separated by
whitespace. Print the elements in clockwise spiral order starting at the
top-left, separated by single spaces, on one line.

Empty input prints an empty line and exits with status 0.

Print an error message to stderr and exit with status 1 if the rows are not all
the same length, or if a value is not an integer.""",
    tests=(
        _t("three by three", stdin="1 2 3\n4 5 6\n7 8 9\n",
           out="1 2 3 6 9 8 7 4 5"),
        _t("two by two", stdin="1 2\n3 4\n", out="1 2 4 3"),
        _t("single element", stdin="1\n", out="1"),
        _t("one row", stdin="1 2 3 4\n", out="1 2 3 4"),
        _t("one column", stdin="1\n2\n3\n", out="1 2 3"),
        _t("four by three", stdin="1 2 3\n4 5 6\n7 8 9\n10 11 12\n",
           out="1 2 3 6 9 12 11 10 7 4 5 8"),
        _t("empty input", stdin="", out=""),
        _t("ragged rows", stdin="1 2\n3\n", exit_code=1),
        _t("non-integer", stdin="1 x\n", exit_code=1),
    ),
)

INI_TO_JSON = BenchTask(
    slug="ini-to-json",
    title="INI to JSON",
    difficulty="medium",
    language="javascript",
    prompt="""Write a Node.js command-line program.

Read an INI document from standard input and print it as JSON.

A section header is a line "[name]". A property is a line "key=value". Keys and
values are trimmed of surrounding whitespace, and every value is a JSON string.
Blank lines are ignored, and so are comment lines whose first non-space
character is ";" or "#".

Print the result as JSON with two-space indentation, with the section names and
the keys inside each section both in ascending alphabetical order. Exactly the
output of JSON.stringify(object, null, 2) for an object built in that order.

Print an error message to stderr and exit with status 1 if a property appears
before any section header, or if a non-blank, non-comment line is neither a
section header nor a key=value property. Otherwise exit with status 0.""",
    tests=(
        _t("sections are sorted", stdin="[b]\nx=1\n[a]\ny=2\n",
           out='{\n  "a": {\n    "y": "2"\n  },\n  "b": {\n    "x": "1"\n  }\n}'),
        _t("keys are sorted", stdin="[s]\nz=1\na=2\n",
           out='{\n  "s": {\n    "a": "2",\n    "z": "1"\n  }\n}'),
        _t("whitespace is trimmed", stdin="[s]\n  k  =  v  \n",
           out='{\n  "s": {\n    "k": "v"\n  }\n}'),
        _t("comments ignored", stdin="; note\n[s]\n# also\nk=v\n",
           out='{\n  "s": {\n    "k": "v"\n  }\n}'),
        _t("empty section", stdin="[s]\n", out='{\n  "s": {}\n}'),
        _t("value keeps inner equals", stdin="[s]\nk=a=b\n",
           out='{\n  "s": {\n    "k": "a=b"\n  }\n}'),
        _t("property before a section", stdin="k=v\n", exit_code=1),
        _t("garbage line", stdin="[s]\nnonsense\n", exit_code=1),
    ),
)

# ============================================================ hard (5)
JSON_QUERY = BenchTask(
    slug="json-query",
    title="Query a JSON document by path",
    difficulty="hard",
    language="python",
    prompt="""Write a Python command-line program.

Usage: main.py PATH

Read a JSON document from standard input and print the value at PATH as
compact JSON - no spaces after separators, exactly what
json.dumps(value, separators=(",", ":")) produces.

A path is dot-separated object keys, where any key may be followed by one or
more bracketed array indices: "a.b", "a.b[1]", "items[0].name",
"grid[1][2]". An empty path refers to the whole document.

Print an error message to stderr and exit with status 1 if standard input is
not valid JSON, if the path is malformed, if a key is missing, if an index is
out of range, or if the path indexes into something that is not an object or
array as required. Otherwise exit with status 0.""",
    tests=(
        _t("nested key", ["a.b"], stdin='{"a":{"b":[1,2,3]}}', out="[1,2,3]"),
        _t("array index", ["a.b[1]"], stdin='{"a":{"b":[1,2,3]}}', out="2"),
        _t("string value is quoted", ["x"], stdin='{"x":"hi"}', out='"hi"'),
        _t("index then key", ["items[0].name"],
           stdin='{"items":[{"name":"first"},{"name":"second"}]}',
           out='"first"'),
        _t("two indices", ["grid[1][2]"],
           stdin='{"grid":[[1,2,3],[4,5,6]]}', out="6"),
        _t("empty path is the document", [""], stdin='{"a":1}', out='{"a":1}'),
        _t("compact separators", ["a"], stdin='{"a":{"b":1,"c":2}}',
           out='{"b":1,"c":2}'),
        _t("null is a value", ["a"], stdin='{"a":null}', out="null"),
        _t("missing key", ["a.zz"], stdin='{"a":{"b":1}}', exit_code=1),
        _t("index out of range", ["a[9]"], stdin='{"a":[1]}', exit_code=1),
        _t("index one past the end", ["a[1]"], stdin='{"a":[1]}',
           exit_code=1),
        _t("indexing an object", ["a[0]"], stdin='{"a":{"b":1}}', exit_code=1),
        _t("invalid json", ["a"], stdin="not json", exit_code=1),
    ),
)

FREE_SLOTS = BenchTask(
    slug="meeting-free-slots",
    title="Free slots in a busy day",
    difficulty="hard",
    language="python",
    prompt="""Write a Python command-line program.

Usage: main.py DAY_START DAY_END

Both arguments are times in HH:MM form on a 24-hour clock. Read zero or more
busy intervals from standard input, one per line, each "HH:MM-HH:MM". The
intervals may overlap and may arrive in any order, and parts of them may fall
outside the working day.

Print the free intervals inside the working day, in ascending order, one per
line, each formatted "HH:MM-HH:MM". Zero-length gaps are not free intervals. If
there is no free time at all, print "none".

Print an error message to stderr and exit with status 1 if an argument or an
input line is not in the required form, if a time is not a valid 24-hour time,
if an interval ends before it starts, or if DAY_END is not after DAY_START.
Otherwise exit with status 0.""",
    tests=(
        _t("two gaps", ["09:00", "13:00"], stdin="09:00-10:00\n11:00-12:00\n",
           out="10:00-11:00\n12:00-13:00"),
        _t("overlapping busy merges", ["09:00", "13:00"],
           stdin="09:00-11:00\n10:00-12:00\n", out="12:00-13:00"),
        _t("unsorted input", ["09:00", "13:00"],
           stdin="11:00-12:00\n09:00-10:00\n", out="10:00-11:00\n12:00-13:00"),
        _t("nothing busy", ["09:00", "13:00"], stdin="", out="09:00-13:00"),
        _t("fully busy", ["09:00", "13:00"], stdin="08:00-14:00\n", out="none"),
        _t("busy outside the day is clipped", ["09:00", "13:00"],
           stdin="07:00-09:30\n12:30-15:00\n", out="09:30-12:30"),
        _t("adjacent intervals leave no gap", ["09:00", "11:00"],
           stdin="09:00-10:00\n10:00-11:00\n", out="none"),
        _t("gap before the first meeting", ["08:00", "10:00"],
           stdin="09:00-09:30\n", out="08:00-09:00\n09:30-10:00"),
        # a zero-length busy interval is not "ends before it starts", so it is
        # accepted and simply blocks nothing.  Mutation testing found this
        # boundary untested.
        _t("zero-length busy interval is ignored", ["09:00", "10:00"],
           stdin="09:30-09:30\n", out="09:00-10:00"),
        _t("bad time", ["09:00", "25:00"], exit_code=1),
        _t("backwards interval", ["09:00", "13:00"], stdin="11:00-10:00\n",
           exit_code=1),
        _t("malformed line", ["09:00", "13:00"], stdin="morning\n",
           exit_code=1),
        _t("day ends before it starts", ["13:00", "09:00"], exit_code=1),
        # likewise: DAY_END must be *after* DAY_START, so equal is rejected
        _t("empty working day", ["09:00", "09:00"], exit_code=1),
    ),
)

EXPR_EVAL = BenchTask(
    slug="expression-eval",
    title="Evaluate an infix expression",
    difficulty="hard",
    language="javascript",
    prompt="""Write a Node.js command-line program.

Read one arithmetic expression from standard input and print its integer value
on one line.

The expression contains non-negative integer literals, the binary operators
+ - * /, unary minus, parentheses, and arbitrary whitespace. Multiplication and
division bind tighter than addition and subtraction, operators of equal
precedence associate left to right, and parentheses override both. All
arithmetic is on integers, and division truncates toward zero.

Print an error message to stderr and exit with status 1 if the expression is
empty, malformed, has unbalanced parentheses, contains an unexpected character,
or divides by zero. Otherwise exit with status 0.""",
    tests=(
        _t("precedence", stdin="2+3*4\n", out="14"),
        _t("parentheses override", stdin="(2+3)*4\n", out="20"),
        _t("division truncates", stdin="10/3\n", out="3"),
        _t("unary minus", stdin="-(2+3)\n", out="-5"),
        _t("left associative subtraction", stdin="10-3-2\n", out="5"),
        _t("left associative division", stdin="100/5/2\n", out="10"),
        _t("whitespace is ignored", stdin="  7  *  ( 1 + 1 )  \n", out="14"),
        _t("nested parentheses", stdin="((2))*((3))\n", out="6"),
        _t("negative truncates toward zero", stdin="-7/2\n", out="-3"),
        _t("trailing operator", stdin="2+\n", exit_code=1),
        _t("unbalanced parenthesis", stdin="2*(3+4\n", exit_code=1),
        _t("division by zero", stdin="100/0\n", exit_code=1),
        _t("empty expression", stdin="\n", exit_code=1),
        _t("unexpected character", stdin="2$3\n", exit_code=1),
    ),
)

TEXT_JUSTIFY = BenchTask(
    slug="text-justify",
    title="Fully justify text to a width",
    difficulty="hard",
    language="python",
    prompt="""Write a Python command-line program.

Usage: main.py WIDTH

Read all of standard input as whitespace-separated words and print them as
lines of exactly WIDTH characters.

Greedily pack as many words onto each line as fit with at least one space
between neighbours. Pad each line to WIDTH by distributing the extra spaces as
evenly as possible between the words, giving the leftmost gaps the extra space
when they do not divide evenly. A line holding a single word is left-justified
and padded on the right. The final line is left-justified with single spaces
between words and padded on the right.

Print an error message to stderr and exit with status 1 if WIDTH is missing,
not an integer, less than 1, or shorter than the longest word in the input.
Empty input prints nothing and exits with status 0.""",
    tests=(
        _t("classic example", ["16"],
           stdin="This is an example of text justification.\n",
           out="This    is    an\nexample  of text\njustification."),
        _t("extra space goes left", ["9"], stdin="a b c d\n",
           out="a b c d"),
        _t("single word per line", ["5"], stdin="alpha bravo\n",
           out="alpha\nbravo"),
        _t("one word padded right", ["8"], stdin="hello\n", out="hello"),
        _t("uneven gaps", ["10"], stdin="aa bb cc dd ee\n",
           out="aa  bb  cc\ndd ee"),
        # the trailing padding of the last line does not survive the strip
        # both sides of a comparison get, so this asserts the width of the
        # justified lines only
        _t("justified lines are exactly the width", ["16"],
           stdin="This is an example of text justification.\n",
           out=r"\A.{16}\n.{16}\n", match="regex"),
        _t("empty input", ["10"], stdin="", out=""),
        _t("width of one", ["1"], stdin="a b\n", out="a\nb"),
        _t("word longer than the width", ["3"], stdin="enormous\n",
           exit_code=1),
        _t("one long word among short ones", ["4"],
           stdin="a b enormous\n", exit_code=1),
        _t("width is not a number", ["wide"], stdin="a b\n", exit_code=1),
        _t("missing width", [], stdin="a b\n", exit_code=1),
    ),
)

SHORTEST_PATH = BenchTask(
    slug="shortest-path",
    title="Shortest path in a weighted graph",
    difficulty="hard",
    language="javascript",
    prompt="""Write a Node.js command-line program.

Read a graph from standard input. The first line is "START END". Each remaining
non-blank line is an undirected edge "A B W", where A and B are node names
without spaces and W is a non-negative integer weight.

Print the shortest total weight and the path:

    dist: D
    path: A -> B -> C

The path lists the node names from START to END separated by " -> ". When
several shortest paths exist, print the one that is alphabetically smallest as
a sequence of node names. If END cannot be reached from START, print
"unreachable" and exit with status 0. A path from a node to itself has distance
0 and a path of just that node.

Print an error message to stderr and exit with status 1 if the first line does
not name two nodes, if an edge line is malformed, if a weight is not a
non-negative integer, or if START or END is not a node of the graph. Otherwise
exit with status 0.""",
    tests=(
        _t("cheaper indirect route", stdin="A D\nA B 1\nB C 2\nA C 5\nC D 1\n",
           out="dist: 4\npath: A -> B -> C -> D"),
        _t("direct edge wins", stdin="A C\nA B 5\nB C 5\nA C 3\n",
           out="dist: 3\npath: A -> C"),
        _t("same node", stdin="A A\nA B 1\n", out="dist: 0\npath: A"),
        _t("unreachable", stdin="A C\nA B 1\nC D 1\n", out="unreachable"),
        _t("zero weights", stdin="A C\nA B 0\nB C 0\n",
           out="dist: 0\npath: A -> B -> C"),
        _t("alphabetical tie break", stdin="A D\nA B 1\nA C 1\nB D 1\nC D 1\n",
           out="dist: 2\npath: A -> B -> D"),
        _t("longer but cheaper", stdin="S T\nS A 1\nA B 1\nB T 1\nS T 10\n",
           out="dist: 3\npath: S -> A -> B -> T"),
        # a correct search must settle B before A even though A was
        # discovered first; mutation testing showed nothing else caught a
        # frontier that simply took nodes in discovery order
        _t("cheap detour found after an expensive edge",
           stdin="S T\nS A 10\nS B 1\nB A 1\nA T 1\n",
           out="dist: 3\npath: S -> B -> A -> T"),
        _t("unknown start", stdin="Z B\nA B 1\n", exit_code=1),
        _t("negative weight", stdin="A B\nA B -1\n", exit_code=1),
        _t("malformed edge", stdin="A B\nA B\n", exit_code=1),
        _t("first line names one node", stdin="A\nA B 1\n", exit_code=1),
    ),
)


TASKS: Tuple[BenchTask, ...] = (
    # easy
    FIZZBUZZ, WORD_COUNT, SUM_ARGS, REVERSE_WORDS, ROMAN_NUMERALS,
    PALINDROME, GCD_LCM,
    # medium
    RPN, CSV_STATS, BRACKETS, RLE, TOP_K_WORDS, DATE_DIFF, MATRIX_SPIRAL,
    INI_TO_JSON,
    # hard
    JSON_QUERY, FREE_SLOTS, EXPR_EVAL, TEXT_JUSTIFY, SHORTEST_PATH,
)

BY_SLUG: Dict[str, BenchTask] = {t.slug: t for t in TASKS}


def get(slug: str) -> BenchTask:
    try:
        return BY_SLUG[slug]
    except KeyError:
        raise KeyError(f"no benchmark task {slug!r}; "
                       f"known: {', '.join(sorted(BY_SLUG))}") from None


def select(difficulty: Optional[str] = None, language: Optional[str] = None,
           slugs: Optional[Sequence[str]] = None) -> List[BenchTask]:
    chosen = [get(s) for s in slugs] if slugs else list(TASKS)
    if difficulty:
        chosen = [t for t in chosen if t.difficulty == difficulty]
    if language:
        chosen = [t for t in chosen if t.language == language]
    return chosen


def composition() -> Dict[str, int]:
    counts: Dict[str, int] = {"tasks": len(TASKS), "tests": 0}
    for d in DIFFICULTIES:
        counts[d] = sum(1 for t in TASKS if t.difficulty == d)
    for lang in LANGUAGES:
        counts[lang] = sum(1 for t in TASKS if t.language == lang)
    counts["tests"] = sum(len(t.tests) for t in TASKS)
    return counts
