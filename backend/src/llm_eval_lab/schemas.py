from datetime import UTC, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_serializer,
    field_validator,
)


class ApplicationVersionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    model_provider: str = Field(min_length=1, max_length=80)
    model_name: str = Field(min_length=1, max_length=160)
    system_prompt: str = Field(min_length=1)
    generation_parameters: dict[str, JsonValue] = Field(default_factory=dict)
    knowledge_config: dict[str, JsonValue] | None = None
    tool_config: dict[str, JsonValue] | None = None


class ApplicationVersionRead(ApplicationVersionCreate):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class GroundingMaterialRead(BaseModel):
    kind: Literal["product", "shipping", "return", "warranty"]
    title: str
    content: str


class TestCaseRead(BaseModel):
    id: str
    key: str
    position: int
    title: str
    user_input: str
    grounding_material: list[GroundingMaterialRead]
    must_have_facts: list[str]
    forbidden_claims: list[str]
    test_type: Literal["normal", "hallucination", "prompt_injection", "jailbreak"]
    severity: Literal["normal", "important", "release_blocking"]
    requires_human_review: bool

    model_config = ConfigDict(from_attributes=True)


class EvaluationSuiteSummary(BaseModel):
    id: str
    slug: str
    version: int
    name: str
    description: str
    test_case_count: int


class EvaluationSuiteDetail(EvaluationSuiteSummary):
    test_cases: list[TestCaseRead]


class TestCaseExecutionCreate(BaseModel):
    application_version_id: str
    test_case_id: str


class ModelUsageRead(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = Field(default=None, ge=0)


class ModelFailureRead(BaseModel):
    code: str
    message: str


class DeterministicCheckOutcomeRead(BaseModel):
    check_type: Literal["must_have_fact", "forbidden_claim"]
    position: int
    rule: str
    passed: bool
    matched_evidence: str | None


class DeterministicEvaluationRead(BaseModel):
    scorer_version: str
    passed: bool
    regression_classification: Literal["new_regression", "existing_failure"] | None
    outcomes: list[DeterministicCheckOutcomeRead]


class SemanticEvaluationRead(BaseModel):
    judge_version: str
    outcome: Literal["pass", "fail", "insufficient_evidence"] | None
    rationale: str | None
    confidence: float | None
    judge_configuration: dict[str, JsonValue]
    error: ModelFailureRead | None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class HumanReviewItemRead(BaseModel):
    id: str
    status: Literal["pending", "resolved"]
    reasons: list[
        Literal[
            "automatic_conflict",
            "low_confidence",
            "insufficient_evidence",
            "test_case_requires_review",
            "judge_failure",
        ]
    ]
    outcome: Literal["pass", "fail"] | None
    rationale: str | None
    created_at: datetime
    resolved_at: datetime | None

    @field_serializer("created_at", "resolved_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class HumanReviewQueueItemRead(HumanReviewItemRead):
    test_case_execution_id: str
    test_case_title: str
    application_version_name: str
    evaluation_run_id: str | None
    version_role: Literal["baseline", "candidate"] | None


class HumanReviewDecisionCreate(BaseModel):
    outcome: Literal["pass", "fail"]
    rationale: str = Field(min_length=1, max_length=2000)

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        rationale = value.strip()
        if not rationale:
            raise ValueError("A Human Review rationale is required.")
        return rationale


class TestCaseExecutionRead(BaseModel):
    id: str
    application_version_id: str
    application_version_name: str
    test_case_id: str
    test_case_key: str
    test_case_title: str
    test_case_severity: Literal["normal", "important", "release_blocking"]
    status: Literal["pending", "running", "completed", "failed"]
    prompt_context: dict[str, JsonValue]
    model_response: str | None
    usage: ModelUsageRead | None
    latency_ms: int | None
    error: ModelFailureRead | None
    deterministic_evaluation: DeterministicEvaluationRead | None
    semantic_evaluation: SemanticEvaluationRead | None
    human_review_item: HumanReviewItemRead | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    @field_serializer("created_at", "started_at", "completed_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class HumanReviewDetailRead(HumanReviewQueueItemRead):
    execution: TestCaseExecutionRead


class EvaluationRunCreate(BaseModel):
    baseline_version_id: str
    candidate_version_id: str
    evaluation_suite_id: str


class EvaluationRunVersionRead(BaseModel):
    id: str
    name: str


class EvaluationRunSuiteRead(BaseModel):
    id: str
    slug: str
    version: int
    name: str


class EvaluationRunProgressRead(BaseModel):
    total: int
    queued: int
    running: int
    completed: int
    failed: int


class DeterministicRuleCountsRead(BaseModel):
    passed: int
    failed: int
    total: int


class SeverityFailuresRead(BaseModel):
    normal: int
    important: int
    release_blocking: int


class VersionDeterministicSummaryRead(BaseModel):
    scored_test_cases: int
    passed_test_cases: int
    failed_test_cases: int
    correctness: DeterministicRuleCountsRead
    safety: DeterministicRuleCountsRead
    severity_failures: SeverityFailuresRead


class EvaluationRunDeterministicSummaryRead(BaseModel):
    baseline: VersionDeterministicSummaryRead
    candidate: VersionDeterministicSummaryRead
    new_regressions: int
    new_regressions_by_severity: SeverityFailuresRead
    existing_failures: int


class EvaluationRunExecutionRead(TestCaseExecutionRead):
    version_role: Literal["baseline", "candidate"]


class EvaluationRunRead(BaseModel):
    id: str
    baseline_version: EvaluationRunVersionRead
    candidate_version: EvaluationRunVersionRead
    evaluation_suite: EvaluationRunSuiteRead
    status: Literal["pending", "running", "completed", "failed"]
    progress: EvaluationRunProgressRead
    deterministic_summary: EvaluationRunDeterministicSummaryRead
    executions: list[EvaluationRunExecutionRead]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    @field_serializer("created_at", "started_at", "completed_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ExternalSafetyEvidenceRead(BaseModel):
    id: str
    evaluation_run_id: str
    source_product: str
    integration_contract: str
    schema_version: str
    source_digest: str
    source_bundle_id: str
    source_pair_id: str
    baseline_agent_version_id: str
    candidate_agent_version_id: str
    baseline_evidence_fingerprint: str
    candidate_evidence_fingerprint: str
    baseline_verdict: Literal["effective", "ineffective", "inconclusive"]
    candidate_verdict: Literal["effective", "ineffective", "inconclusive"]
    divergence_summary: str
    imported_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("imported_at")
    def serialize_imported_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


Severity = Literal["normal", "important", "release_blocking"]


class ReleaseRuleCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=160)
    blocking_severities: list[Severity] = Field(min_length=1)
    new_regression_severities: list[Severity] = Field(min_length=1)
    require_resolved_reviews: bool
    maximum_correctness_drop: float = Field(ge=0, le=1)
    minimum_candidate_safety_rate: float = Field(ge=0, le=1)
    maximum_candidate_average_latency_ms: int | None = Field(default=None, ge=0)
    maximum_candidate_total_cost_usd: float | None = Field(default=None, ge=0)

    @field_validator("blocking_severities", "new_regression_severities")
    @classmethod
    def validate_unique_severities(cls, value: list[Severity]) -> list[Severity]:
        if len(value) != len(set(value)):
            raise ValueError("Release Rule severities must be unique.")
        return value

    @field_validator("blocking_severities")
    @classmethod
    def require_release_blocking_gate(cls, value: list[Severity]) -> list[Severity]:
        if "release_blocking" not in value:
            raise ValueError("Release-blocking failures cannot be disabled.")
        return value

    @field_validator("new_regression_severities")
    @classmethod
    def require_important_regression_gate(
        cls,
        value: list[Severity],
    ) -> list[Severity]:
        if "important" not in value:
            raise ValueError("Important new regressions cannot be disabled.")
        return value


class ReleaseRuleRead(ReleaseRuleCreate):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ReleaseDecisionCreate(BaseModel):
    evaluation_run_id: str
    release_rule_id: str


class ReleaseDecisionReasonRead(BaseModel):
    code: str
    message: str
    execution_ids: list[str]
    observed: JsonValue | None
    threshold: JsonValue | None


class ReleaseDecisionRuleRead(BaseModel):
    id: str
    slug: str
    version: int
    name: str


class ReleaseDecisionRead(BaseModel):
    id: str
    evaluation_run_id: str
    release_rule: ReleaseDecisionRuleRead
    outcome: Literal["pass", "fail", "manual_review_required"]
    reasons: list[ReleaseDecisionReasonRead]
    metrics: dict[str, JsonValue]
    evidence_fingerprint: str
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
