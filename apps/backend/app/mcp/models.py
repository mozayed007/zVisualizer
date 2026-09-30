"""Contract models for MCP tool results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FormatName = Literal["svg", "png", "html"]


class RenderedFileModel(BaseModel):
    format: FormatName
    path: str
    bytes: int
    width: int | None = None
    height: int | None = None
    theme: Literal["light", "dark"] | None = None
    renderer: str | None = None


class VisualizeResultModel(BaseModel):
    status: Literal["ok", "no_visual"]
    conversation_id: str | None = None
    title: str | None = None
    kind: Literal["svg", "html"] | None = None
    assistant_text: str = ""
    follow_up_chips: list[str] = Field(default_factory=list)
    widget_code: str | None = None
    files: list[RenderedFileModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    manifest_path: str | None = None


class RenderResultModel(BaseModel):
    title: str
    kind: Literal["svg", "html"]
    files: list[RenderedFileModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    manifest_path: str | None = None
    template_id: str | None = None


class ValidationReportModel(BaseModel):
    valid: bool
    title: str
    kind: str | None = None
    errors: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)


class AgentSummaryModel(BaseModel):
    id: str
    name: str
    display_name: str
    default_model: str
    description: str | None = None


class CapabilitiesModel(BaseModel):
    server: str = "visualizer-agent"
    agents: list[AgentSummaryModel] = Field(default_factory=list)
    default_agent_id: str
    renderers: list[str] = Field(default_factory=list)
    artifact_root: str
    google_api_key_configured: bool
    notes: list[str] = Field(default_factory=list)


class SvgTemplateModel(BaseModel):
    id: str
    category: str
    placeholder_count: int


class SvgTemplateDetailModel(SvgTemplateModel):
    svg_source: str


class ManifestModel(BaseModel):
    title: str
    kind: Literal["svg", "html"]
    source: str
    theme: Literal["light", "dark"]
    scale: float
    created_at: str
    conversation_id: str | None = None
    agent_id: str | None = None
    model: str | None = None
    prompt: str | None = None
    template_id: str | None = None
    files: list[RenderedFileModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
