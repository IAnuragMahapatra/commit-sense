"""SQLAlchemy models — Repo, Commit, Flag."""

from datetime import datetime, timezone

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey,
    Integer, String, Boolean, Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Repo(Base):
    __tablename__ = "repos"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    commits = relationship("Commit", back_populates="repo", cascade="all, delete-orphan")


class Commit(Base):
    __tablename__ = "commits"

    id = Column(Integer, primary_key=True, index=True)
    sha = Column(String, unique=True, index=True, nullable=False)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=False)

    # Hook-populated fields
    original_message = Column(Text, nullable=True)
    rewritten_message = Column(Text, nullable=True)
    amended = Column(Boolean, default=False)

    # CI-populated fields
    score = Column(Integer, nullable=True)
    grade = Column(String(1), nullable=True)
    llm_aligned = Column(Boolean, nullable=True)
    llm_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    repo = relationship("Repo", back_populates="commits")
    flags = relationship("Flag", back_populates="commit", cascade="all, delete-orphan")


class Flag(Base):
    __tablename__ = "flags"

    id = Column(Integer, primary_key=True, index=True)
    commit_id = Column(Integer, ForeignKey("commits.id"), nullable=False)
    rule = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    detail = Column(Text, nullable=True)

    commit = relationship("Commit", back_populates="flags")
