from __future__ import annotations

from dataclasses import dataclass
import re
from xml.etree import ElementTree

from pydantic import BaseModel, Field

from app.core.errors import ValidationAppError

URL_REFERENCE_PATTERN = re.compile(r"url\(\s*#([^)]+?)\s*\)")


class SvgTemplateViolation(BaseModel):
    code: str
    message: str
    element_id: str | None = None
    details: dict[str, object] = Field(default_factory=dict)


class SvgTemplateValidationResult(BaseModel):
    source_view_box: str | None = None
    working_view_box: str | None = None
    checked_ids: int = 0
    checked_group_ids: int = 0
    checked_reference_edges: int = 0
    checked_sibling_groups: int = 0
    violations: list[SvgTemplateViolation] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _ElementSnapshot:
    element_id: str
    tag: str
    path: tuple[int, ...]
    parent_key: str
    parent_id: str | None
    referenced_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SvgStructureMap:
    view_box: str | None
    nodes_by_id: dict[str, _ElementSnapshot]
    identified_child_order: dict[str, list[str]]
    duplicate_ids: list[str]
    root_tag: str


def validate_svg_template_instance(
    *,
    source_svg: str,
    working_svg: str,
) -> SvgTemplateValidationResult:
    source_map = _build_structure_map(source_svg, label="source")
    working_map = _build_structure_map(working_svg, label="working copy")
    violations: list[SvgTemplateViolation] = []

    if source_map.root_tag != "svg":
        violations.append(
            SvgTemplateViolation(
                code="source_root_not_svg",
                message="Source template root element must be <svg>.",
            )
        )
    if working_map.root_tag != "svg":
        violations.append(
            SvgTemplateViolation(
                code="working_root_not_svg",
                message="Working SVG root element must be <svg>.",
            )
        )

    violations.extend(_build_duplicate_id_violations(source_map.duplicate_ids, location="source"))
    violations.extend(_build_duplicate_id_violations(working_map.duplicate_ids, location="working"))

    if source_map.view_box != working_map.view_box:
        violations.append(
            SvgTemplateViolation(
                code="viewbox_drift",
                message="Working SVG must preserve the source template viewBox exactly.",
                details={
                    "source_view_box": source_map.view_box,
                    "working_view_box": working_map.view_box,
                },
            )
        )

    for element_id, source_node in source_map.nodes_by_id.items():
        working_node = working_map.nodes_by_id.get(element_id)
        if working_node is None:
            code = "group_id_missing" if source_node.tag == "g" else "id_missing"
            message = (
                f"Group id '{element_id}' from the source template is missing in the working SVG."
                if source_node.tag == "g"
                else f"Element id '{element_id}' from the source template is missing in the working SVG."
            )
            violations.append(
                SvgTemplateViolation(
                    code=code,
                    message=message,
                    element_id=element_id,
                )
            )
            continue

        if working_node.tag != source_node.tag:
            violations.append(
                SvgTemplateViolation(
                    code="tag_mutation",
                    message=(
                        f"Element '{element_id}' changed tag from <{source_node.tag}> "
                        f"to <{working_node.tag}>."
                    ),
                    element_id=element_id,
                    details={
                        "source_tag": source_node.tag,
                        "working_tag": working_node.tag,
                    },
                )
            )

        if working_node.parent_key != source_node.parent_key or working_node.parent_id != source_node.parent_id:
            violations.append(
                SvgTemplateViolation(
                    code="hierarchy_drift",
                    message=(
                        f"Element '{element_id}' changed parent or hierarchy position in the working SVG."
                    ),
                    element_id=element_id,
                    details={
                        "source_parent_id": source_node.parent_id,
                        "working_parent_id": working_node.parent_id,
                        "source_parent_key": source_node.parent_key,
                        "working_parent_key": working_node.parent_key,
                    },
                )
            )
        elif working_node.path != source_node.path:
            violations.append(
                SvgTemplateViolation(
                    code="sibling_order_drift",
                    message=(
                        f"Element '{element_id}' moved relative to its siblings in the working SVG."
                    ),
                    element_id=element_id,
                    details={
                        "source_path": list(source_node.path),
                        "working_path": list(working_node.path),
                    },
                )
            )

        if working_node.referenced_ids != source_node.referenced_ids:
            violations.append(
                SvgTemplateViolation(
                    code="reference_drift",
                    message=(
                        f"Element '{element_id}' changed structural id references in the working SVG."
                    ),
                    element_id=element_id,
                    details={
                        "source_references": list(source_node.referenced_ids),
                        "working_references": list(working_node.referenced_ids),
                    },
                )
            )

    for parent_key, source_children in source_map.identified_child_order.items():
        working_children = working_map.identified_child_order.get(parent_key)
        if working_children is None:
            violations.append(
                SvgTemplateViolation(
                    code="hierarchy_drift",
                    message=(
                        "A source parent that contained identified children no longer maps "
                        "to the same working SVG location."
                    ),
                    details={
                        "parent_key": parent_key,
                        "source_children": source_children,
                    },
                )
            )
            continue
        if working_children != source_children:
            violations.append(
                SvgTemplateViolation(
                    code="sibling_order_drift",
                    message="The order of identified siblings changed in the working SVG.",
                    details={
                        "parent_key": parent_key,
                        "source_children": source_children,
                        "working_children": working_children,
                    },
                )
            )

    result = SvgTemplateValidationResult(
        source_view_box=source_map.view_box,
        working_view_box=working_map.view_box,
        checked_ids=len(source_map.nodes_by_id),
        checked_group_ids=sum(1 for node in source_map.nodes_by_id.values() if node.tag == "g"),
        checked_reference_edges=sum(
            len(node.referenced_ids) for node in source_map.nodes_by_id.values()
        ),
        checked_sibling_groups=len(source_map.identified_child_order),
        violations=violations,
    )
    if violations:
        _raise_svg_template_validation_error(result)
    return result


def _raise_svg_template_validation_error(result: SvgTemplateValidationResult) -> None:
    top_messages = [violation.message for violation in result.violations[:5]]
    summary = "; ".join(top_messages)
    if len(result.violations) > 5:
        summary += f"; plus {len(result.violations) - 5} more violation(s)"
    raise ValidationAppError(
        f"SVG template instance validation failed: {summary}",
        details={
            "validator": "svg_template_validator",
            "checked_ids": result.checked_ids,
            "checked_group_ids": result.checked_group_ids,
            "checked_reference_edges": result.checked_reference_edges,
            "checked_sibling_groups": result.checked_sibling_groups,
            "violations": [violation.model_dump() for violation in result.violations],
        },
    )


def _build_structure_map(svg: str, *, label: str) -> _SvgStructureMap:
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError as exc:
        raise ValidationAppError(
            f"Could not parse {label} SVG.",
            details={"validator": "svg_template_validator", "phase": "parse"},
        ) from exc

    nodes_by_id: dict[str, _ElementSnapshot] = {}
    identified_child_order: dict[str, list[str]] = {}
    duplicate_ids: list[str] = []

    def walk(
        element: ElementTree.Element,
        *,
        path: tuple[int, ...],
        parent_key: str,
        parent_id: str | None,
    ) -> None:
        child_ids: list[str] = []
        children = list(element)
        for index, child in enumerate(children):
            child_path = (*path, index)
            element_id = (child.attrib.get("id") or "").strip() or None
            if element_id is not None:
                if element_id in nodes_by_id:
                    duplicate_ids.append(element_id)
                else:
                    nodes_by_id[element_id] = _ElementSnapshot(
                        element_id=element_id,
                        tag=_local_name(child.tag),
                        path=child_path,
                        parent_key=_path_key(path),
                        parent_id=parent_id,
                        referenced_ids=tuple(sorted(_extract_referenced_ids(child))),
                    )
                child_ids.append(element_id)

            walk(
                child,
                path=child_path,
                parent_key=_path_key(path),
                parent_id=element_id,
            )

        if child_ids:
            identified_child_order[_path_key(path)] = child_ids

    root_id = (root.attrib.get("id") or "").strip() or None
    walk(root, path=(), parent_key="root", parent_id=root_id)
    return _SvgStructureMap(
        view_box=root.attrib.get("viewBox"),
        nodes_by_id=nodes_by_id,
        identified_child_order=identified_child_order,
        duplicate_ids=duplicate_ids,
        root_tag=_local_name(root.tag),
    )


def _build_duplicate_id_violations(ids: list[str], *, location: str) -> list[SvgTemplateViolation]:
    violations: list[SvgTemplateViolation] = []
    for element_id in ids:
        violations.append(
            SvgTemplateViolation(
                code="duplicate_id",
                message=f"The {location} SVG contains duplicate id '{element_id}'.",
                element_id=element_id,
                details={"location": location},
            )
        )
    return violations


def _extract_referenced_ids(element: ElementTree.Element) -> set[str]:
    refs: set[str] = set()
    for attribute_name, raw_value in element.attrib.items():
        value = raw_value.strip()
        if not value:
            continue

        attribute_local_name = _local_name(attribute_name)
        if attribute_local_name == "href" and value.startswith("#"):
            refs.add(value[1:])

        for match in URL_REFERENCE_PATTERN.findall(value):
            cleaned = match.strip()
            if cleaned:
                refs.add(cleaned)

    return refs


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _path_key(path: tuple[int, ...]) -> str:
    if not path:
        return "root"
    return "/".join(str(segment) for segment in path)
