"""SQLAlchemy models - the persistence layer from proposal section 7.

SQLite during development; the schema is written so it migrates to PostgreSQL
without changes.  Every run of the engine is fully traceable: the original
prompt, the PM specification, every version of the code, every review and the
metrics used for evaluation.
"""

from __future__ import annotations

import datetime as _dt
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------- users
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=utcnow)

    projects: Mapped[List["Project"]] = relationship(back_populates="user")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    prompt: Mapped[str] = mapped_column(Text)
    target_language: Mapped[str] = mapped_column(String(20), default="python")
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint("target_language IN ('python','javascript')",
                        name="ck_projects_language"),
    )

    user: Mapped[Optional[User]] = relationship(back_populates="projects")
    runs: Mapped[List["Run"]] = relationship(back_populates="project")


# -------------------------------------------------------------------- agents
class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(30))
    model_name: Mapped[str] = mapped_column(String(80))
    system_prompt: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    temperature: Mapped[float] = mapped_column(Float, default=0.2)

    __table_args__ = (
        CheckConstraint(
            "role IN ('product_manager','developer','reviewer')",
            name="ck_agents_role"),
    )

    messages: Mapped[List["Message"]] = relationship(back_populates="agent")


class BenchmarkTask(Base):
    __tablename__ = "benchmark_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    prompt: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(10))
    hidden_tests: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(20), default="python")

    __table_args__ = (
        CheckConstraint("difficulty IN ('easy','medium','hard')",
                        name="ck_tasks_difficulty"),
    )

    runs: Mapped[List["Run"]] = relationship(back_populates="benchmark_task")


# ---------------------------------------------------------------------- runs
class Run(Base):
    """One execution of the engine.  `mode` distinguishes the proposed system
    from the single-model baseline used in the Phase 4 comparison."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"))
    benchmark_task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("benchmark_tasks.id"))
    mode: Mapped[str] = mapped_column(String(20), default="multi_agent")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    max_iterations: Mapped[int] = mapped_column(Integer, default=5)
    iteration_count: Mapped[int] = mapped_column(Integer, default=0)
    total_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    termination_reason: Mapped[Optional[str]] = mapped_column(String(50))
    started_at: Mapped[Optional[_dt.datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[_dt.datetime]] = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint("mode IN ('multi_agent','single_model','self_refine')",
                        name="ck_runs_mode"),
        CheckConstraint(
            "status IN ('pending','running','approved','max_iterations','failed')",
            name="ck_runs_status"),
        Index("ix_runs_project", "project_id"),
        Index("ix_runs_benchmark_mode", "benchmark_task_id", "mode"),
    )

    project: Mapped[Optional[Project]] = relationship(back_populates="runs")
    benchmark_task: Mapped[Optional[BenchmarkTask]] = relationship(
        back_populates="runs")
    messages: Mapped[List["Message"]] = relationship(
        back_populates="run", cascade="all, delete-orphan")
    specifications: Mapped[List["Specification"]] = relationship(
        back_populates="run", cascade="all, delete-orphan")
    code_artifacts: Mapped[List["CodeArtifact"]] = relationship(
        back_populates="run", cascade="all, delete-orphan")
    reviews: Mapped[List["Review"]] = relationship(
        back_populates="run", cascade="all, delete-orphan")
    memory_summaries: Mapped[List["MemorySummary"]] = relationship(
        back_populates="run", cascade="all, delete-orphan")
    evaluation_results: Mapped[List["EvaluationResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan")

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agents.id"))
    iteration: Mapped[int] = mapped_column(Integer)
    sender_role: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (Index("ix_messages_run_iter", "run_id", "iteration"),)

    run: Mapped[Run] = relationship(back_populates="messages")
    agent: Mapped[Optional[Agent]] = relationship(back_populates="messages")


class Specification(Base):
    __tablename__ = "specifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text)
    acceptance_criteria: Mapped[str] = mapped_column(Text)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped[Run] = relationship(back_populates="specifications")


class CodeArtifact(Base):
    """One generated file.  `content_hash` is what the no-progress exit
    condition compares to detect a Developer that is not making progress."""

    __tablename__ = "code_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    iteration: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(20), default="python")
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (Index("ix_artifacts_run_iter", "run_id", "iteration"),)

    run: Mapped[Run] = relationship(back_populates="code_artifacts")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    iteration: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(10))
    severity: Mapped[Optional[str]] = mapped_column(String(10))
    tests_passed: Mapped[int] = mapped_column(Integer, default=0)
    tests_failed: Mapped[int] = mapped_column(Integer, default=0)
    feedback: Mapped[str] = mapped_column(Text)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint("verdict IN ('approve','reject')", name="ck_reviews_verdict"),
        Index("ix_reviews_run_iter", "run_id", "iteration"),
    )

    run: Mapped[Run] = relationship(back_populates="reviews")


class MemorySummary(Base):
    __tablename__ = "memory_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    from_iteration: Mapped[int] = mapped_column(Integer)
    to_iteration: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    tokens_before: Mapped[int] = mapped_column(Integer, default=0)
    tokens_after: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped[Run] = relationship(back_populates="memory_summaries")


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    metric: Mapped[str] = mapped_column(String(50))
    value: Mapped[float] = mapped_column(Float)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped[Run] = relationship(back_populates="evaluation_results")
