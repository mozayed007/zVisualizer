from __future__ import annotations

import re

from app.agent.config import (
    AgentDocReference,
    VisualAgentConfig,
    get_agent_config,
    resolve_source_documents,
)
from app.core.settings import Settings, get_settings

DOC_KEYWORDS = (
    "must",
    "never",
    "always",
    "required",
    "rule",
    "show_widget",
    "sendprompt",
    "viewbox",
    "illustrative",
    "flowchart",
    "structural",
    "html",
    "svg",
    "position: fixed",
    "design token",
    "c-{ramp}",
)
MAX_DOC_LINE_LENGTH = 220
SYSTEM_DOC_LINES_PER_FILE = 12
VISUAL_DOC_LINES_PER_FILE = 8
EXCERPT_DOCS_HEADING = "Authoritative source-doc contract excerpts (load-bearing runtime context):"
FULL_SKILL_DOCS_HEADING = (
    "Authoritative source-doc contract (full skill docs enabled for docs/skill/*.md):"
)


def _is_full_skill_doc(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return normalized.startswith("docs/skill/") and normalized.endswith(".md")


def _normalize_doc_line(raw_line: str) -> str:
    line = raw_line.strip()
    if not line:
        return ""

    # Source docs can include html and markdown formatting; runtime prompts need plain text.
    line = re.sub(r"<[^>]+>", "", line).strip()
    line = line.lstrip("-* ").strip()
    line = re.sub(r"^\d+\.\s*", "", line)
    return line


def _extract_doc_lines(content: str, *, max_lines: int) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()

    for raw_line in content.splitlines():
        line = _normalize_doc_line(raw_line)
        if not line or line == "```":
            continue

        lowered = line.lower()
        is_heading = raw_line.strip().startswith("#")
        has_keyword = any(keyword in lowered for keyword in DOC_KEYWORDS)
        if not is_heading and not has_keyword:
            continue

        if len(line) > MAX_DOC_LINE_LENGTH:
            line = f"{line[: MAX_DOC_LINE_LENGTH - 1]}…"
        if line in seen:
            continue

        seen.add(line)
        selected.append(line)
        if len(selected) >= max_lines:
            break

    if selected:
        return selected

    fallback_lines = [
        _normalize_doc_line(line)
        for line in content.splitlines()
        if _normalize_doc_line(line)
    ]
    return fallback_lines[:max_lines]


def _build_excerpt_source_doc_section(
    doc_ref: AgentDocReference,
    content: str,
    *,
    max_lines_per_file: int,
) -> str | None:
    lines = _extract_doc_lines(content, max_lines=max_lines_per_file)
    if not lines:
        return None
    section_lines = [f"{doc_ref.label} ({doc_ref.path}):"]
    section_lines.extend(f"- {line}" for line in lines)
    return "\n".join(section_lines)


def _build_full_text_source_doc_section(
    doc_ref: AgentDocReference,
    content: str,
) -> str | None:
    normalized_content = content.strip()
    if not normalized_content:
        return None
    return "\n".join(
        [
            f"{doc_ref.label} ({doc_ref.path}) full text:",
            normalized_content,
        ]
    )


def _build_source_doc_contract(
    config: VisualAgentConfig,
    *,
    max_lines_per_file: int,
    load_full_skill_docs_on_session_start: bool = False,
) -> str:
    doc_sections: list[str] = []
    included_full_skill_docs = False

    for doc_ref, _, content in resolve_source_documents(config):
        section: str | None
        if load_full_skill_docs_on_session_start and _is_full_skill_doc(doc_ref.path):
            section = _build_full_text_source_doc_section(doc_ref, content)
            included_full_skill_docs = included_full_skill_docs or section is not None
        else:
            section = _build_excerpt_source_doc_section(
                doc_ref,
                content,
                max_lines_per_file=max_lines_per_file,
            )

        if section:
            doc_sections.append(section)

    heading = FULL_SKILL_DOCS_HEADING if included_full_skill_docs else EXCERPT_DOCS_HEADING
    return "\n\n".join([heading, *doc_sections])


def build_system_prompt(
    config: VisualAgentConfig,
    *,
    load_full_skill_docs_on_session_start: bool = False,
) -> str:
    agent = config.agent
    prompt_contract = agent.prompt_contract
    sections = [
        f"You are {agent.name}, an expert visual learning companion.",
        f"Subject area: {agent.subject_area}.",
        f"Learner profile: {agent.learner_profile}.",
        f"Tone: {agent.tone}.",
        "Follow the YAML runtime prompt contract exactly.",
        f"Mandatory skill loading rule: {prompt_contract.mandatory_skill_loading_rule}",
        f"Quality bar: {prompt_contract.target_quality_bar}",
        "The host application, renderer, and validator enforce the platform contract.",
        "The configured source docs are runtime context for this turn and are not optional.",
        "Distilled runtime routing rules (align with docs/claude-visuals-guide-v2.html):",
        "- Use plain text when a visual would not materially improve understanding.",
        "- Use SVG for reference maps, architecture, containment, comparisons, and mechanism visuals when there is no real parameter to vary.",
        "- Use HTML widgets when the underlying system has a control the learner should vary (step index, learning rate, frequency, etc.) or when stepping through stages teaches better than one static frame.",
        "- Prefer illustrative diagrams over flowcharts for mechanism explanation; avoid defaulting to box-and-arrow flowcharts for intuition questions.",
        "- Use a side-by-side comparison layout when the learner asks for differences between two concepts.",
        "- Interactivity is for pedagogy, not decoration — every slider, button, or step must change something that matters to understanding.",
    ]

    if prompt_contract.enforce_platform_requirements:
        sections.append(
            "You must obey the platform requirements for widget structure, sandboxing, "
            "parent/iframe messaging, accessibility, and design-token usage."
        )

    if prompt_contract.mandatory_visual_rules:
        visual_rules = [f"- {rule}" for rule in prompt_contract.mandatory_visual_rules]
        sections.append("\n".join(["Mandatory visual rules:"] + visual_rules))
    if prompt_contract.pedagogical_rules:
        pedagogical_rules = [f"- {rule}" for rule in prompt_contract.pedagogical_rules]
        sections.append("\n".join(["Mandatory pedagogical rules:"] + pedagogical_rules))

    sections.append(
        _build_source_doc_contract(
            config,
            max_lines_per_file=SYSTEM_DOC_LINES_PER_FILE,
            load_full_skill_docs_on_session_start=load_full_skill_docs_on_session_start,
        )
    )

    if agent.response_style.ask_one_check_question:
        sections.append("Ask at most one comprehension check question per response.")
    if agent.response_style.prefer_visual_when_helpful:
        sections.append("Prefer a visual whenever it materially improves understanding.")
    if agent.response_style.never_stack_widgets_without_text:
        sections.append("Never place two visuals back-to-back without connecting prose.")

    sections.append(
        "When a visual is needed, call the show_widget tool with validated SVG or "
        "HTML widget code."
    )
    sections.append(
        "show_widget title contract: the title must be short snake_case only, for example "
        "'dense_vs_moe_architecture'. Never use spaces, punctuation, parentheses, or title case."
    )
    sections.append(
        "Unless the learner explicitly asks for multiple visuals, prefer one strong final "
        "show_widget call per turn rather than multiple separate widgets."
    )
    sections.append(
        "Choose SVG or HTML using the decision logic from claude-visuals-guide-v2: "
        "static explanatory diagram → SVG; parameter-driven or staged process → HTML. "
        "Never add JS chrome that does not encode a teaching-relevant variable."
    )
    sections.append(
        "If you call show_widget, still finish the turn with one brief connecting "
        "sentence after the tool call. Do not end the turn immediately after the tool."
    )
    sections.append(
        "Widget output contract: "
        "SVG must use viewBox='0 0 680 H', include arrow defs, use dominant-baseline='central', "
        "and keep connector paths fill='none'."
    )
    sections.append(
        "SVG formatting contract: "
        "standalone SVG widget_code must start directly with <svg>. "
        "Do not wrap a single SVG in a top-level <style> block."
    )
    sections.append(
        "Token contract: "
        "use only host-supported tokens and classes: c-{ramp}, --color-*, --font-*, "
        "--border-radius-*, and SVG shorthand vars --p/--s/--t/--bg2/--b. "
        "Never invent variables like --c-purple-500."
    )
    sections.append(
        "Exact token examples: "
        "valid variables include --color-text-info, --color-background-secondary, "
        "--color-border-secondary, --font-sans, and --border-radius-md. "
        "Valid color-ramp classes are exactly c-purple, c-teal, c-amber, c-coral, "
        "c-blue, c-green, c-pink, c-gray, and c-red. "
        "Never use palette-stop names like --color-blue-200 or classes like c-teal-200."
    )
    sections.append(
        "HTML widget contract: "
        "Emit a fragment only. Structure it in this order: style, visible content, CDN scripts, then logic script. "
        "Do not emit DOCTYPE, html, head, body, or comments."
    )
    sections.append(
        "Detailed HTML rules: "
        "no localStorage, sessionStorage, IndexedDB, or position:fixed. "
        "Use only approved script CDNs: cdnjs.cloudflare.com, esm.sh, cdn.jsdelivr.net, and unpkg.com. "
        "Keep CDN script tags before inline logic. Do not emit <link> tags."
    )
    sections.append(
        "Detailed HTML behavior rules: "
        "state lives in JS variables, learner-visible computed numbers must be rounded, "
        "charts/canvas need an explicit-height container, and any meaningful follow-up control "
        "should call sendPrompt(...) with a specific learner-voiced question."
    )
    sections.append(
        "Detailed HTML animation rules: "
        "animations must teach, stay lightweight, prefer transform/opacity motion, and respect "
        "prefers-reduced-motion."
    )
    sections.append(
        "Visual pedagogy contract: "
        "Keep the first visual focused and uncluttered, usually 3 to 6 major elements. "
        "Use progressive disclosure and meaningful sendPrompt follow-ups where useful."
    )
    if prompt_contract.visual_requests_require_tool_call:
        sections.append(
            "If the learner explicitly asks for a visual, diagram, architecture, flow, "
            "comparison, or interactive explanation, you must call show_widget unless "
            "the request is impossible to visualize faithfully."
        )
        sections.append(
            "Do not write SVG or HTML code directly in your text response. "
            "You MUST use the show_widget tool to provide visual content."
        )

    return "\n\n".join(sections)


def build_visual_generation_prompt(
    config: VisualAgentConfig,
    *,
    load_full_skill_docs_on_session_start: bool = False,
) -> str:
    agent = config.agent
    prompt_contract = agent.prompt_contract

    sections = [
        f"You are {agent.name}, but for this run you are operating as a dedicated visual generator.",
        "Your only job is to produce one valid widget payload for the learner request.",
        "Return structured widget data only. Do not return prose, markdown fences, or explanations.",
        "The widget must be learner-friendly, polished, dark-mode-safe, and immediately renderable.",
        "This visual generator exists because the main conversational pass may fail to call the tool.",
        "You must still follow the same visual skill and platform contracts.",
        f"Mandatory skill loading rule: {prompt_contract.mandatory_skill_loading_rule}",
        f"Quality bar: {prompt_contract.target_quality_bar}",
        "Critical output rules:",
        "- title must be short snake_case",
        "- loading_messages must contain 1 to 4 short learner-facing strings",
        "- widget_code must be raw SVG starting with <svg> or raw HTML fragment",
        "- never include DOCTYPE, html, head, or body",
        "- never return prose outside widget payload fields",
        "- never emit raw widget code as chat text",
        "- default to polished SVG for comparisons and architectures; use HTML when a real parameter or step sequence is load-bearing",
        "- prefer an overview visual with 3 to 6 major elements",
        "- make the visual explanatory, not decorative",
        "- for comparisons, place concepts side by side with parallel structure",
        "- for SVG, use viewBox='0 0 680 H' and include arrow defs",
        "- for SVG, use dominant-baseline='central' on text and fill='none' on connector paths",
        "- for standalone SVG, start widget_code directly with <svg>; do not put a top-level <style> block before it",
        "- for SVG text, use the injected classes t, ts, or th",
        "- for HTML, emit style first, then content, then CDN scripts, then logic",
        "- for HTML, never emit <link> tags, localStorage/sessionStorage/IndexedDB, or position:fixed",
        "- for HTML, keep approved CDN scripts before inline logic and use only cdnjs.cloudflare.com, esm.sh, cdn.jsdelivr.net, or unpkg.com",
        "- for HTML, keep learner-visible computed numbers rounded and give canvas/chart containers explicit height",
        "- use only host-supported tokens: c-{ramp}, --color-*, --font-*, --border-radius-*, and --p/--s/--t/--bg2/--b",
        "- never invent color variables like --c-purple-500",
        "- use exact token names like --color-text-info, not palette-stop tokens like --color-blue-200",
        "- use exact ramp classes like c-blue, not c-blue-200",
        "Distilled Claude-style visual guidance:",
        "- visuals should teach with spatial structure, not repeat the prose",
        "- comparisons should place both concepts side by side with clear labels",
        "- mechanisms should use illustrative diagrams before generic flowcharts",
        "- every meaningful node should be clickable when practical using sendPrompt(...)",
        "- progressive disclosure beats clutter",
    ]

    sections.append(
        _build_source_doc_contract(
            config,
            max_lines_per_file=VISUAL_DOC_LINES_PER_FILE,
            load_full_skill_docs_on_session_start=load_full_skill_docs_on_session_start,
        )
    )

    return "\n\n".join(sections)


def get_compiled_system_prompt(settings: Settings | None = None) -> str:
    active_settings = settings or get_settings()
    return build_system_prompt(
        get_agent_config(active_settings),
        load_full_skill_docs_on_session_start=(
            active_settings.agent_load_full_skill_docs_on_session_start
        ),
    )


def get_compiled_visual_generation_prompt(settings: Settings | None = None) -> str:
    active_settings = settings or get_settings()
    return build_visual_generation_prompt(
        get_agent_config(active_settings),
        load_full_skill_docs_on_session_start=(
            active_settings.agent_load_full_skill_docs_on_session_start
        ),
    )
