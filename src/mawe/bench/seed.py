"""Load the benchmark into the `benchmark_tasks` table.

Week 9.  The schema has carried this table since Week 2 (proposal section 7);
this is what finally fills it, so that a `runs` row can point at the task it
was attempting and the Phase 4 comparison can be rebuilt from the database
alone rather than from whatever was on the screen when the sweep ran.

Seeding is idempotent and keyed on `name`: re-running it updates the stored
prompt and tests in place instead of creating a second copy of the suite.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select as sa_select

from ..db import BenchmarkTask, session_scope
from .tasks import TASKS, BenchTask


def tests_as_json(task: BenchTask) -> str:
    return json.dumps([dataclasses.asdict(t) for t in task.tests], indent=None)


def seed(engine, tasks: Sequence[BenchTask] = TASKS) -> Dict[str, int]:
    """Insert or update every task.  Returns slug -> row id."""
    ids: Dict[str, int] = {}
    with session_scope(engine) as session:
        existing = {row.name: row for row in
                    session.scalars(sa_select(BenchmarkTask)).all()}
        for task in tasks:
            row = existing.get(task.slug)
            if row is None:
                row = BenchmarkTask(name=task.slug)
                session.add(row)
            row.prompt = task.prompt
            row.difficulty = task.difficulty
            row.language = task.language
            row.hidden_tests = tests_as_json(task)
            session.flush()
            ids[task.slug] = row.id
    return ids


def task_ids(engine) -> Dict[str, int]:
    with session_scope(engine) as session:
        return {row.name: row.id
                for row in session.scalars(sa_select(BenchmarkTask)).all()}
