from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import Literal

from pydantic import ValidationError

from app.agent.config import ToolConfig
from app.core.errors import ValidationAppError
from app.models.chat import WidgetPayload

TITLE_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
SVG_FRAGMENT_PATTERN = re.compile(r"^\s*(<svg[\s\S]*?</svg>)\s*$", re.IGNORECASE)
STANDALONE_SVG_WITH_STYLE_WRAPPER_PATTERN = re.compile(
    r"^\s*(?:<style\b[\s\S]*?</style>\s*)+(<svg[\s\S]*?</svg>)\s*$",
    re.IGNORECASE,
)
COMMENT_PATTERN = re.compile(r"<!--[\s\S]*?-->", re.IGNORECASE)
STYLE_TAG_PATTERN = re.compile(r"<style\b", re.IGNORECASE)
STYLE_BLOCK_PATTERN = re.compile(r"<style\b[\s\S]*?</style>", re.IGNORECASE)
SCRIPT_TAG_PATTERN = re.compile(r"<script\b", re.IGNORECASE)
SCRIPT_END_PATTERN = re.compile(r"</script\s*>", re.IGNORECASE)
SCRIPT_BLOCK_PATTERN = re.compile(
    r"<script\b([^>]*)>([\s\S]*?)</script\s*>",
    re.IGNORECASE,
)
SCRIPT_SRC_PATTERN = re.compile(r"\bsrc\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
MODULE_IMPORT_URL_PATTERN = re.compile(
    r"(?:from\s*['\"]|import\(\s*['\"])(https?://[^'\"]+)['\"]",
    re.IGNORECASE,
)
LINK_TAG_PATTERN = re.compile(r"<link\b", re.IGNORECASE)
NON_STYLE_SCRIPT_TAG_PATTERN = re.compile(
    r"<(?!/?(?:style|script)\b)[a-z][^>]*>",
    re.IGNORECASE,
)
SVG_VIEWBOX_PATTERN = re.compile(
    r"viewBox\s*=\s*['\"]\s*0\s+0\s+680(?:\s+H|\s+\d+(?:\.\d+)?)\s*['\"]",
    re.IGNORECASE,
)
SVG_WIDTH_PATTERN = re.compile(r"width\s*=\s*['\"]100%['\"]", re.IGNORECASE)
SVG_TEXT_TAG_PATTERN = re.compile(r"<text\b[^>]*>", re.IGNORECASE)
SVG_ARROW_PATH_PATTERN = re.compile(
    r"<path\b[^>]*marker-end\s*=\s*['\"]url\(#arrow\)['\"][^>]*>",
    re.IGNORECASE,
)
CSS_VAR_REFERENCE_PATTERN = re.compile(r"var\(\s*(--[a-z0-9-]+)\s*[,)]", re.IGNORECASE)
CLASS_NAME_PATTERN = re.compile(r"class\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
SUPPORTED_CSS_VARIABLES = {
    "--color-background-primary",
    "--color-background-secondary",
    "--color-background-tertiary",
    "--color-background-info",
    "--color-background-success",
    "--color-background-warning",
    "--color-background-danger",
    "--color-text-primary",
    "--color-text-secondary",
    "--color-text-tertiary",
    "--color-text-info",
    "--color-text-success",
    "--color-text-warning",
    "--color-text-danger",
    "--color-border-tertiary",
    "--color-border-secondary",
    "--color-border-primary",
    "--color-border-info",
    "--color-border-success",
    "--color-border-warning",
    "--color-border-danger",
    "--font-sans",
    "--font-mono",
    "--font-serif",
    "--border-radius-sm",
    "--border-radius-md",
    "--border-radius-lg",
    "--border-radius-xl",
    "--p",
    "--s",
    "--t",
    "--bg2",
    "--b",
}
SUPPORTED_COLOR_RAMP_CLASSES = {
    "c-purple",
    "c-teal",
    "c-amber",
    "c-coral",
    "c-blue",
    "c-green",
    "c-pink",
    "c-gray",
    "c-red",
}
ALLOWED_SCRIPT_CDN_HOSTS = {
    "cdnjs.cloudflare.com",
    "esm.sh",
    "cdn.jsdelivr.net",
    "unpkg.com",
}


def build_widget_payload(
    *,
    title: str,
    loading_messages: list[str],
    widget_code: str,
    tool_config: ToolConfig,
) -> WidgetPayload:
    normalized_title = title.strip()
    normalized_code = _normalize_widget_code(widget_code)
    normalized_messages = [message.strip() for message in loading_messages if message.strip()]

    if not TITLE_PATTERN.fullmatch(normalized_title):
        raise ValidationAppError("Widget title must be snake_case.")
    if not 1 <= len(normalized_messages) <= tool_config.max_loading_messages:
        raise ValidationAppError("Widget loading_messages must contain between 1 and 4 items.")
    if not normalized_code:
        raise ValidationAppError("Widget code cannot be empty after normalization.")
    if len(normalized_code) > tool_config.max_widget_code_chars:
        raise ValidationAppError("Widget code exceeds the configured size limit.")

    errors = _collect_widget_code_errors(normalized_code)
    if errors:
        raise ValidationAppError(
            "; ".join(errors),
            details={"violations": errors},
        )

    try:
        lowered_code = normalized_code.lower()
        kind: Literal["svg", "html"] = "svg" if lowered_code.startswith("<svg") else "html"
        return WidgetPayload(
            title=normalized_title,
            loading_messages=normalized_messages,
            widget_code=normalized_code,
            kind=kind,
        )
    except ValidationError as exc:
        raise ValidationAppError(
            "Widget payload validation failed.",
            details={"errors": exc.errors()},
        ) from exc


def _normalize_widget_code(widget_code: str) -> str:
    normalized_code = widget_code.strip().replace("\ufeff", "")

    svg_match = SVG_FRAGMENT_PATTERN.fullmatch(normalized_code)
    if svg_match is not None:
        return svg_match.group(1).strip()

    return normalized_code


def _collect_widget_code_errors(widget_code: str) -> list[str]:
    errors: list[str] = []
    lowered_code = widget_code.lower()
    disallowed_patterns = ("<html", "<body", "<head", "<!doctype")
    if any(pattern in lowered_code for pattern in disallowed_patterns):
        errors.append("Widget code contains disallowed document-level markup.")
    if COMMENT_PATTERN.search(widget_code):
        errors.append("Widget code cannot include HTML comments.")
    if STANDALONE_SVG_WITH_STYLE_WRAPPER_PATTERN.fullmatch(widget_code):
        errors.append(
            "Standalone SVG widget code must start directly with <svg>. "
            "Do not wrap a single SVG in a top-level <style> block."
        )

    errors.extend(_validate_css_variable_usage(widget_code))

    kind: Literal["svg", "html"] = "svg" if lowered_code.startswith("<svg") else "html"
    if kind == "html":
        errors.extend(_validate_html_widget_code(widget_code))
    else:
        errors.extend(_validate_svg_widget_code(widget_code))

    return errors


def _validate_html_widget_code(widget_code: str) -> list[str]:
    errors: list[str] = []
    lowered = widget_code.lower()
    if "position:fixed" in lowered or "position: fixed" in lowered:
        errors.append(
            "HTML widget code cannot use position:fixed because iframe auto-sizing "
            "depends on intrinsic document height."
        )
    if "localstorage" in lowered or "sessionstorage" in lowered or "indexeddb" in lowered:
        errors.append(
            "HTML widget code cannot use localStorage, sessionStorage, or IndexedDB in the sandbox."
        )
    if "/*" in lowered:
        errors.append("HTML widget code cannot include CSS block comments.")
    if LINK_TAG_PATTERN.search(widget_code):
        errors.append(
            "HTML widget code cannot include <link> tags. Use the host-injected styles "
            "and allowed CDN <script> tags only."
        )

    first_tag = re.match(r"\s*<([a-z0-9]+)", widget_code, flags=re.IGNORECASE)
    if first_tag is None or first_tag.group(1).lower() != "style":
        errors.append(
            "HTML widget code must start with a <style> block before visible content."
        )

    script_matches = list(SCRIPT_TAG_PATTERN.finditer(widget_code))
    style_matches = list(STYLE_TAG_PATTERN.finditer(widget_code))
    if not style_matches:
        errors.append("HTML widget code must include a <style> block.")

    if script_matches:
        first_script_start = script_matches[0].start()
        if any(style.start() > first_script_start for style in style_matches):
            errors.append(
                "HTML widget code must place <style> before any <script> tags."
            )

        content_before_scripts = widget_code[:first_script_start]
        content_without_styles = STYLE_BLOCK_PATTERN.sub("", content_before_scripts)
        if NON_STYLE_SCRIPT_TAG_PATTERN.search(content_without_styles) is None:
            errors.append(
                "HTML widget code must contain visible markup before scripts."
            )

        script_end_matches = list(SCRIPT_END_PATTERN.finditer(widget_code))
        if script_end_matches:
            after_last_script = widget_code[script_end_matches[-1].end() :]
            if after_last_script.strip():
                errors.append(
                    "HTML widget code must keep scripts at the end of the fragment."
                )

    saw_inline_logic_script = False
    for attrs, script_body in SCRIPT_BLOCK_PATTERN.findall(widget_code):
        src_match = SCRIPT_SRC_PATTERN.search(attrs)
        if src_match:
            src = src_match.group(1)
            host = urlparse(src).hostname or ""
            if not src.lower().startswith("https://") or host not in ALLOWED_SCRIPT_CDN_HOSTS:
                errors.append(
                    f"HTML widget script source '{src}' is not allowed. "
                    "Only cdnjs.cloudflare.com, esm.sh, cdn.jsdelivr.net, and unpkg.com are supported."
                )
            if saw_inline_logic_script:
                errors.append(
                    "HTML widget code must keep CDN <script src=...> tags before inline logic scripts."
                )
        else:
            saw_inline_logic_script = True
            for import_url in MODULE_IMPORT_URL_PATTERN.findall(script_body):
                host = urlparse(import_url).hostname or ""
                if (
                    not import_url.lower().startswith("https://")
                    or host not in ALLOWED_SCRIPT_CDN_HOSTS
                ):
                    errors.append(
                        f"HTML widget module import '{import_url}' is not allowed. "
                        "Use only esm.sh, cdnjs.cloudflare.com, cdn.jsdelivr.net, or unpkg.com."
                    )
    return errors


def _validate_svg_widget_code(widget_code: str) -> list[str]:
    errors: list[str] = []
    if not SVG_WIDTH_PATTERN.search(widget_code):
        errors.append("SVG widget code must include width='100%'.")
    if not SVG_VIEWBOX_PATTERN.search(widget_code):
        errors.append(
            "SVG widget code must use viewBox='0 0 680 H' (with computed H)."
        )
    if "<defs" not in widget_code.lower() or "id=\"arrow\"" not in widget_code.lower().replace("'", '"'):
        errors.append("SVG widget code must include <defs> with an arrow marker id='arrow'.")

    text_tags = SVG_TEXT_TAG_PATTERN.findall(widget_code)
    if text_tags:
        missing_baseline = [
            tag for tag in text_tags if "dominant-baseline" not in tag.lower()
        ]
        if missing_baseline:
            errors.append(
                "Every SVG <text> element must include dominant-baseline='central'."
            )
        missing_text_class = [
            tag
            for tag in text_tags
            if re.search(r"class\s*=\s*['\"][^'\"]*\b(?:t|ts|th)\b", tag.lower()) is None
        ]
        if missing_text_class:
            errors.append(
                "Every SVG <text> element must use one of the injected text classes: t, ts, or th."
            )

    for path_tag in SVG_ARROW_PATH_PATTERN.findall(widget_code):
        lowered_path = path_tag.lower()
        has_fill_none = re.search(r"fill\s*=\s*['\"]none['\"]", lowered_path) is not None
        has_arr_class = re.search(r"class\s*=\s*['\"][^'\"]*\barr\b", lowered_path) is not None
        if not has_fill_none and not has_arr_class:
            errors.append(
                "SVG connector paths that use marker-end='url(#arrow)' must declare fill='none' or class='arr'."
            )
    return errors


def _validate_css_variable_usage(widget_code: str) -> list[str]:
    errors: list[str] = []
    for var_name in CSS_VAR_REFERENCE_PATTERN.findall(widget_code):
        lowered = var_name.lower()
        if lowered in SUPPORTED_CSS_VARIABLES:
            continue
        errors.append(
            f"Unsupported CSS variable '{var_name}'. "
            "Use only the exact host-injected design tokens from the guide, such as "
            "--color-text-info, --color-background-secondary, --font-sans, "
            "--border-radius-md, or SVG shorthand vars --p/--s/--t/--bg2/--b."
        )

    for class_attr in CLASS_NAME_PATTERN.findall(widget_code):
        for class_name in class_attr.split():
            lowered = class_name.lower()
            if lowered.startswith("c-") and lowered not in SUPPORTED_COLOR_RAMP_CLASSES:
                errors.append(
                    f"Unsupported color ramp class '{class_name}'. "
                    "Use only exact ramp classes like c-purple, c-teal, c-amber, "
                    "c-coral, c-blue, c-green, c-pink, c-gray, or c-red."
                )
    return errors
