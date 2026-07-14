from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer


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
