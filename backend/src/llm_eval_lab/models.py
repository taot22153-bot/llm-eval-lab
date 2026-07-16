from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
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


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_evaluation_run_status",
        ),
        CheckConstraint(
            "baseline_version_id <> candidate_version_id",
            name="ck_evaluation_run_distinct_versions",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    baseline_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("application_versions.id", ondelete="RESTRICT"),
    )
    candidate_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("application_versions.id", ondelete="RESTRICT"),
    )
    evaluation_suite_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_suites.id", ondelete="RESTRICT"),
    )
    status: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    baseline_version: Mapped[ApplicationVersion] = relationship(
        foreign_keys=[baseline_version_id]
    )
    candidate_version: Mapped[ApplicationVersion] = relationship(
        foreign_keys=[candidate_version_id]
    )
    evaluation_suite: Mapped[EvaluationSuite] = relationship()
    executions: Mapped[list[TestCaseExecution]] = relationship(
        back_populates="evaluation_run",
        cascade="all, delete-orphan",
    )
    release_decisions: Mapped[list[ReleaseDecision]] = relationship(
        back_populates="evaluation_run",
        cascade="all, delete-orphan",
    )


class TestCaseExecution(Base):
    __tablename__ = "test_case_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_test_case_execution_status",
        ),
        CheckConstraint(
            "version_role IS NULL OR version_role IN ('baseline', 'candidate')",
            name="ck_test_case_execution_version_role",
        ),
        CheckConstraint(
            "(evaluation_run_id IS NULL AND version_role IS NULL) OR "
            "(evaluation_run_id IS NOT NULL AND version_role IS NOT NULL)",
            name="ck_test_case_execution_run_role_pair",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("application_versions.id", ondelete="RESTRICT"),
    )
    test_case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("test_cases.id", ondelete="RESTRICT"),
    )
    evaluation_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    version_role: Mapped[str | None] = mapped_column(String(24), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    prompt_context: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage: Mapped[dict[str, int | float | None] | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    application_version: Mapped[ApplicationVersion] = relationship()
    test_case: Mapped[TestCase] = relationship()
    evaluation_run: Mapped[EvaluationRun | None] = relationship(back_populates="executions")
    deterministic_evaluation: Mapped[DeterministicEvaluation | None] = relationship(
        back_populates="execution",
        cascade="all, delete-orphan",
        uselist=False,
    )
    semantic_evaluation: Mapped[SemanticEvaluation | None] = relationship(
        back_populates="execution",
        cascade="all, delete-orphan",
        uselist=False,
    )
    human_review_item: Mapped[HumanReviewItem | None] = relationship(
        back_populates="execution",
        cascade="all, delete-orphan",
        uselist=False,
    )


class DeterministicEvaluation(Base):
    __tablename__ = "deterministic_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "test_case_execution_id",
            name="uq_deterministic_evaluation_execution",
        ),
        CheckConstraint(
            "regression_classification IS NULL OR "
            "regression_classification IN ('new_regression', 'existing_failure')",
            name="ck_deterministic_evaluation_regression",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    test_case_execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("test_case_executions.id", ondelete="CASCADE"),
    )
    scorer_version: Mapped[str] = mapped_column(String(80))
    passed: Mapped[bool] = mapped_column(Boolean)
    regression_classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    execution: Mapped[TestCaseExecution] = relationship(
        back_populates="deterministic_evaluation"
    )
    outcomes: Mapped[list[DeterministicCheckOutcome]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
        order_by="DeterministicCheckOutcome.position",
    )


class DeterministicCheckOutcome(Base):
    __tablename__ = "deterministic_check_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "deterministic_evaluation_id",
            "position",
            name="uq_deterministic_outcome_position",
        ),
        CheckConstraint(
            "check_type IN ('must_have_fact', 'forbidden_claim')",
            name="ck_deterministic_outcome_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deterministic_evaluation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("deterministic_evaluations.id", ondelete="CASCADE"),
    )
    check_type: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer)
    rule: Mapped[str] = mapped_column(Text)
    passed: Mapped[bool] = mapped_column(Boolean)
    matched_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation: Mapped[DeterministicEvaluation] = relationship(back_populates="outcomes")


class SemanticEvaluation(Base):
    __tablename__ = "semantic_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "test_case_execution_id",
            name="uq_semantic_evaluation_execution",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('pass', 'fail', 'insufficient_evidence')",
            name="ck_semantic_evaluation_outcome",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_semantic_evaluation_confidence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    test_case_execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("test_case_executions.id", ondelete="CASCADE"),
    )
    judge_version: Mapped[str] = mapped_column(String(80))
    outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    judge_configuration: Mapped[dict[str, Any]] = mapped_column(JSON)
    error: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    execution: Mapped[TestCaseExecution] = relationship(
        back_populates="semantic_evaluation"
    )


class HumanReviewItem(Base):
    __tablename__ = "human_review_items"
    __table_args__ = (
        UniqueConstraint(
            "test_case_execution_id",
            name="uq_human_review_item_execution",
        ),
        CheckConstraint(
            "status IN ('pending', 'resolved')",
            name="ck_human_review_item_status",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('pass', 'fail')",
            name="ck_human_review_item_outcome",
        ),
        CheckConstraint(
            "(status = 'pending' AND outcome IS NULL AND rationale IS NULL "
            "AND resolved_at IS NULL) OR "
            "(status = 'resolved' AND outcome IS NOT NULL AND rationale IS NOT NULL "
            "AND resolved_at IS NOT NULL)",
            name="ck_human_review_item_decision_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    test_case_execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("test_case_executions.id", ondelete="CASCADE"),
    )
    status: Mapped[str] = mapped_column(String(24), default="pending")
    reasons: Mapped[list[str]] = mapped_column(JSON)
    outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    execution: Mapped[TestCaseExecution] = relationship(back_populates="human_review_item")


class ReleaseRule(Base):
    __tablename__ = "release_rules"
    __table_args__ = (
        UniqueConstraint("slug", "version", name="uq_release_rule_slug_version"),
        CheckConstraint("version >= 1", name="ck_release_rule_version"),
        CheckConstraint(
            "maximum_correctness_drop >= 0 AND maximum_correctness_drop <= 1",
            name="ck_release_rule_correctness_drop",
        ),
        CheckConstraint(
            "minimum_candidate_safety_rate >= 0 "
            "AND minimum_candidate_safety_rate <= 1",
            name="ck_release_rule_safety_rate",
        ),
        CheckConstraint(
            "maximum_candidate_average_latency_ms IS NULL "
            "OR maximum_candidate_average_latency_ms >= 0",
            name="ck_release_rule_latency_budget",
        ),
        CheckConstraint(
            "maximum_candidate_total_cost_usd IS NULL "
            "OR maximum_candidate_total_cost_usd >= 0",
            name="ck_release_rule_cost_budget",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160))
    blocking_severities: Mapped[list[str]] = mapped_column(JSON)
    new_regression_severities: Mapped[list[str]] = mapped_column(JSON)
    require_resolved_reviews: Mapped[bool] = mapped_column(Boolean)
    maximum_correctness_drop: Mapped[float] = mapped_column(Float)
    minimum_candidate_safety_rate: Mapped[float] = mapped_column(Float)
    maximum_candidate_average_latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    maximum_candidate_total_cost_usd: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    decisions: Mapped[list[ReleaseDecision]] = relationship(back_populates="release_rule")


class ReleaseDecision(Base):
    __tablename__ = "release_decisions"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_run_id",
            "release_rule_id",
            "evidence_fingerprint",
            name="uq_release_decision_evidence",
        ),
        CheckConstraint(
            "outcome IN ('pass', 'fail', 'manual_review_required')",
            name="ck_release_decision_outcome",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    evaluation_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
    )
    release_rule_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("release_rules.id", ondelete="RESTRICT"),
    )
    outcome: Mapped[str] = mapped_column(String(40))
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=6),
        default=lambda: datetime.now(UTC),
    )
    evaluation_run: Mapped[EvaluationRun] = relationship(back_populates="release_decisions")
    release_rule: Mapped[ReleaseRule] = relationship(back_populates="decisions")
