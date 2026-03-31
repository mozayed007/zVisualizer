from __future__ import annotations

import importlib
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.settings import PROJECT_ROOT, Settings, get_settings

yaml = importlib.import_module("yaml")


class AgentDocReference(BaseModel):
    path: str
    label: str


class ResponseStyleConfig(BaseModel):
    ask_one_check_question: bool = True
    prefer_visual_when_helpful: bool = True
    never_stack_widgets_without_text: bool = True


class FollowUpChipConfig(BaseModel):
    with_widget: list[str] = Field(default_factory=list)
    without_widget: list[str] = Field(default_factory=list)


class ToolConfig(BaseModel):
    name: str = "show_widget"
    max_loading_messages: int = 4
    max_widget_code_chars: int = 75000


class PromptContractConfig(BaseModel):
    source_docs_are_mandatory: bool = True
    source_docs_override_defaults: bool = True
    enforce_platform_requirements: bool = True
    never_treat_skill_docs_as_optional: bool = True
    visual_requests_require_tool_call: bool = True
    target_quality_bar: str = (
        "Match the polish, clarity, and beauty of the best claude.ai educational visuals."
    )
    mandatory_skill_loading_rule: str = (
        "Load all skill files before generating any visual output. "
        "Each file is load-bearing."
    )
    mandatory_visual_rules: list[str] = Field(default_factory=list)
    pedagogical_rules: list[str] = Field(default_factory=list)


class AgentDefinition(BaseModel):
    name: str
    provider: str
    model: str
    subject_area: str
    learner_profile: str
    tone: str
    response_style: ResponseStyleConfig
    follow_up_chips: FollowUpChipConfig
    tool: ToolConfig
    prompt_contract: PromptContractConfig = Field(default_factory=PromptContractConfig)
    source_docs: list[AgentDocReference]


class VisualAgentConfig(BaseModel):
    agent: AgentDefinition


def load_agent_config_from_path(path: Path) -> VisualAgentConfig:
    raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return VisualAgentConfig.model_validate(raw_data)


def resolve_source_documents(
    config: VisualAgentConfig,
) -> list[tuple[AgentDocReference, Path, str]]:
    resolved: list[tuple[AgentDocReference, Path, str]] = []
    for document in config.agent.source_docs:
        absolute_path = PROJECT_ROOT / document.path
        resolved.append(
            (document, absolute_path, absolute_path.read_text(encoding="utf-8"))
        )
    return resolved

def get_agent_config(settings: Settings | None = None) -> VisualAgentConfig:
    active_settings = settings or get_settings()
    return load_agent_config_from_path(active_settings.agent_config_path)
