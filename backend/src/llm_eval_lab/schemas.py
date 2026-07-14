from datetime import UTC, datetime

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
