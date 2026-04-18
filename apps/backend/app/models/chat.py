from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class LearnerProfile(BaseModel):
    concepts_seen: list[str] = Field(default_factory=list)
    struggling_with: list[str] = Field(default_factory=list)
    interaction_count: int = 0


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    subject: str | None = None
    agent_id: str | None = Field(
        default=None,
        description="Optional backend agent/profile identifier for this turn.",
    )
    learner_profile: LearnerProfile | None = None
    model: str | None = Field(
        default=None,
        description="Optional Gemini model override for this turn.",
    )
    from_widget: str | None = Field(
        default=None,
        description="Snake_case widget title when the learner clicked sendPrompt or a chip tied to a widget.",
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("message cannot be empty")
        return text

    @field_validator("agent_id")
    @classmethod
    def normalize_agent_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        return text[7:] if text.startswith("models/") else text


class WidgetPayload(BaseModel):
    title: str
    loading_messages: list[str]
    widget_code: str
    kind: Literal["svg", "html"]


class AvailableModel(BaseModel):
    id: str
    resource_name: str
    display_name: str
    description: str | None = None
    input_token_limit: int | None = None
    output_token_limit: int | None = None
    supported_generation_methods: list[str] = Field(default_factory=list)
    thinking: bool = False
    chat_compatible: bool = False
    is_default: bool = False


class ModelCatalogResponse(BaseModel):
    default_model: str
    models: list[AvailableModel]


class AvailableAgent(BaseModel):
    id: str
    name: str
    display_name: str
    description: str | None = None
    provider: str
    default_model: str


class AgentCatalogResponse(BaseModel):
    default_agent_id: str
    agents: list[AvailableAgent]


class StreamEvent(BaseModel):
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class ConversationRecord(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    turn_count: int = 0
    subject: str | None = None
    agent_id: str | None = None
    learner_profile: LearnerProfile = Field(default_factory=LearnerProfile)
    message_history_json: str | None = None

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)
