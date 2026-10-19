"""
MAWE - Multi-Agent AI Workflow Engine
Week 1-2 prototype (milestone M1).

Runs the PM -> Developer -> Reviewer state graph end to end with a scripted
mock LLM, so the orchestration, loop-prevention and persistence layers can be
exercised with no API key and no cost.  This is the "integration tests with a
mocked LLM" step from the proposal's testing strategy (section 9.3): it
measures the ENGINE, not model quality.  Swap MockLLM for a real API client
to get model quality numbers in Phase 4.

    python mawe_prototype.py          # run the three demo scenarios
    python mawe_prototype.py --db     # ...and dump what landed in SQLite

Marco Perozo, Gabriel Marte, Lewdy Aquino, Alvin Almonte
"""

import argparse
import hashlib
import sqlite3
import textwrap
import time

DB_PATH = "mawe.db"
MAX_ITERATIONS = 5

# --------------------------------------------------------------------------
# persistence layer  (subset of the full schema in the proposal, section 7)
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt             TEXT    NOT NULL,
    mode               TEXT    NOT NULL,
    status             TEXT    NOT NULL,
    max_iterations     INTEGER NOT NULL,
    iteration_count    INTEGER NOT NULL DEFAULT 0,
    total_tokens       INTEGER NOT NULL DEFAULT 0,
    termination_reason TEXT,
    started_at         REAL,
    finished_at        REAL
);
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    iteration   INTEGER NOT NULL,
    sender_role TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    tokens      INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS specifications (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL REFERENCES runs(id),
    version             INTEGER NOT NULL,
    content             TEXT    NOT NULL,
    acceptance_criteria TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS code_artifacts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL REFERENCES runs(id),
    iteration    INTEGER NOT NULL,
    file_path    TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    content_hash TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    INTEGER NOT NULL REFERENCES runs(id),
    iteration INTEGER NOT NULL,
    verdict   TEXT    NOT NULL,
    severity  TEXT,
    feedback  TEXT    NOT NULL
);
"""


def connect(path=DB_PATH):
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


# --------------------------------------------------------------------------
# agent layer
# --------------------------------------------------------------------------

def count_tokens(text):
    """Stand-in for the provider tokenizer: ~4 characters per token."""
    return max(1, len(text) // 4)


class MockLLM:
    """Deterministic scripted backend, so runs are repeatable and free.

    Each scenario is a dict: role -> list of responses indexed by iteration.
    """

    def __init__(self, script):
        self.script = script
        self.calls = 0

    def complete(self, role, iteration):
        self.calls += 1
        responses = self.script[role]
        return responses[min(iteration, len(responses) - 1)]


class Engine:
    """The state graph:

    START -> PM.plan -> Dev.implement -> Reviewer.review
          -> [approve                              -> finalize]
          |  [reject & iter < max & progress       -> Dev.implement]
          |  [reject & (iter = max | no progress)  -> finalize_with_warnings]
          -> END
    """

    BLOCKING = ("critical", "major")

    def __init__(self, llm, db, max_iterations=MAX_ITERATIONS, verbose=True):
        self.llm = llm
        self.db = db
        self.max_iterations = max_iterations
        self.verbose = verbose
        self.tokens = 0

    # -- helpers ----------------------------------------------------------
    def log(self, role, text, indent=6):
        if not self.verbose:
            return
        body = textwrap.fill(text, 92, initial_indent=" " * indent,
                             subsequent_indent=" " * indent)
        print(f"  {role:<10} {body.strip()}" if indent == 0 else body)

    def record(self, run_id, iteration, role, content):
        tokens = count_tokens(content)
        self.tokens += tokens
        self.db.execute(
            "INSERT INTO messages (run_id, iteration, sender_role, content, tokens)"
            " VALUES (?,?,?,?,?)", (run_id, iteration, role, content, tokens))
        return tokens

    # -- nodes ------------------------------------------------------------
    def plan(self, run_id, prompt):
        spec = self.llm.complete("pm", 0)
        criteria = self.llm.complete("pm_criteria", 0)
        self.record(run_id, 0, "product_manager", spec)
        self.db.execute(
            "INSERT INTO specifications (run_id, version, content, acceptance_criteria)"
            " VALUES (?,?,?,?)", (run_id, 1, spec, criteria))
        print(f"\n  [0] PM        spec written  ({count_tokens(spec)} tok)")
        print(f"      criteria: {criteria}")
        return spec

    def implement(self, run_id, iteration):
        code = self.llm.complete("dev", iteration)
        digest = hashlib.sha256(code.encode()).hexdigest()
        self.record(run_id, iteration, "developer", code)
        self.db.execute(
            "INSERT INTO code_artifacts (run_id, iteration, file_path, content, content_hash)"
            " VALUES (?,?,?,?,?)", (run_id, iteration, "src/main.py", code, digest))
        print(f"  [{iteration}] Developer  {len(code.splitlines())} lines"
              f"  sha256:{digest[:10]}  ({count_tokens(code)} tok)")
        return code, digest

    def review(self, run_id, iteration):
        raw = self.llm.complete("reviewer", iteration)
        verdict, severity, feedback = raw
        self.record(run_id, iteration, "reviewer", feedback)
        self.db.execute(
            "INSERT INTO reviews (run_id, iteration, verdict, severity, feedback)"
            " VALUES (?,?,?,?,?)", (run_id, iteration, verdict, severity, feedback))
        mark = "PASS" if verdict == "approve" else "FAIL"
        print(f"  [{iteration}] Reviewer   {mark}  severity={severity or '-':<8}"
              f"  {feedback}")
        return verdict, severity

    # -- the loop ---------------------------------------------------------
    def run(self, prompt, label=""):
        started = time.time()
        cur = self.db.execute(
            "INSERT INTO runs (prompt, mode, status, max_iterations, started_at)"
            " VALUES (?,?,?,?,?)",
            (prompt, "multi_agent", "running", self.max_iterations, started))
        run_id = cur.lastrowid

        print(f"\n{'=' * 100}")
        print(f"RUN {run_id}  {label}")
        print(f"prompt: {prompt!r}   max_iterations={self.max_iterations}")
        print("=" * 100)

        self.plan(run_id, prompt)

        seen_hashes = set()
        iteration = 1
        status, reason = "failed", "error"

        while True:
            code, digest = self.implement(run_id, iteration)

            # loop-prevention mechanism 3: no-progress detection
            if digest in seen_hashes:
                status, reason = "max_iterations", "no_progress"
                print(f"  [{iteration}] ENGINE     identical code hash seen before "
                      f"-> no-progress exit")
                break
            seen_hashes.add(digest)

            verdict, severity = self.review(run_id, iteration)

            # loop-prevention mechanism 2: severity threshold
            if verdict == "approve" or severity not in self.BLOCKING:
                status, reason = "approved", "approved"
                if verdict != "approve":
                    print(f"  [{iteration}] ENGINE     '{severity}' is below the blocking "
                          f"threshold -> approved with notes")
                break

            # loop-prevention mechanism 1: hard iteration cap
            if iteration >= self.max_iterations:
                status, reason = "max_iterations", "iteration_cap"
                print(f"  [{iteration}] ENGINE     iteration cap ({self.max_iterations}) "
                      f"reached -> finalize_with_warnings")
                break

            iteration += 1

        finished = time.time()
        self.db.execute(
            "UPDATE runs SET status=?, iteration_count=?, total_tokens=?,"
            " termination_reason=?, finished_at=? WHERE id=?",
            (status, iteration, self.tokens, reason, finished, run_id))
        self.db.commit()

        print("-" * 100)
        print(f"  RESULT  status={status}  iterations={iteration}"
              f"  termination_reason={reason}"
              f"  tokens={self.tokens}  llm_calls={self.llm.calls}"
              f"  latency={finished - started:.4f}s")
        return {"run_id": run_id, "status": status, "iterations": iteration,
                "reason": reason, "tokens": self.tokens,
                "calls": self.llm.calls, "latency": finished - started}


# --------------------------------------------------------------------------
# scripted scenarios - one per termination path the engine must handle
# --------------------------------------------------------------------------

SPEC = ("Terminal snake game in Python. Files: src/main.py. Features: 20x20 grid, "
        "arrow-key movement, food spawns at random free cell, snake grows on eat, "
        "game ends on wall or self collision, score displayed.")
CRITERIA = ("1) runs without error  2) snake grows on eat  3) wall collision ends game  "
            "4) self collision ends game  5) score shown")

CODE_V1 = "\n".join(f"line {i} of the first draft" for i in range(1, 61))
CODE_V2 = "\n".join(f"line {i} of the fixed version" for i in range(1, 74))

HAPPY_PATH = {
    "pm": [SPEC],
    "pm_criteria": [CRITERIA],
    "dev": [CODE_V1, CODE_V1, CODE_V2],
    "reviewer": [
        ("reject", "major", "criterion 4 fails: self-collision never ends the game"),
        ("reject", "major", "criterion 4 fails: self-collision never ends the game"),
        ("reject", "minor", "all 5 criteria pass; variable name 'x1' is unclear"),
    ],
}

STUCK_DEV = {   # Developer returns byte-identical code -> no-progress exit
    "pm": [SPEC],
    "pm_criteria": [CRITERIA],
    "dev": [CODE_V1],
    "reviewer": [("reject", "critical", "criterion 1 fails: IndexError on first move")],
}

PICKY_REVIEWER = {  # Reviewer never satisfied, code keeps changing -> cap
    "pm": [SPEC],
    "pm_criteria": [CRITERIA],
    "dev": [CODE_V1 + f"\n# revision {i}" for i in range(1, 9)],
    "reviewer": [("reject", "major", "criterion 4 still fails")],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="store_true", help="dump the database afterwards")
    args = ap.parse_args()

    db = connect()
    db.executescript("DELETE FROM reviews; DELETE FROM code_artifacts;"
                     "DELETE FROM specifications; DELETE FROM messages; DELETE FROM runs;"
                     "DELETE FROM sqlite_sequence;")

    scenarios = [
        ("happy path - reject, reject, approve-with-minor", HAPPY_PATH, 5),
        ("stuck developer - identical code returned twice", STUCK_DEV, 5),
        ("picky reviewer - never approves, code keeps changing", PICKY_REVIEWER, 5),
    ]

    results = []
    for label, script, cap in scenarios:
        engine = Engine(MockLLM(script), db, max_iterations=cap)
        results.append((label, engine.run(SPEC.split(".")[0], label)))

    print(f"\n{'=' * 100}")
    print("PROTOTYPE RESULTS - engine behaviour over 3 scenarios")
    print("=" * 100)
    print(f"{'scenario':<52}{'iters':>6}{'termination':>17}{'tokens':>9}{'calls':>7}{'latency s':>11}")
    print("-" * 100)
    for label, r in results:
        print(f"{label:<52}{r['iterations']:>6}{r['reason']:>17}"
              f"{r['tokens']:>9}{r['calls']:>7}{r['latency']:>11.4f}")
    print("-" * 100)
    terminated = sum(1 for _, r in results if r["reason"] != "error")
    print(f"runs that terminated cleanly: {terminated}/{len(results)}  (target: 100%)")
    print(f"distinct termination paths exercised: "
          f"{len({r['reason'] for _, r in results})}/3")

    if args.db:
        print(f"\n{'=' * 100}")
        print("PERSISTED IN mawe.db")
        print("=" * 100)
        for table in ("runs", "messages", "specifications", "code_artifacts", "reviews"):
            n = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:<18} {n:>4} rows")
        print("\n  runs table:")
        cols = "id prompt status iteration_count total_tokens termination_reason".split()
        print("   " + "".join(f"{c:<22}" if c == "prompt" else f"{c:<20}" for c in cols))
        for row in db.execute("SELECT id, prompt, status, iteration_count,"
                              " total_tokens, termination_reason FROM runs"):
            cells = [str(row[0]), row[1][:20], row[2], str(row[3]), str(row[4]), str(row[5])]
            print("   " + "".join(f"{c:<22}" if i == 1 else f"{c:<20}"
                                  for i, c in enumerate(cells)))
    db.close()


if __name__ == "__main__":
    main()
