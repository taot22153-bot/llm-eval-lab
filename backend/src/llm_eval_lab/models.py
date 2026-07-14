from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llm_eval_lab.database import Base


class ApplicationVersion(Base):
    __tablename__ = "application_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    model_provider: Mapped[str] = mapped_column(String(80))
    model_name: Mapped[str] = mapped_column(String(160))
    system_prompt: Mapped[str] = mapped_column(Text)
    generation_parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    knowledge_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tool_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


class EvaluationSuite(Base):
    __tablename__ = "evaluation_suites"
    __table_args__ = (UniqueConstraint("slug", "version", name="uq_suite_slug_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    test_cases: Mapped[list[TestCase]] = relationship(
        back_populates="suite",
        cascade="all, delete-orphan",
        order_by="TestCase.position",
    )


class TestCase(Base):
    __tablename__ = "test_cases"
    __table_args__ = (
        UniqueConstraint("suite_id", "key", name="uq_test_case_suite_key"),
        CheckConstraint(
            "test_type IN ('normal', 'hallucination', 'prompt_injection', 'jailbreak')",
            name="ck_test_case_type",
        ),
        CheckConstraint(
            "severity IN ('normal', 'important', 'release_blocking')",
            name="ck_test_case_severity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    suite_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_suites.id", ondelete="CASCADE"),
    )
    key: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(180))
    user_input: Mapped[str] = mapped_column(Text)
    grounding_material: Mapped[list[dict[str, str]]] = mapped_column(JSON)
    must_have_facts: Mapped[list[str]] = mapped_column(JSON)
    forbidden_claims: Mapped[list[str]] = mapped_column(JSON)
    test_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(40))
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    suite: Mapped[EvaluationSuite] = relationship(back_populates="test_cases")
