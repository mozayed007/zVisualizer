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
    template_id_required: bool = False


class PromptContractConfig(BaseModel):
    source_docs_are_mandatory: bool = True
    source_docs_override_defaults: bool = True
    enforce_platform_requirements: bool = True
    never_treat_skill_docs_as_optional: bool = True
    visual_requests_require_tool_call: bool = True
    target_quality_bar: str = "Match the polish, clarity, and beauty of the best claude.ai educational visuals."
    mandatory_skill_loading_rule: str = (
        "Load all skill files before generating any visual output. Each file is load-bearing."
    )
    mandatory_visual_rules: list[str] = Field(default_factory=list)
    pedagogical_rules: list[str] = Field(default_factory=list)


class AgentDefinition(BaseModel):
    id: str
    name: str
    display_name: str | None = None
    description: str | None = None
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


class AgentConfig(BaseModel):
    agent: AgentDefinition


VisualAgentConfig = AgentConfig


def load_agent_config_from_path(path: Path) -> AgentConfig:
    raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AgentConfig.model_validate(raw_data)


def resolve_source_documents(
    config: AgentConfig,
) -> list[tuple[AgentDocReference, Path, str]]:
    resolved: list[tuple[AgentDocReference, Path, str]] = []
    for document in config.agent.source_docs:
        absolute_path = PROJECT_ROOT / document.path
        resolved.append((document, absolute_path, absolute_path.read_text(encoding="utf-8")))
    return resolved


def load_agent_configs_from_dir(path: Path) -> dict[str, AgentConfig]:
    configs: dict[str, AgentConfig] = {}
    for config_path in sorted(path.glob("agent.*.yaml")):
        config = load_agent_config_from_path(config_path)
        configs[config.agent.id] = config
    return configs


def get_agent_config(settings: Settings | None = None, agent_id: str | None = None) -> AgentConfig:
    active_settings = settings or get_settings()
    configs = load_agent_configs_from_dir(active_settings.agent_config_dir)
    resolved_agent_id = agent_id or active_settings.default_agent_id
    if resolved_agent_id in configs:
        return configs[resolved_agent_id]

    if active_settings.agent_config_path.exists():
        legacy_config = load_agent_config_from_path(active_settings.agent_config_path)
        if agent_id is None or legacy_config.agent.id == resolved_agent_id:
            return legacy_config

    available = ", ".join(sorted(configs)) or "none"
    raise ValueError(f"Unknown agent_id '{resolved_agent_id}'. Available agents: {available}")
