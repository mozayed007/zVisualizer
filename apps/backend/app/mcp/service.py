"""Visualizer MCP service layer: agent generation + validation + artifact writing.

Plain async methods, no MCP imports; `app.mcp.server` exposes these as tools.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.agent.config import ToolConfig
from app.agent.widget_validator import (
    build_validated_template_widget_payload,
    build_widget_payload,
)
from app.core.errors import ValidationAppError
from app.core.settings import Settings, get_settings
from app.mcp.artifacts import default_artifact_root, widget_output_dir, write_manifest
from app.mcp.models import (
    AgentSummaryModel,
    CapabilitiesModel,
    ManifestModel,
    RenderedFileModel,
    RenderResultModel,
    SvgTemplateDetailModel,
    SvgTemplateModel,
    ValidationReportModel,
    VisualizeResultModel,
)
from app.mcp.render.pipeline import FormatName, RenderOutcome, render_widget_outcome
from app.mcp.render.png import available_renderers
from app.mcp.render.theme import ThemeMode
from app.mcp.turn import ProgressCallback, run_visual_turn
from app.models.chat import ChatRequest, WidgetPayload
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

DEFAULT_RENDER_LOADING_MESSAGES = ["Rendering the visual"]
DEFAULT_TITLE = "hand_authored_visual"
DEFAULT_FORMATS_SVG: tuple[FormatName, ...] = ("svg", "png")
DEFAULT_FORMATS_HTML: tuple[FormatName, ...] = ("html", "png")
_VALID_FORMATS: tuple[FormatName, ...] = ("svg", "png", "html")


class ServiceToolError(RuntimeError):
    """Tool-visible failure with a clean, actionable message."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _normalize_formats(formats: Sequence[str] | None, *, kind: str) -> tuple[FormatName, ...]:
    if not formats:
        return DEFAULT_FORMATS_SVG if kind == "svg" else DEFAULT_FORMATS_HTML
    normalized: list[FormatName] = []
    for raw in formats:
        lowered = str(raw).strip().lower()
        if lowered not in _VALID_FORMATS:
            raise ServiceToolError(f"Unknown format '{raw}'. Supported formats: svg, png, html.")
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized)


def _file_models(outcome: RenderOutcome, theme: ThemeMode) -> list[RenderedFileModel]:
    return [
        RenderedFileModel(
            format=artifact.format,
            path=str(artifact.path.resolve()),
            bytes=artifact.bytes,
            width=artifact.width,
            height=artifact.height,
            theme=theme,
            renderer=artifact.renderer,
        )
        for artifact in outcome.files
    ]


class VisualizerMcpService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        chat_service: ChatService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.chat_service = chat_service or ChatService(settings=self.settings)

    # -- helpers -----------------------------------------------------------

    def _tool_config(self, agent_id: str | None) -> ToolConfig:
        return self.chat_service.agent_registry.get(agent_id).config.agent.tool

    def _validate_widget_code(
        self,
        *,
        widget_code: str,
        title: str,
        template_id: str | None,
        agent_id: str | None,
    ) -> WidgetPayload:
        tool_config = self._tool_config(agent_id)
        if template_id is not None and template_id.strip():
            resolved = template_id.strip()
            template = self.chat_service.svg_library_service.resolve_template(resolved)
            source_svg = self.chat_service.svg_library_service.read_source_svg(template)
            return build_validated_template_widget_payload(
                title=title,
                loading_messages=list(DEFAULT_RENDER_LOADING_MESSAGES),
                widget_code=widget_code,
                template_id=template.relative_path,
                source_svg=source_svg,
                tool_config=tool_config,
            )
        return build_widget_payload(
            title=title,
            loading_messages=list(DEFAULT_RENDER_LOADING_MESSAGES),
            widget_code=widget_code,
            tool_config=tool_config,
        )

    @staticmethod
    def _output_directory(*, output_dir: str | None, conversation_id: str | None, title: str) -> Path:
        if output_dir is not None and output_dir.strip():
            return Path(output_dir.strip()).expanduser()
        return widget_output_dir(
            root=default_artifact_root(),
            conversation_id=conversation_id,
            title=title,
        )

    @staticmethod
    def _write_manifest(
        *,
        directory: Path,
        widget: WidgetPayload,
        theme: ThemeMode,
        scale: float,
        files: list[RenderedFileModel],
        warnings: list[str],
        source: str,
        conversation_id: str | None = None,
        agent_id: str | None = None,
        model: str | None = None,
        prompt: str | None = None,
        template_id: str | None = None,
    ) -> str:
        manifest = ManifestModel(
            title=widget.title,
            kind=widget.kind,
            source=source,
            theme=theme,
            scale=scale,
            created_at=datetime.now(UTC).isoformat(),
            conversation_id=conversation_id,
            agent_id=agent_id,
            model=model,
            prompt=prompt,
            template_id=template_id,
            files=files,
            warnings=warnings,
        )
        path = write_manifest(directory=directory, payload=manifest.model_dump(mode="json"))
        return str(path.resolve())

    # -- tool implementations ---------------------------------------------

    async def capabilities(self) -> CapabilitiesModel:
        catalog = self.chat_service.agent_registry.list_summaries()
        renderers = available_renderers()
        notes: list[str] = []
        if "playwright" not in renderers:
            notes.append(
                "PNG rendering uses external SVG rasterizers only. Install Playwright for the "
                "preferred renderer and for PNG screenshots of interactive HTML widgets."
            )
        return CapabilitiesModel(
            agents=[
                AgentSummaryModel(
                    id=agent.id,
                    name=agent.name,
                    display_name=agent.display_name,
                    default_model=agent.default_model,
                    description=agent.description,
                )
                for agent in catalog.agents
            ],
            default_agent_id=catalog.default_agent_id,
            renderers=renderers,
            artifact_root=str(default_artifact_root()),
            google_api_key_configured=self.settings.google_api_key is not None,
            notes=notes,
        )

    def list_svg_templates(self, *, query: str | None = None, limit: int = 100) -> list[SvgTemplateModel]:
        try:
            templates = self.chat_service.svg_library_service.list_templates()
        except ValidationAppError as exc:
            raise ServiceToolError(f"SVG template library unavailable: {exc.message}") from exc
        normalized_query = (query or "").strip().casefold()
        rows: list[SvgTemplateModel] = []
        for template in templates:
            if (
                normalized_query
                and normalized_query not in template.relative_path.casefold()
                and (normalized_query not in template.category.casefold())
            ):
                continue
            rows.append(
                SvgTemplateModel(
                    id=template.relative_path,
                    category=template.category,
                    placeholder_count=template.placeholder_count,
                )
            )
        return rows[: max(1, limit)]

    def get_svg_template(self, *, template_id: str) -> SvgTemplateDetailModel:
        try:
            template = self.chat_service.svg_library_service.resolve_template(template_id)
            source_svg = self.chat_service.svg_library_service.read_source_svg(template)
        except ValidationAppError as exc:
            raise ServiceToolError(f"Unknown SVG template '{template_id}': {exc.message}") from exc
        return SvgTemplateDetailModel(
            id=template.relative_path,
            category=template.category,
            placeholder_count=template.placeholder_count,
            svg_source=source_svg,
        )

    def validate_visual(
        self,
        *,
        widget_code: str,
        title: str | None = None,
        template_id: str | None = None,
        agent_id: str | None = None,
    ) -> ValidationReportModel:
        normalized_title = (title or DEFAULT_TITLE).strip() or DEFAULT_TITLE
        try:
            payload = self._validate_widget_code(
                widget_code=widget_code,
                title=normalized_title,
                template_id=template_id,
                agent_id=agent_id,
            )
        except ValidationAppError as exc:
            violations: list[str] = []
            raw_violations = exc.details.get("violations")
            if isinstance(raw_violations, list):
                violations = [str(item) for item in raw_violations]
            return ValidationReportModel(
                valid=False,
                title=normalized_title,
                kind=None,
                errors=[exc.message],
                violations=violations,
            )
        except ValueError as exc:
            raise ServiceToolError(str(exc)) from exc
        return ValidationReportModel(
            valid=True,
            title=payload.title,
            kind=payload.kind,
            errors=[],
            violations=[],
        )

    def render_visual(
        self,
        *,
        widget_code: str,
        title: str | None = None,
        template_id: str | None = None,
        agent_id: str | None = None,
        theme: ThemeMode = "light",
        formats: Sequence[str] | None = None,
        scale: float = 2.0,
        output_dir: str | None = None,
        settle_ms: int = 400,
    ) -> RenderResultModel:
        normalized_title = (title or DEFAULT_TITLE).strip() or DEFAULT_TITLE
        try:
            payload = self._validate_widget_code(
                widget_code=widget_code,
                title=normalized_title,
                template_id=template_id,
                agent_id=agent_id,
            )
        except ValidationAppError as exc:
            raise ServiceToolError(f"Widget validation failed: {exc.message}") from exc
        except ValueError as exc:
            raise ServiceToolError(str(exc)) from exc

        requested = _normalize_formats(formats, kind=payload.kind)
        directory = self._output_directory(
            output_dir=output_dir,
            conversation_id=None,
            title=payload.title,
        )
        outcome = render_widget_outcome(
            widget=payload,
            theme=theme,
            formats=requested,
            scale=scale,
            output_dir=directory,
            basename=payload.title,
            settle_ms=settle_ms,
        )
        file_models = _file_models(outcome, theme)
        manifest_path = self._write_manifest(
            directory=directory,
            widget=payload,
            theme=theme,
            scale=scale,
            files=file_models,
            warnings=outcome.warnings,
            source="mcp:render_visual",
            template_id=template_id,
        )
        return RenderResultModel(
            title=payload.title,
            kind=payload.kind,
            files=file_models,
            warnings=outcome.warnings,
            manifest_path=manifest_path,
            template_id=template_id,
        )

    async def visualize(
        self,
        *,
        prompt: str,
        agent_id: str = "visualizer",
        model: str | None = None,
        subject: str | None = None,
        conversation_id: str | None = None,
        theme: ThemeMode = "light",
        formats: Sequence[str] | None = None,
        scale: float = 2.0,
        output_dir: str | None = None,
        include_code: bool = True,
        timeout_s: float = 240.0,
        settle_ms: int = 400,
        on_progress: ProgressCallback | None = None,
    ) -> tuple[VisualizeResultModel, bytes | None]:
        request = ChatRequest(
            message=prompt,
            conversation_id=conversation_id or None,
            subject=subject,
            agent_id=agent_id or None,
            model=model,
        )
        client_id = f"mcp:{agent_id or 'default'}"

        try:
            async with asyncio.timeout(timeout_s):
                turn = await run_visual_turn(
                    self.chat_service,
                    request,
                    client_id=client_id,
                    on_progress=on_progress,
                )
        except TimeoutError as exc:
            raise ServiceToolError(
                f"Visual generation exceeded the {timeout_s:.0f}s budget. Retry with a shorter prompt "
                "or raise timeout_s."
            ) from exc

        if turn.error is not None:
            raise ServiceToolError(f"{turn.error.title}: {turn.error.detail}".strip())

        if turn.status != "ok" or turn.widget_code is None or turn.title is None or turn.kind is None:
            return (
                VisualizeResultModel(
                    status="no_visual",
                    conversation_id=turn.conversation_id,
                    assistant_text=turn.assistant_text,
                    follow_up_chips=turn.follow_up_chips,
                    warnings=turn.warnings,
                ),
                None,
            )

        payload = WidgetPayload(
            title=turn.title,
            loading_messages=turn.loading_messages or list(DEFAULT_RENDER_LOADING_MESSAGES),
            widget_code=turn.widget_code,
            kind=turn.kind,
        )
        requested = _normalize_formats(formats, kind=payload.kind)
        directory = self._output_directory(
            output_dir=output_dir,
            conversation_id=turn.conversation_id,
            title=payload.title,
        )
        outcome = await asyncio.to_thread(
            render_widget_outcome,
            widget=payload,
            theme=theme,
            formats=requested,
            scale=scale,
            output_dir=directory,
            basename=payload.title,
            settle_ms=settle_ms,
        )
        file_models = _file_models(outcome, theme)
        manifest_path = self._write_manifest(
            directory=directory,
            widget=payload,
            theme=theme,
            scale=scale,
            files=file_models,
            warnings=[*turn.warnings, *outcome.warnings],
            source="mcp:visualize",
            conversation_id=turn.conversation_id,
            agent_id=agent_id or None,
            model=model,
            prompt=prompt,
        )

        result = VisualizeResultModel(
            status="ok",
            conversation_id=turn.conversation_id,
            title=payload.title,
            kind=payload.kind,
            assistant_text=turn.assistant_text,
            follow_up_chips=turn.follow_up_chips,
            widget_code=payload.widget_code if include_code else None,
            files=file_models,
            warnings=[*turn.warnings, *outcome.warnings],
            manifest_path=manifest_path,
        )
        return result, outcome.png_bytes
