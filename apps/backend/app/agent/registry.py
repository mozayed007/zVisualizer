from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from app.agent.config import VisualAgentConfig, load_agent_configs_from_dir
from app.agent.prompt import build_system_prompt, build_visual_generation_prompt
from app.core.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class AgentPromptBundle:
    config: VisualAgentConfig
    system_prompt: str
    visual_generation_prompt: str


class AgentSummary(BaseModel):
    id: str
    name: str
    display_name: str
    description: str | None = None
    provider: str
    default_model: str


class AgentCatalogResponse(BaseModel):
    default_agent_id: str
    agents: list[AgentSummary]


class AgentRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        configs = load_agent_configs_from_dir(self.settings.agent_config_dir)
        if not configs:
            raise ValueError(
                f"No agent configs found in '{self.settings.agent_config_dir}'."
            )
        self._bundles = {
            agent_id: AgentPromptBundle(
                config=config,
                system_prompt=build_system_prompt(
                    config,
                    load_full_skill_docs_on_session_start=(
                        self.settings.agent_load_full_skill_docs_on_session_start
                    ),
                ),
                visual_generation_prompt=build_visual_generation_prompt(
                    config,
                    load_full_skill_docs_on_session_start=(
                        self.settings.agent_load_full_skill_docs_on_session_start
                    ),
                ),
            )
            for agent_id, config in configs.items()
        }
        if self.settings.default_agent_id not in self._bundles:
            raise ValueError(
                f"Default agent '{self.settings.default_agent_id}' is not configured."
            )

    def get(self, agent_id: str | None = None) -> AgentPromptBundle:
        resolved_agent_id = agent_id or self.settings.default_agent_id
        bundle = self._bundles.get(resolved_agent_id)
        if bundle is None:
            available = ", ".join(sorted(self._bundles)) or "none"
            raise ValueError(
                f"Unknown agent_id '{resolved_agent_id}'. Available agents: {available}"
            )
        return bundle

    def list_summaries(self) -> AgentCatalogResponse:
        agents = [
            AgentSummary(
                id=bundle.config.agent.id,
                name=bundle.config.agent.name,
                display_name=bundle.config.agent.display_name or bundle.config.agent.name,
                description=bundle.config.agent.description,
                provider=bundle.config.agent.provider,
                default_model=bundle.config.agent.model,
            )
            for bundle in self._bundles.values()
        ]
        return AgentCatalogResponse(
            default_agent_id=self.settings.default_agent_id,
            agents=agents,
        )
