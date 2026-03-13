"""
SQLAlchemy ORM models for GBADS v2.
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer,
    String, Text, JSON, Enum, func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ──────────────────────────────────────────────────────────────────────

class ProjectStatus(str, PyEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class RepoStructure(str, PyEnum):
    MONO = "MONO"
    MULTI = "MULTI"
    MICROSERVICES = "MICROSERVICES"


class CloneStatus(str, PyEnum):
    PENDING = "PENDING"
    CLONING = "CLONING"
    DONE = "DONE"
    FAILED = "FAILED"


class RepoRole(str, PyEnum):
    PRIMARY = "PRIMARY"
    SERVICE = "SERVICE"


class FeatureStatus(str, PyEnum):
    INTERCEPTING = "INTERCEPTING"
    AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"
    AWAITING_METRIC_APPROVAL = "AWAITING_METRIC_APPROVAL"
    RUNNING = "RUNNING"
    DONE = "DONE"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"


# ── Models ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: str = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    github_id: str = Column(String, unique=True, nullable=False)
    github_username: str = Column(String, nullable=False)
    github_email: str = Column(String, nullable=True)
    github_access_token: str = Column(Text, nullable=False)  # Fernet-encrypted
    avatar_url: str = Column(String, nullable=True)
    created_at: datetime = Column(DateTime, default=func.now(), nullable=False)
    last_login: datetime = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    projects = relationship("Project", back_populates="user", lazy="select")


class Project(Base):
    __tablename__ = "projects"

    id: str = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: str = Column(String, ForeignKey("users.id"), nullable=False)
    name: str = Column(String, nullable=False)
    description: str = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime, default=func.now(), nullable=False)
    status: str = Column(String, default=ProjectStatus.ACTIVE, nullable=False)
    repo_structure: str = Column(String, default=RepoStructure.MONO, nullable=False)
    detected_stack: Optional[dict] = Column(JSON, nullable=True)
    generated_compose: Optional[str] = Column(Text, nullable=True)

    user = relationship("User", back_populates="projects")
    repos = relationship("ProjectRepo", back_populates="project", lazy="select")
    features = relationship("Feature", back_populates="project", lazy="select")


class ProjectRepo(Base):
    __tablename__ = "project_repos"

    id: str = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: str = Column(String, ForeignKey("projects.id"), nullable=False)
    github_url: str = Column(String, nullable=False)
    repo_name: str = Column(String, nullable=False)
    local_path: str = Column(String, nullable=True)
    clone_status: str = Column(String, default=CloneStatus.PENDING, nullable=False)
    clone_error: Optional[str] = Column(Text, nullable=True)
    default_branch: str = Column(String, nullable=True)
    cloned_at: Optional[datetime] = Column(DateTime, nullable=True)
    role: str = Column(String, default=RepoRole.PRIMARY, nullable=False)

    project = relationship("Project", back_populates="repos")


class Feature(Base):
    __tablename__ = "features"

    id: str = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: str = Column(String, ForeignKey("projects.id"), nullable=False)
    title: str = Column(String, nullable=False)
    raw_requirement: str = Column(Text, nullable=False)
    status: str = Column(String, default=FeatureStatus.INTERCEPTING, nullable=False)
    module_spec: Optional[dict] = Column(JSON, nullable=True)
    benchmark_plan: Optional[dict] = Column(JSON, nullable=True)
    approved_at: Optional[datetime] = Column(DateTime, nullable=True)
    feature_branch: Optional[str] = Column(String, nullable=True)
    pr_url: Optional[str] = Column(String, nullable=True)
    created_at: datetime = Column(DateTime, default=func.now(), nullable=False)
    session_id: Optional[str] = Column(String, ForeignKey("sessions.id"), nullable=True)

    project = relationship("Project", back_populates="features")
    session = relationship("Session", back_populates="feature", foreign_keys=[session_id])


class Session(Base):
    __tablename__ = "sessions"

    id: str = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    module_name: str = Column(String, nullable=False)
    requirement: str = Column(Text, nullable=False)
    created_at: datetime = Column(DateTime, default=func.now(), nullable=False)
    status: str = Column(String, default="running", nullable=False)
    best_score: Optional[float] = Column(Float, nullable=True)
    best_iteration: Optional[int] = Column(Integer, nullable=True)

    # v2 fields
    feature_id: Optional[str] = Column(String, ForeignKey("features.id"), nullable=True)
    project_id: Optional[str] = Column(String, ForeignKey("projects.id"), nullable=True)
    repo_path: Optional[str] = Column(String, nullable=True)
    feature_branch: Optional[str] = Column(String, nullable=True)
    pushed_at: Optional[datetime] = Column(DateTime, nullable=True)
    push_commit_hash: Optional[str] = Column(String, nullable=True)

    iterations = relationship("Iteration", back_populates="session", lazy="select")
    feature = relationship("Feature", back_populates="session", foreign_keys=[feature_id])


class Iteration(Base):
    __tablename__ = "iterations"

    id: str = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: str = Column(String, ForeignKey("sessions.id"), nullable=False)
    iteration_number: int = Column(Integer, nullable=False)
    score: float = Column(Float, nullable=False)
    passed: int = Column(Integer, nullable=False)
    failed: int = Column(Integer, nullable=False)
    total: int = Column(Integer, nullable=False)
    code: str = Column(Text, nullable=False)
    result_json: Optional[dict] = Column(JSON, nullable=True)
    commit_hash: Optional[str] = Column(String, nullable=True)
    diff: Optional[str] = Column(Text, nullable=True)
    is_best: bool = Column(Boolean, default=False, nullable=False)
    created_at: datetime = Column(DateTime, default=func.now(), nullable=False)

    session = relationship("Session", back_populates="iterations")


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: str = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Optional[str] = Column(String, ForeignKey("sessions.id"), nullable=True)
    iteration_number: Optional[int] = Column(Integer, nullable=True)
    prompt_tokens: int = Column(Integer, nullable=False)
    completion_tokens: int = Column(Integer, nullable=False)
    duration_ms: int = Column(Integer, nullable=False)
    created_at: datetime = Column(DateTime, default=func.now(), nullable=False)
