from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from google import genai
from google.genai import types

from app.agent.config import ToolConfig
from app.agent.svg_preview_renderer import (
    NoopSvgPreviewRenderer,
    SvgPreviewRenderer,
)
from app.agent.svg_template_validator import validate_svg_template_instance
from app.agent.widget_validator import (
    VISUALIZER_RAW_SVG_KIND,
    build_template_instance_widget_payload,
    build_widget_payload,
)
from app.core.errors import ValidationAppError
from app.models.chat import WidgetPayload

SVG_FRAGMENT_PATTERN = re.compile(r"(<svg[\s\S]*?</svg>)", re.IGNORECASE)

# ServiceTier mapping for google-genai >=1.75.
# The SDK's GenerateContentConfig.service_tier now accepts lowercase string
# literals ('unspecified' | 'flex' | 'standard' | 'priority') instead of the
# legacy integer enum values. We keep the historical settings keys so existing
# environment configuration continues to work.
SERVICE_TIER_ENUM_MAP: dict[str, str] = {
    "SERVICE_TIER_UNSPECIFIED": "unspecified",
    "SERVICE_TIER_STANDARD": "standard",
    "SERVICE_TIER_PRIORITY": "priority",
    "SERVICE_TIER_FLEX": "flex",
}


def _get_service_tier_value(service_tier: str | None) -> str | None:
    """Map the historical SERVICE_TIER_* settings value to the lowercase string
    literal required by google-genai >=1.75. Returns ``None`` when unset.
    """
    if service_tier is None:
        return None
    return SERVICE_TIER_ENUM_MAP.get(service_tier, service_tier)


@dataclass(frozen=True, slots=True)
class SvgVisionRepairDraft:
    request_message: str
    widget_title: str
    template_relative_path: str
    source_svg: str
    working_svg: str
    content_lines: list[str]
    violations: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SvgVisionRawRepairDraft:
    widget_title: str
    working_svg: str
    text_violations: list[str]
    geometry_violations: list[dict[str, Any]]


class _GenerateContentClient(Protocol):
    def generate_content(
        self,
        *,
        model: str,
        contents: list[types.Part | str],
        config: types.GenerateContentConfig,
    ) -> Any: ...


class SvgVisionRepairService:
    def __init__(
        self,
        *,
        api_key: str | None,
        model_name: str | None,
        service_tier: str | None = None,
        preview_renderer: SvgPreviewRenderer | None = None,
        generate_content_client: _GenerateContentClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.service_tier = service_tier
        self.preview_renderer = preview_renderer or NoopSvgPreviewRenderer()
        self._generate_content_client = generate_content_client
        self._cached_client: _GenerateContentClient | None = None

    @property
    def is_enabled(self) -> bool:
        return bool(self.api_key and self.model_name)

    def repair_from_validation_error(
        self,
        *,
        error: ValidationAppError,
        tool_config: ToolConfig,
    ) -> WidgetPayload | None:
        if not self.is_enabled:
            return None

        draft = self._draft_from_error(error)
        if draft is None:
            return None

        response = self._client().generate_content(
            model=self.model_name or "",
            contents=self._build_contents(draft),
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=16_384,
                service_tier=_get_service_tier_value(self.service_tier),
            ),
        )
        response_text = (getattr(response, "text", None) or "").strip()
        repaired_svg = self._extract_svg_markup(response_text)
        if not repaired_svg:
            return None

        validate_svg_template_instance(
            source_svg=draft.source_svg,
            working_svg=repaired_svg,
        )
        return build_template_instance_widget_payload(
            title=draft.widget_title,
            loading_messages=[
                "Static validation found issues",
                "Sending SVG plus violations to the repair model",
                "Revalidating the repaired clone",
            ],
            widget_code=repaired_svg,
            tool_config=tool_config,
        )

    def repair_raw_visualizer_svg(
        self,
        *,
        error: ValidationAppError,
        tool_config: ToolConfig,
    ) -> WidgetPayload | None:
        """Attempt to repair a raw visualizer SVG that failed geometric validation.

        This is a single-shot repair: the model is given the failing SVG plus the
        listed violations and asked to emit a corrected version. The repaired SVG
        is re-validated through :func:`build_widget_payload`; if it still fails
        the caller sees ``None`` and the original error bubbles up.
        """

        if not self.is_enabled:
            return None

        draft = self._raw_draft_from_error(error)
        if draft is None:
            return None

        response = self._client().generate_content(
            model=self.model_name or "",
            contents=self._build_raw_contents(draft),
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=16_384,
                service_tier=_get_service_tier_value(self.service_tier),
            ),
        )
        response_text = (getattr(response, "text", None) or "").strip()
        repaired_svg = self._extract_svg_markup(response_text)
        if not repaired_svg:
            return None

        try:
            return build_widget_payload(
                title=draft.widget_title,
                loading_messages=[
                    "Static validation found issues",
                    "Repairing the visualizer SVG with Gemini",
                    "Revalidating the repaired widget",
                ],
                widget_code=repaired_svg,
                tool_config=tool_config,
            )
        except ValidationAppError:
            return None

    def _raw_draft_from_error(
        self, error: ValidationAppError
    ) -> SvgVisionRawRepairDraft | None:
        details = error.details
        if details.get("kind") != VISUALIZER_RAW_SVG_KIND:
            return None
        source_svg = details.get("source_svg")
        widget_title = details.get("widget_title")
        text_violations = details.get("violations")
        geometry_violations = details.get("geometry_violations", [])
        if not isinstance(source_svg, str) or not isinstance(widget_title, str):
            return None
        if not isinstance(text_violations, list):
            return None
        if not isinstance(geometry_violations, list):
            geometry_violations = []
        return SvgVisionRawRepairDraft(
            widget_title=widget_title,
            working_svg=source_svg,
            text_violations=[str(entry) for entry in text_violations],
            geometry_violations=[
                entry for entry in geometry_violations if isinstance(entry, dict)
            ],
        )

    def _build_raw_contents(
        self, draft: SvgVisionRawRepairDraft
    ) -> list[types.Part | str]:
        violation_lines: list[str] = []
        for entry in draft.geometry_violations[:12]:
            code = str(entry.get("code", "unknown"))
            message = str(entry.get("message", "unknown violation"))
            hint = entry.get("element_hint")
            line = f"- {code}: {message}"
            if isinstance(hint, str) and hint:
                line += f" (element: {hint})"
            violation_lines.append(line)
        if not violation_lines:
            violation_lines = [f"- {text}" for text in draft.text_violations[:12]]

        preview = self.preview_renderer.render(draft.working_svg)

        prompt = "\n".join(
            [
                "You are repairing a raw visualizer-agent SVG that failed geometric validation.",
                f"Target widget title: {draft.widget_title}",
                "Hard invariants for the visualizer contract:",
                "- Keep viewBox='0 0 680 H' with H recomputed from content.",
                "- Every <text> must use one of the injected classes th, t, or ts and",
                "  include dominant-baseline='central'.",
                "- Every <text> bounding box must fit inside its nearest container <rect>",
                "  with roughly 12px of inner padding on each side.",
                "- rect.width must satisfy: width >= longest_line_chars * font_size *",
                "  weight_factor * 1.08 + 24  (th=14/0.58, t=14/0.52, ts=12/0.50).",
                "- rect.height must fit line_count * font_size * 1.35 with 16px vertical padding.",
                "- Node rectangles must not overlap each other. Callouts/annotations must",
                "  sit in clear space (or inside a dedicated non-overlapping rect).",
                "- Keep all content inside the 0..680 x 0..H viewBox.",
                "- Preserve c-{ramp} classes, arrow defs, and connector fill='none'.",
                "Current validation violations (fix ALL of them):",
                *violation_lines,
                "Return only the repaired raw <svg>...</svg> markup with no prose or",
                "markdown fences. Shorten long text, wrap with <tspan x='...' dy='...'>,",
                "widen rects, or move callouts as needed — never leave text overflowing",
                "its rect or overlapping a sibling node.",
            ]
        )

        contents: list[types.Part | str] = [prompt]
        if preview is not None:
            contents.append(
                types.Part.from_bytes(data=preview.data, mime_type=preview.mime_type)
            )
            contents.append(
                types.Part.from_text(text=f"Rendered preview attached: {preview.description}")
            )
        contents.append(
            types.Part.from_bytes(
                data=draft.working_svg.encode("utf-8"),
                mime_type="image/svg+xml",
            )
        )
        return contents

    def _client(self) -> _GenerateContentClient:
        if self._generate_content_client is not None:
            return self._generate_content_client
        if self._cached_client is not None:
            return self._cached_client
        if not self.api_key:
            raise ValidationAppError("SVG vision repair is enabled without a Google API key.")
        self._cached_client = genai.Client(api_key=self.api_key).models
        return self._cached_client

    def _draft_from_error(self, error: ValidationAppError) -> SvgVisionRepairDraft | None:
        details = error.details
        source_svg = details.get("source_svg")
        working_svg = details.get("working_svg")
        widget_title = details.get("widget_title")
        template_relative_path = details.get("template_relative_path")
        request_message = details.get("request_message")
        content_lines = details.get("content_lines")
        violations = details.get("violations")

        if not isinstance(source_svg, str) or not isinstance(working_svg, str):
            return None
        if not isinstance(widget_title, str) or not isinstance(template_relative_path, str):
            return None
        if not isinstance(request_message, str) or not isinstance(content_lines, list):
            return None
        if not isinstance(violations, list):
            return None

        return SvgVisionRepairDraft(
            request_message=request_message,
            widget_title=widget_title,
            template_relative_path=template_relative_path,
            source_svg=source_svg,
            working_svg=working_svg,
            content_lines=[str(line) for line in content_lines],
            violations=[violation for violation in violations if isinstance(violation, dict)],
        )

    def _build_contents(self, draft: SvgVisionRepairDraft) -> list[types.Part | str]:
        violation_lines = []
        for violation in draft.violations[:12]:
            code = str(violation.get("code", "unknown"))
            message = str(violation.get("message", "unknown violation"))
            violation_lines.append(f"- {code}: {message}")
        preview = self.preview_renderer.render(draft.working_svg)

        prompt = "\n".join(
            [
                "You are repairing a cloned SVG template instance for strict structural safety.",
                f"User request: {draft.request_message}",
                f"Template path: {draft.template_relative_path}",
                f"Target widget title: {draft.widget_title}",
                "Hard invariants:",
                "- Never rename existing ids.",
                "- Never rename group <g> ids.",
                "- Never regroup, flatten, or reorder structural siblings.",
                "- Never change the source template viewBox.",
                "- Preserve defs, clip-path, mask, filter, and href/url(#...) references.",
                "Current validation violations:",
                *violation_lines,
                "Requested content lines:",
                *[f"- {line}" for line in draft.content_lines],
                "Return only the repaired raw <svg>...</svg> markup with no prose or "
                "markdown fences.",
                "You may adjust editable text content, text lengths, and inline styling, "
                "but you must preserve template identity.",
                "Source SVG follows after this instruction as reference. The current "
                "failing clone is attached as SVG bytes.",
                draft.source_svg,
            ]
        )

        contents: list[types.Part | str] = [prompt]
        if preview is not None:
            contents.append(types.Part.from_bytes(data=preview.data, mime_type=preview.mime_type))
            contents.append(
                types.Part.from_text(text=f"Rendered preview attached: {preview.description}")
            )
        contents.append(
            types.Part.from_bytes(
                data=draft.working_svg.encode("utf-8"),
                mime_type="image/svg+xml",
            )
        )
        return contents

    def _extract_svg_markup(self, response_text: str) -> str | None:
        match = SVG_FRAGMENT_PATTERN.search(response_text)
        if match is None:
            return None
        return match.group(1).strip()
