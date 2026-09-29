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
PLATFORM_REQUIREMENTS_BODY_SNIPPET = "iframe.sandbox = 'allow-scripts allow-popups-to-escape-sandbox';"


def test_agent_config_loads_source_docs() -> None:
    config = load_agent_config_from_path(CONFIG_PATH)

    assert config.agent.id == "visualizer"
    assert config.agent.model.startswith("gemini-3")
    assert len(config.agent.source_docs) >= 3
    assert config.agent.prompt_contract.source_docs_are_mandatory is True
    assert "claude.ai educational visuals" in config.agent.prompt_contract.target_quality_bar


def test_system_prompt_uses_distilled_runtime_rules() -> None:
    config = load_agent_config_from_path(CONFIG_PATH)

    prompt = build_system_prompt(config, load_full_skill_docs_on_session_start=False)

    assert "show_widget" in prompt
    assert "Quality bar:" in prompt
    assert "Mandatory visual rules:" in prompt
    assert "finish the turn with one brief connecting sentence" in prompt
    assert "configured source docs are runtime context" in prompt
    assert "Use SVG for reference maps, architecture, containment, and mechanism visuals" in prompt
    assert "Use HTML widgets when the underlying system has a control" in prompt
    assert "tunable parameters" in prompt
    assert "interactive HTML widget" in prompt
    assert "claude-visuals-guide-v2.html" in prompt
    assert "Widget output contract:" in prompt
    assert "HTML widget contract:" in prompt
    assert "Color variety contract:" in prompt
    assert "Avoid defaulting to the same purple-teal-amber sequence repeatedly" in prompt
    assert "title must be short snake_case" in prompt
    assert "dense_vs_moe_architecture" in prompt
    assert "Authoritative source-doc contract excerpts" in prompt
    assert "skills/visualizer/design-system.md" in prompt
    assert FULL_SKILL_DOC_SNIPPET not in prompt


def test_visual_generation_prompt_contains_distilled_guide_rules() -> None:
    config = load_agent_config_from_path(CONFIG_PATH)

    prompt = build_visual_generation_prompt(config, load_full_skill_docs_on_session_start=False)

    assert "Return structured widget data only." in prompt
    assert "for SVG, use viewBox='0 0 680 H' and include arrow defs" in prompt
    assert "for HTML, emit style first, then content, then CDN scripts, then logic" in prompt
    assert "for comparisons of parameterized systems" in prompt
    assert "avoid repeating the same purple-teal-amber trio" in prompt
    assert "Authoritative source-doc contract excerpts" in prompt
    assert "skills/visualizer/svg-generation.md" in prompt


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
    assert "master_skill (skills/visualizer/SKILL.md) full text:" in full_prompt
    assert "priority skill docs inlined in full" in full_prompt
    assert PLATFORM_REQUIREMENTS_BODY_SNIPPET not in full_prompt
    assert "platform_requirements (docs/PLATFORM-REQUIREMENTS.md):" in full_prompt


def test_visual_generation_prompt_can_inline_priority_skill_docs_only() -> None:
    config = load_agent_config_from_path(CONFIG_PATH)

    prompt = build_visual_generation_prompt(
        config,
        load_full_skill_docs_on_session_start=True,
    )

    assert FULL_SKILL_DOC_SNIPPET in prompt
    assert "master_skill (skills/visualizer/SKILL.md) full text:" in prompt
    assert "design_system (skills/visualizer/design-system.md) full text:" in prompt
    assert PLATFORM_REQUIREMENTS_BODY_SNIPPET not in prompt
    assert "platform_requirements (docs/PLATFORM-REQUIREMENTS.md):" in prompt
    assert "svg_generation (skills/visualizer/svg-generation.md):" in prompt
    assert "svg_generation (skills/visualizer/svg-generation.md) full text:" not in prompt


def test_svg_agent_config_loads_source_docs() -> None:
    config = load_agent_config_from_path(SVG_CONFIG_PATH)

    assert config.agent.id == "svg"
    assert config.agent.display_name == "SVG Agent"
    assert config.agent.tool.template_id_required is True
    assert any(doc.path == "skills/svg/SKILL.md" for doc in config.agent.source_docs)
    assert any(doc.path == "skills/svg/violation-detection.md" for doc in config.agent.source_docs)


def test_svg_system_prompt_excludes_visualizer_html_contract() -> None:
    config = load_agent_config_from_path(SVG_CONFIG_PATH)

    prompt = build_system_prompt(config, load_full_skill_docs_on_session_start=False)

    assert "expert SVG template operator" in prompt
    assert "HTML widget contract:" not in prompt
    assert "viewBox='0 0 680 H'" not in prompt
    assert "claude-visuals-guide-v2" not in prompt
    assert "Color variety contract:" not in prompt


def test_svg_system_prompt_includes_template_identity_rules() -> None:
    config = load_agent_config_from_path(SVG_CONFIG_PATH)

    prompt = build_system_prompt(config, load_full_skill_docs_on_session_start=False)

    assert "template_id is required on every call" in prompt
    assert "Preserve source-template identity" in prompt
    assert "DISCOVER → SELECT → CLONE" in prompt


def test_visualizer_system_prompt_still_includes_html_contract() -> None:
    config = load_agent_config_from_path(CONFIG_PATH)

    prompt = build_system_prompt(config, load_full_skill_docs_on_session_start=False)

    assert "HTML widget contract:" in prompt
    assert "viewBox='0 0 680 H'" in prompt


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


def test_agent_registry_accepts_display_name_alias_case_insensitively() -> None:
    registry = AgentRegistry(
        Settings(
            agent_config_dir=CONFIG_PATH.parent,
            default_agent_id="visualizer",
        )
    )

    bundle = registry.get("Visualizer")

    assert bundle.config.agent.id == "visualizer"
    assert bundle.widget_fallback_prompt
