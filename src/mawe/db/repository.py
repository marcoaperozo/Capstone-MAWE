"""Session management and the small set of writes the engine needs.

Keeping persistence behind this module means the graph nodes never touch
SQLAlchemy directly, which is what lets the integration tests run the whole
pipeline against an in-memory database.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    Base,
    CodeArtifact,
    EvaluationResult,
    MemorySummary,
    Message,
    Project,
    Review,
    Run,
    Specification,
    utcnow,
)

DEFAULT_URL = "sqlite:///mawe.db"


def make_engine(url: str = DEFAULT_URL, echo: bool = False):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, echo=echo, future=True, connect_args=connect_args)
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def session_scope(engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class RunRepository:
    """Thin write-side helper bound to one open session."""

    def __init__(self, session: Session):
        self.session = session

    # -- creation ---------------------------------------------------------
    def create_project(self, prompt: str, title: str = "",
                       language: str = "python") -> Project:
        project = Project(title=title or prompt[:60], prompt=prompt,
                          target_language=language)
        self.session.add(project)
        self.session.flush()
        return project

    def start_run(self, project: Optional[Project], max_iterations: int,
                  mode: str = "multi_agent") -> Run:
        run = Run(project_id=project.id if project else None,
                  mode=mode, status="running",
                  max_iterations=max_iterations, started_at=utcnow())
        self.session.add(run)
        self.session.flush()
        return run

    # -- per-node writes --------------------------------------------------
    def add_message(self, run: Run, iteration: int, role: str, content: str,
                    prompt_tokens: int = 0, completion_tokens: int = 0) -> Message:
        msg = Message(run_id=run.id, iteration=iteration, sender_role=role,
                      content=content, prompt_tokens=prompt_tokens,
                      completion_tokens=completion_tokens)
        run.total_prompt_tokens += prompt_tokens
        run.total_completion_tokens += completion_tokens
        self.session.add(msg)
        self.session.flush()
        return msg

    def add_specification(self, run: Run, content: str, criteria: str,
                          version: int = 1) -> Specification:
        spec = Specification(run_id=run.id, version=version, content=content,
                             acceptance_criteria=criteria)
        self.session.add(spec)
        self.session.flush()
        return spec

    def add_code_artifact(self, run: Run, iteration: int, path: str,
                          content: str, language: str = "python") -> CodeArtifact:
        art = CodeArtifact(run_id=run.id, iteration=iteration, file_path=path,
                           language=language, content=content,
                           content_hash=sha256(content))
        self.session.add(art)
        self.session.flush()
        return art

    def add_review(self, run: Run, iteration: int, verdict: str,
                   severity: Optional[str], feedback: str,
                   tests_passed: int = 0, tests_failed: int = 0) -> Review:
        review = Review(run_id=run.id, iteration=iteration, verdict=verdict,
                        severity=severity, feedback=feedback,
                        tests_passed=tests_passed, tests_failed=tests_failed)
        self.session.add(review)
        self.session.flush()
        return review

    def add_memory_summary(self, run: Run, from_iter: int, to_iter: int,
                           summary: str, before: int, after: int) -> MemorySummary:
        row = MemorySummary(run_id=run.id, from_iteration=from_iter,
                            to_iteration=to_iter, summary=summary,
                            tokens_before=before, tokens_after=after)
        self.session.add(row)
        self.session.flush()
        return row

    def add_metric(self, run: Run, metric: str, value: float) -> EvaluationResult:
        row = EvaluationResult(run_id=run.id, metric=metric, value=float(value))
        self.session.add(row)
        self.session.flush()
        return row

    # -- completion -------------------------------------------------------
    def finish_run(self, run: Run, status: str, reason: str,
                   iterations: int) -> Run:
        run.status = status
        run.termination_reason = reason
        run.iteration_count = iterations
        run.finished_at = utcnow()
        self.session.flush()
        return run
