from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from app.agent.config import ToolConfig
from app.agent.svg_template_validator import (
    SvgTemplateValidationResult,
    validate_svg_template_instance,
)
from app.agent.widget_validator import build_template_instance_widget_payload
from app.core.errors import ValidationAppError
from app.models.chat import WidgetPayload

PLACEHOLDER_PATTERN = re.compile(r"_{3,}")
COMPARE_PATTERN = re.compile(r"\b(?P<left>[^,.;]+?)\s+(?:vs\.?|versus)\s+(?P<right>[^,.;]+?)\b", re.IGNORECASE)
SPLIT_PATTERN = re.compile(r"[\n;|]+|(?:\.\s+)")
NON_WORD_PATTERN = re.compile(r"[^a-z0-9]+")
WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9&/+_-]*")
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "versus": ("vs", "versus", "compare", "comparison", "difference"),
    "pros-and-cons": ("pros and cons", "advantages", "disadvantages", "tradeoff", "trade-off"),
    "timeline": ("timeline", "roadmap", "chronology", "schedule", "milestone"),
    "journey": ("journey", "funnel", "experience", "customer journey", "path"),
    "sequence": ("sequence", "steps", "process", "workflow", "procedure"),
    "cycle": ("cycle", "loop", "iteration", "lifecycle"),
    "venn": ("venn", "overlap", "intersection"),
    "pyramid": ("pyramid", "hierarchy", "layers"),
    "mindmap": ("mind map", "mindmap", "brainstorm", "hub and spoke"),
    "list": ("list", "bullet", "checklist", "items"),
    "key-ideas": ("key ideas", "summary", "highlights", "takeaways"),
    "table": ("table", "matrix", "grid"),
    "relationship": ("relationship", "dependency", "mapping"),
}


@dataclass(frozen=True, slots=True)
class SvgTemplateRecord:
    category: str
    path: Path
    relative_path: str
    placeholder_count: int


@dataclass(frozen=True, slots=True)
class SvgLibraryRenderResult:
    widget: WidgetPayload
    template: SvgTemplateRecord
    validation: SvgTemplateValidationResult
    content_lines: list[str]


class SvgLibraryService:
    def __init__(self, library_root: Path) -> None:
        self.library_root = library_root
        self._template_cache: list[SvgTemplateRecord] | None = None

    def build_widget_for_request(
        self,
        *,
        request_message: str,
        tool_config: ToolConfig,
    ) -> SvgLibraryRenderResult:
        templates = self.list_templates()
        category = self._infer_category(request_message)
        candidates = [template for template in templates if template.category == category]
        if not candidates:
            raise ValidationAppError(
                f"No SVG templates are available for category '{category}'.",
                details={"validator": "svg_library_service", "category": category},
            )

        requested_lines = self._derive_content_lines(request_message)
        candidate = self._choose_candidate(candidates, target_line_count=len(requested_lines))
        source_svg = candidate.path.read_text(encoding="utf-8")
        working_svg = self._populate_template(source_svg, requested_lines)
        try:
            validation = validate_svg_template_instance(
                source_svg=source_svg,
                working_svg=working_svg,
            )
        except ValidationAppError as exc:
            exc.details.update(
                {
                    "validator": "svg_library_service",
                    "request_message": request_message,
                    "template_relative_path": candidate.relative_path,
                    "template_category": candidate.category,
                    "widget_title": self._build_widget_title(candidate),
                    "content_lines": requested_lines,
                    "source_svg": source_svg,
                    "working_svg": working_svg,
                }
            )
            raise
        widget = build_template_instance_widget_payload(
            title=self._build_widget_title(candidate),
            loading_messages=[
                f"Selecting a {candidate.category} template",
                "Cloning the source SVG",
                "Applying request content safely",
                "Validating structure before render",
            ],
            widget_code=working_svg,
            tool_config=tool_config,
        )
        return SvgLibraryRenderResult(
            widget=widget,
            template=candidate,
            validation=validation,
            content_lines=requested_lines,
        )

    def list_templates(self) -> list[SvgTemplateRecord]:
        if self._template_cache is not None:
            return self._template_cache

        if not self.library_root.exists():
            raise ValidationAppError(
                f"SVG library root does not exist: {self.library_root}",
                details={"validator": "svg_library_service", "library_root": str(self.library_root)},
            )

        templates: list[SvgTemplateRecord] = []
        for svg_path in sorted(self.library_root.glob("**/*.svg")):
            try:
                source_svg = svg_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise ValidationAppError(
                    f"Could not read SVG template '{svg_path.name}'.",
                    details={"validator": "svg_library_service", "template_path": str(svg_path)},
                ) from exc

            category = svg_path.parent.name
            placeholder_count = len(self._find_editable_nodes(source_svg))
            if placeholder_count == 0:
                continue
            templates.append(
                SvgTemplateRecord(
                    category=category,
                    path=svg_path,
                    relative_path=str(svg_path.relative_to(self.library_root)).replace("\\", "/"),
                    placeholder_count=placeholder_count,
                )
            )

        if not templates:
            raise ValidationAppError(
                "No editable SVG templates were found in the configured library.",
                details={"validator": "svg_library_service", "library_root": str(self.library_root)},
            )

        self._template_cache = templates
        return templates

    def _infer_category(self, request_message: str) -> str:
        lowered = request_message.lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                return category
        if COMPARE_PATTERN.search(request_message):
            return "versus"
        return "list"

    def _derive_content_lines(self, request_message: str) -> list[str]:
        compare_match = COMPARE_PATTERN.search(request_message)
        if compare_match is not None:
            left = self._clean_content_line(compare_match.group("left"))
            right = self._clean_content_line(compare_match.group("right"))
            return [line for line in [left, right, f"Compare {left}", f"Compare {right}"] if line]

        segments = [
            self._clean_content_line(segment)
            for segment in SPLIT_PATTERN.split(request_message)
            if self._clean_content_line(segment)
        ]
        if segments:
            return segments[:12]

        words = WORD_PATTERN.findall(request_message)
        if not words:
            return ["Requested SVG update"]

        lines: list[str] = []
        chunk_size = 4
        for index in range(0, len(words), chunk_size):
            chunk = " ".join(words[index : index + chunk_size]).strip()
            if chunk:
                lines.append(chunk)
            if len(lines) >= 12:
                break
        return lines or ["Requested SVG update"]

    def _choose_candidate(
        self,
        candidates: list[SvgTemplateRecord],
        *,
        target_line_count: int,
    ) -> SvgTemplateRecord:
        def score(template: SvgTemplateRecord) -> tuple[int, int, str]:
            deficit = max(0, target_line_count - template.placeholder_count)
            surplus = max(0, template.placeholder_count - target_line_count)
            return (deficit, surplus, template.relative_path)

        return min(candidates, key=score)

    def _populate_template(self, source_svg: str, content_lines: list[str]) -> str:
        try:
            root = ElementTree.fromstring(source_svg)
        except ElementTree.ParseError as exc:
            raise ValidationAppError(
                "Could not parse source SVG template before cloning.",
                details={"validator": "svg_library_service", "phase": "populate"},
            ) from exc

        editable_nodes = self._find_editable_nodes(source_svg, parsed_root=root)
        if not editable_nodes:
            raise ValidationAppError(
                "Selected SVG template does not expose editable placeholder text nodes.",
                details={"validator": "svg_library_service", "phase": "editable_slots"},
            )

        lines_to_apply = list(content_lines)
        for index, node in enumerate(editable_nodes):
            original_text = node.text or ""
            replacement = ""
            if index < len(lines_to_apply):
                replacement = self._fit_line_to_placeholder(lines_to_apply[index], original_text)
            node.text = replacement

        self._register_svg_namespaces(root)
        return ElementTree.tostring(root, encoding="unicode")

    def _find_editable_nodes(
        self,
        source_svg: str,
        *,
        parsed_root: ElementTree.Element | None = None,
    ) -> list[ElementTree.Element]:
        root = parsed_root
        if root is None:
            root = ElementTree.fromstring(source_svg)

        editable_nodes: list[ElementTree.Element] = []
        for element in root.iter():
            tag = self._local_name(element.tag)
            if tag not in {"text", "tspan"}:
                continue
            text_value = (element.text or "").strip()
            if PLACEHOLDER_PATTERN.search(text_value):
                editable_nodes.append(element)

        editable_nodes.sort(key=self._editable_node_sort_key)
        return editable_nodes

    def _editable_node_sort_key(self, element: ElementTree.Element) -> tuple[int, str]:
        element_id = (element.attrib.get("id") or "").lower()
        if "title" in element_id or re.fullmatch(r"text\d+.*", element_id):
            priority = 0
        elif "desc" in element_id or "body" in element_id:
            priority = 2
        else:
            priority = 1
        return (priority, element_id)

    def _fit_line_to_placeholder(self, line: str, placeholder: str) -> str:
        cleaned = self._clean_content_line(line)
        capacity = max(6, placeholder.count("_"))
        if len(cleaned) <= capacity:
            return cleaned
        if capacity <= 3:
            return cleaned[:capacity]
        return f"{cleaned[: capacity - 1].rstrip()}…"

    def _build_widget_title(self, template: SvgTemplateRecord) -> str:
        raw = f"{template.category}_{template.path.stem}"
        normalized = NON_WORD_PATTERN.sub("_", raw.lower()).strip("_")
        return normalized or "svg_template_widget"

    def _clean_content_line(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip(" .,-")

    def _local_name(self, tag: str) -> str:
        if "}" in tag:
            return tag.rsplit("}", 1)[1]
        return tag

    def _register_svg_namespaces(self, root: ElementTree.Element) -> None:
        if root.tag.startswith("{"):
            namespace_uri = root.tag.split("}", 1)[0][1:]
            if namespace_uri:
                ElementTree.register_namespace("", namespace_uri)

        for attribute_name in root.attrib:
            if not attribute_name.startswith("{"):
                continue
            namespace_uri, local_name = attribute_name[1:].split("}", 1)
            if local_name == "href":
                ElementTree.register_namespace("xlink", namespace_uri)
