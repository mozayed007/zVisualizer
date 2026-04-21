from pathlib import Path

from app.agent.config import load_agent_config_from_path
from app.agent.prompt import (
    build_system_prompt,
    build_visual_generation_prompt,
    get_compiled_system_prompt,
)
from app.agent.registry import AgentRegistry
from app.core.settings import Settings

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "agent.visual.yaml"
SVG_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "agent.svg.yaml"
FULL_SKILL_DOC_SNIPPET = "| File | Purpose | When to load |"
PLATFORM_REQUIREMENTS_BODY_SNIPPET = (
    "iframe.sandbox = 'allow-scripts allow-popups-to-escape-sandbox';"
)


def test_agent_config_loads_source_docs() -> None:
    config = load_agent_config_from_path(CONFIG_PATH)

    assert config.agent.id == "visualizer"
    assert config.agent.model.startswith("gemini-3")
    assert len(config.agent.source_docs) >= 3
    assert config.agent.prompt_contract.source_docs_are_mandatory is True
    assert "claude.ai educational visuals" in config.agent.prompt_contract.target_quality_bar


def test_system_prompt_uses_distilled_runtime_rules() -> None:
    config = load_agent_config_from_path(CONFIG_PATH)

    prompt = build_system_prompt(config)

    assert "show_widget" in prompt
    assert "Quality bar:" in prompt
    assert "Mandatory visual rules:" in prompt
    assert "finish the turn with one brief connecting sentence" in prompt
    assert "configured source docs are runtime context" in prompt
    assert "Use SVG for reference maps, architecture, containment, and mechanism visuals" in prompt
    assert "Use HTML widgets when the underlying system has a control" in prompt
    assert "claude-visuals-guide-v2.html" in prompt
    assert "Widget output contract:" in prompt
    assert "HTML widget contract:" in prompt
    assert "title must be short snake_case" in prompt
    assert "dense_vs_moe_architecture" in prompt
    assert "Authoritative source-doc contract excerpts" in prompt
    assert "docs/visualizer_skill/design-system.md" in prompt
    assert FULL_SKILL_DOC_SNIPPET not in prompt


def test_visual_generation_prompt_contains_distilled_guide_rules() -> None:
    config = load_agent_config_from_path(CONFIG_PATH)

    prompt = build_visual_generation_prompt(config)

    assert "Return structured widget data only." in prompt
    assert "for SVG, use viewBox='0 0 680 H' and include arrow defs" in prompt
    assert "for HTML, emit style first, then content, then CDN scripts, then logic" in prompt
    assert "Authoritative source-doc contract excerpts" in prompt
    assert "docs/visualizer_skill/svg-generation.md" in prompt


def test_compiled_system_prompt_respects_full_skill_doc_setting() -> None:
    excerpt_prompt = get_compiled_system_prompt(
        Settings(
            agent_config_path=CONFIG_PATH,
            agent_load_full_skill_docs_on_session_start=False,
        )
    )
    full_prompt = get_compiled_system_prompt(
        Settings(
            agent_config_path=CONFIG_PATH,
            agent_load_full_skill_docs_on_session_start=True,
        )
    )

    assert FULL_SKILL_DOC_SNIPPET not in excerpt_prompt
    assert "Authoritative source-doc contract excerpts" in excerpt_prompt
    assert FULL_SKILL_DOC_SNIPPET in full_prompt
    assert "master_skill (docs/visualizer_skill/SKILL.md) full text:" in full_prompt
    assert "full skill docs enabled for docs/skill/*.md" in full_prompt
    assert PLATFORM_REQUIREMENTS_BODY_SNIPPET not in full_prompt
    assert "platform_requirements (docs/PLATFORM-REQUIREMENTS.md):" in full_prompt


def test_visual_generation_prompt_can_inline_full_skill_docs_only() -> None:
    config = load_agent_config_from_path(CONFIG_PATH)

    prompt = build_visual_generation_prompt(
        config,
        load_full_skill_docs_on_session_start=True,
    )

    assert FULL_SKILL_DOC_SNIPPET in prompt
    assert "master_skill (docs/visualizer_skill/SKILL.md) full text:" in prompt
    assert PLATFORM_REQUIREMENTS_BODY_SNIPPET not in prompt
    assert "platform_requirements (docs/PLATFORM-REQUIREMENTS.md):" in prompt


def test_svg_agent_config_loads_source_docs() -> None:
    config = load_agent_config_from_path(SVG_CONFIG_PATH)

    assert config.agent.id == "svg"
    assert config.agent.display_name == "SVG Agent"
    assert any(doc.path == "docs/svg_skill/SKILL.md" for doc in config.agent.source_docs)
    assert any(
        doc.path == "docs/svg_skill/violation-detection.md" for doc in config.agent.source_docs
    )


def test_agent_registry_discovers_visualizer_and_svg_agents() -> None:
    registry = AgentRegistry(
        Settings(
            agent_config_dir=CONFIG_PATH.parent,
            default_agent_id="visualizer",
        )
    )

    catalog = registry.list_summaries()
    ids = {agent.id for agent in catalog.agents}

    assert catalog.default_agent_id == "visualizer"
    assert {"visualizer", "svg"}.issubset(ids)
