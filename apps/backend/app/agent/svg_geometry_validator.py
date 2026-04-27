"""Geometric violation detector for raw visualizer-agent SVG widgets.

This module inspects widget SVGs produced by the visualizer agent (not the
svg_skill template flow) and reports geometric failures that the previous
regex-only checks in :mod:`app.agent.widget_validator` could not catch:

    V-VIZ-TEXT-OVERFLOW-H       text estimated bbox exits its container rect horizontally
    V-VIZ-TEXT-OVERFLOW-V       text estimated bbox exits its container rect vertically
    V-VIZ-SIBLING-OVERLAP       two node-level rects intersect each other
    V-VIZ-VIEWBOX-ESCAPE        any rect or text bbox exits the root viewBox
    V-VIZ-TEXT-WORDCOUNT        text class exceeds its per-role word/char budget
    V-VIZ-BOX-WIDTH-FORMULA     node rect width is smaller than the docs-mandated
                                `chars x font_size x weight x 1.08 + 24` budget

The character-width model mirrors ``docs/visualizer_skill/svg-generation.md``
and ``docs/svg_skill/text-fitting-and-alignment.md``. All dimensions are
estimated — the goal is to flag authoring mistakes, not to pixel-measure the
final rendered output.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Literal
from xml.etree import ElementTree

Severity = Literal["HIGH", "MEDIUM"]

# Font metrics derived from the host-injected SVG stylesheet. Keep these in sync
# with ``docs/visualizer_skill/svg-generation.md``.
#   th -> 14px weight 500 (title / node label, primary color)
#   t  -> 14px weight 400 (body label)
#   ts -> 12px weight 400 (subtitle / annotation)
_TEXT_CLASS_METRICS: dict[str, tuple[float, float]] = {
    "th": (14.0, 0.58),
    "t": (14.0, 0.52),
    "ts": (12.0, 0.50),
}

# Width safety margin for kerning/rounding (matches the 8% margin in the docs).
_WIDTH_SAFETY = 1.08

# Line-height factor used by the docs (``line_height = font_size * 1.35``).
_LINE_HEIGHT_FACTOR = 1.35

# Slot internal padding (docs: ``max(title_chars x 8, subtitle_chars x 7) + 24``).
_SLOT_PADDING = 24.0

# Word / character budgets per text role.
_TEXT_BUDGET: dict[str, tuple[int, int, int]] = {
    # class -> (max_words, max_chars_per_line, max_lines)
    "th": (7, 40, 2),
    "t": (10, 60, 3),
    "ts": (12, 80, 3),
}

# Pixel tolerance for overflow/overlap detection. Small jitter is ignored so
# templates that sit exactly on the edge do not flap.
_EDGE_TOLERANCE = 4.0
_OVERLAP_TOLERANCE = 2.0

# A group is treated as a "node" (i.e. a colored box with a label) when its
# class list contains ``node`` or any of the visualizer color-ramp classes.
_NODE_CLASS_HINTS = frozenset(
    {
        "node",
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
)

_VIEWBOX_PATTERN = re.compile(r"\s*([\-\d.]+)\s+([\-\d.]+)\s+([\-\d.]+)\s+([\-\d.]+)\s*")
_TRANSLATE_PATTERN = re.compile(
    r"translate\(\s*([\-\d.]+)\s*(?:[,\s]\s*([\-\d.]+))?\s*\)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class GeometryViolation:
    code: str
    severity: Severity
    message: str
    element_hint: str | None = None

    def formatted(self) -> str:
        if self.element_hint:
            return f"[{self.code}] {self.message} (element: {self.element_hint})"
        return f"[{self.code}] {self.message}"


@dataclass(frozen=True, slots=True)
class _Bbox:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def contains_point(self, px: float, py: float) -> bool:
        return self.x <= px <= self.right and self.y <= py <= self.bottom

    def intersects(self, other: _Bbox, tolerance: float) -> bool:
        return not (
            self.right - tolerance <= other.x
            or other.right - tolerance <= self.x
            or self.bottom - tolerance <= other.y
            or other.bottom - tolerance <= self.y
        )


@dataclass(slots=True)
class _RectInfo:
    bbox: _Bbox
    is_node: bool
    hint: str


@dataclass(slots=True)
class _TextInfo:
    anchor_x: float
    y: float
    bbox: _Bbox
    line_count: int
    longest_line_chars: int
    word_count: int
    text_class: str
    hint: str
    lines: list[str] = field(default_factory=list)


def validate_svg_geometry(widget_code: str) -> list[GeometryViolation]:
    """Return the list of geometric violations for ``widget_code``.

    The caller is expected to have already run the regex-based checks in
    :mod:`app.agent.widget_validator`. On parse failure this function returns
    an empty list so the existing structural errors remain the source of
    truth.
    """

    try:
        root = ElementTree.fromstring(widget_code)
    except ElementTree.ParseError:
        return []

    viewbox = _parse_viewbox(root.attrib.get("viewBox"))

    rects: list[_RectInfo] = []
    texts: list[_TextInfo] = []
    _walk(
        root,
        tx=0.0,
        ty=0.0,
        parent_class_tokens=frozenset(),
        rects=rects,
        texts=texts,
    )

    violations: list[GeometryViolation] = []
    violations.extend(_check_viewbox_escape(rects, texts, viewbox))
    violations.extend(_check_text_overflow(rects, texts))
    violations.extend(_check_sibling_overlap(rects))
    violations.extend(_check_text_budgets(texts))
    violations.extend(_check_box_width_formula(rects, texts))
    return violations


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _parse_float(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    stripped = value.strip()
    if not stripped:
        return default
    # Drop optional trailing unit (e.g. "12px", "1.5em" for dy).
    match = re.match(r"^(-?\d+(?:\.\d+)?)", stripped)
    if match is None:
        return default
    try:
        return float(match.group(1))
    except ValueError:
        return default


def _parse_viewbox(raw: str | None) -> _Bbox | None:
    if not raw:
        return None
    match = _VIEWBOX_PATTERN.fullmatch(raw)
    if match is None:
        return None
    x, y, w, h = (float(match.group(i)) for i in range(1, 5))
    return _Bbox(x=x, y=y, width=w, height=h)


def _parse_translate(transform: str | None) -> tuple[float, float]:
    if not transform:
        return 0.0, 0.0
    match = _TRANSLATE_PATTERN.search(transform)
    if match is None:
        return 0.0, 0.0
    tx = _parse_float(match.group(1))
    ty = _parse_float(match.group(2))
    return tx, ty


def _class_tokens(element: ElementTree.Element) -> frozenset[str]:
    raw = element.attrib.get("class")
    if not raw:
        return frozenset()
    return frozenset(token for token in raw.split() if token)


def _hint_for(element: ElementTree.Element, local: str) -> str:
    element_id = element.attrib.get("id")
    if element_id:
        return f"<{local} id='{element_id}'>"
    classes = element.attrib.get("class")
    if classes:
        return f"<{local} class='{classes}'>"
    return f"<{local}>"


def _text_content_for_text_element(element: ElementTree.Element) -> list[str]:
    """Collect the text content of a ``<text>`` element as a list of lines.

    Each child ``<tspan>`` is treated as its own line. Whitespace inside a
    line is collapsed. Empty lines are dropped.
    """

    tspans = [child for child in element if _local_name(child.tag) == "tspan"]
    lines: list[str] = []
    if tspans:
        leading = (element.text or "").strip()
        if leading:
            lines.append(_collapse_ws(leading))
        for tspan in tspans:
            body = "".join(tspan.itertext())
            collapsed = _collapse_ws(body)
            if collapsed:
                lines.append(collapsed)
        return lines

    body = "".join(element.itertext())
    collapsed = _collapse_ws(body)
    if collapsed:
        lines.append(collapsed)
    return lines


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


# ---------------------------------------------------------------------------
# Tree walk
# ---------------------------------------------------------------------------


def _walk(
    element: ElementTree.Element,
    *,
    tx: float,
    ty: float,
    parent_class_tokens: frozenset[str],
    rects: list[_RectInfo],
    texts: list[_TextInfo],
) -> None:
    local = _local_name(element.tag)

    local_tx, local_ty = _parse_translate(element.attrib.get("transform"))
    absolute_tx = tx + local_tx
    absolute_ty = ty + local_ty
    own_classes = _class_tokens(element)

    if local == "rect":
        x = _parse_float(element.attrib.get("x")) + absolute_tx
        y = _parse_float(element.attrib.get("y")) + absolute_ty
        width = _parse_float(element.attrib.get("width"))
        height = _parse_float(element.attrib.get("height"))
        if width > 0 and height > 0:
            combined_classes = parent_class_tokens | own_classes
            is_node = bool(combined_classes & _NODE_CLASS_HINTS)
            rects.append(
                _RectInfo(
                    bbox=_Bbox(x=x, y=y, width=width, height=height),
                    is_node=is_node,
                    hint=_hint_for(element, local),
                )
            )

    if local == "text":
        text_info = _build_text_info(
            element=element,
            absolute_tx=absolute_tx,
            absolute_ty=absolute_ty,
        )
        if text_info is not None:
            texts.append(text_info)
        # Do not descend further: tspans are already consumed.
        return

    # Propagate group class tokens so a <rect> inside ``<g class='c-blue'>``
    # is still classified as a node even when the rect itself has no class.
    if local == "g":
        forwarded_classes = parent_class_tokens | own_classes
    else:
        forwarded_classes = parent_class_tokens

    for child in element:
        _walk(
            child,
            tx=absolute_tx,
            ty=absolute_ty,
            parent_class_tokens=forwarded_classes,
            rects=rects,
            texts=texts,
        )


def _build_text_info(
    *,
    element: ElementTree.Element,
    absolute_tx: float,
    absolute_ty: float,
) -> _TextInfo | None:
    classes = _class_tokens(element)
    text_class = next((token for token in ("th", "t", "ts") if token in classes), None)
    if text_class is None:
        return None  # unknown class — already rejected elsewhere

    font_size, weight_factor = _TEXT_CLASS_METRICS[text_class]

    lines = _text_content_for_text_element(element)
    if not lines:
        return None

    longest_line_chars = max(len(line) for line in lines)
    word_count = sum(len(line.split()) for line in lines)

    x = _parse_float(element.attrib.get("x")) + absolute_tx
    y = _parse_float(element.attrib.get("y")) + absolute_ty

    width = longest_line_chars * font_size * weight_factor * _WIDTH_SAFETY
    line_height = font_size * _LINE_HEIGHT_FACTOR
    height = max(font_size, line_height * len(lines))

    anchor = (element.attrib.get("text-anchor") or "start").strip().lower()
    if anchor == "middle":
        left = x - width / 2
    elif anchor == "end":
        left = x - width
    else:
        left = x

    baseline_mode = (element.attrib.get("dominant-baseline") or "").strip().lower()
    if baseline_mode in {"central", "middle"}:
        top = y - font_size / 2
        # Additional lines extend downward from the first line.
        if len(lines) > 1:
            height = font_size + line_height * (len(lines) - 1)
    else:
        top = y - font_size  # treat y as baseline of the first line

    bbox = _Bbox(x=left, y=top, width=max(width, 1.0), height=max(height, 1.0))

    return _TextInfo(
        anchor_x=x,
        y=y,
        bbox=bbox,
        line_count=len(lines),
        longest_line_chars=longest_line_chars,
        word_count=word_count,
        text_class=text_class,
        hint=_hint_for(element, "text"),
        lines=lines,
    )


# ---------------------------------------------------------------------------
# Violation checks
# ---------------------------------------------------------------------------


def _nearest_container(rects: list[_RectInfo], text: _TextInfo) -> _RectInfo | None:
    candidates = [
        rect
        for rect in rects
        if rect.bbox.contains_point(text.anchor_x, text.y)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda rect: rect.bbox.area())
    return candidates[0]


def _check_text_overflow(
    rects: list[_RectInfo],
    texts: list[_TextInfo],
) -> list[GeometryViolation]:
    violations: list[GeometryViolation] = []
    for text in texts:
        container = _nearest_container(rects, text)
        if container is None:
            continue
        box = container.bbox
        text_bbox = text.bbox
        if (
            text_bbox.right > box.right - _EDGE_TOLERANCE
            or text_bbox.x < box.x + _EDGE_TOLERANCE
        ):
            violations.append(
                GeometryViolation(
                    code="V-VIZ-TEXT-OVERFLOW-H",
                    severity="HIGH",
                    message=(
                        "Text exceeds its container horizontally. "
                        f"Text bbox spans x={text_bbox.x:.0f}..{text_bbox.right:.0f} "
                        f"but container is x={box.x:.0f}..{box.right:.0f}. "
                        "Shorten the copy, wrap with <tspan>, or widen the rect "
                        "(rect.width >= longest_line_chars * font_size * weight * 1.08 + 24)."
                    ),
                    element_hint=text.hint,
                )
            )
        if (
            text_bbox.bottom > box.bottom - _EDGE_TOLERANCE
            or text_bbox.y < box.y + _EDGE_TOLERANCE
        ):
            violations.append(
                GeometryViolation(
                    code="V-VIZ-TEXT-OVERFLOW-V",
                    severity="HIGH",
                    message=(
                        "Text exceeds its container vertically. "
                        f"Text bbox spans y={text_bbox.y:.0f}..{text_bbox.bottom:.0f} "
                        f"but container is y={box.y:.0f}..{box.bottom:.0f}. "
                        "Reduce line count, use a taller rect, or split the note into "
                        "a dedicated annotation placed in clear space."
                    ),
                    element_hint=text.hint,
                )
            )
    return violations


def _check_sibling_overlap(rects: list[_RectInfo]) -> list[GeometryViolation]:
    node_rects = [rect for rect in rects if rect.is_node]
    violations: list[GeometryViolation] = []
    seen_pairs: set[tuple[int, int]] = set()
    for i, rect_a in enumerate(node_rects):
        for j, rect_b in enumerate(node_rects[i + 1 :], start=i + 1):
            if (i, j) in seen_pairs:
                continue
            if rect_a.bbox.intersects(rect_b.bbox, _OVERLAP_TOLERANCE):
                seen_pairs.add((i, j))
                violations.append(
                    GeometryViolation(
                        code="V-VIZ-SIBLING-OVERLAP",
                        severity="HIGH",
                        message=(
                            "Two node rectangles overlap. "
                            f"Rect A spans x={rect_a.bbox.x:.0f}..{rect_a.bbox.right:.0f}, "
                            f"y={rect_a.bbox.y:.0f}..{rect_a.bbox.bottom:.0f}; "
                            f"Rect B spans x={rect_b.bbox.x:.0f}..{rect_b.bbox.right:.0f}, "
                            f"y={rect_b.bbox.y:.0f}..{rect_b.bbox.bottom:.0f}. "
                            "Move callouts into clear space or shrink the sibling node."
                        ),
                        element_hint=f"{rect_a.hint} ↔ {rect_b.hint}",
                    )
                )
    return violations


def _check_viewbox_escape(
    rects: list[_RectInfo],
    texts: list[_TextInfo],
    viewbox: _Bbox | None,
) -> list[GeometryViolation]:
    if viewbox is None:
        return []

    violations: list[GeometryViolation] = []

    def _escapes(bbox: _Bbox) -> bool:
        return (
            bbox.x < viewbox.x - _EDGE_TOLERANCE
            or bbox.y < viewbox.y - _EDGE_TOLERANCE
            or bbox.right > viewbox.right + _EDGE_TOLERANCE
            or bbox.bottom > viewbox.bottom + _EDGE_TOLERANCE
        )

    for rect in rects:
        if _escapes(rect.bbox):
            violations.append(
                GeometryViolation(
                    code="V-VIZ-VIEWBOX-ESCAPE",
                    severity="HIGH",
                    message=(
                        "Rect extends outside the root viewBox. "
                        f"Rect spans x={rect.bbox.x:.0f}..{rect.bbox.right:.0f}, "
                        f"y={rect.bbox.y:.0f}..{rect.bbox.bottom:.0f}; "
                        f"viewBox is x={viewbox.x:.0f}..{viewbox.right:.0f}, "
                        f"y={viewbox.y:.0f}..{viewbox.bottom:.0f}. "
                        "Keep rects inside the 0..680 x 0..H safe area."
                    ),
                    element_hint=rect.hint,
                )
            )

    for text in texts:
        if _escapes(text.bbox):
            violations.append(
                GeometryViolation(
                    code="V-VIZ-VIEWBOX-ESCAPE",
                    severity="HIGH",
                    message=(
                        "Text extends outside the root viewBox. "
                        f"Text bbox spans x={text.bbox.x:.0f}..{text.bbox.right:.0f}, "
                        f"y={text.bbox.y:.0f}..{text.bbox.bottom:.0f}. "
                        "Shorten the copy or move the text into the safe area."
                    ),
                    element_hint=text.hint,
                )
            )
    return violations


def _check_text_budgets(texts: list[_TextInfo]) -> list[GeometryViolation]:
    violations: list[GeometryViolation] = []
    for text in texts:
        budget = _TEXT_BUDGET.get(text.text_class)
        if budget is None:
            continue
        max_words, max_chars_per_line, max_lines = budget
        if text.word_count > max_words:
            violations.append(
                GeometryViolation(
                    code="V-VIZ-TEXT-WORDCOUNT",
                    severity="HIGH",
                    message=(
                        f"Text class '{text.text_class}' allows at most {max_words} words "
                        f"but this element has {text.word_count}. Shorten the copy or "
                        "split the concept into its own node."
                    ),
                    element_hint=text.hint,
                )
            )
        if text.longest_line_chars > max_chars_per_line:
            violations.append(
                GeometryViolation(
                    code="V-VIZ-TEXT-WORDCOUNT",
                    severity="HIGH",
                    message=(
                        f"Text class '{text.text_class}' allows at most "
                        f"{max_chars_per_line} characters per line but the longest "
                        f"line is {text.longest_line_chars} characters. Wrap with "
                        "<tspan> or shorten the copy."
                    ),
                    element_hint=text.hint,
                )
            )
        if text.line_count > max_lines:
            violations.append(
                GeometryViolation(
                    code="V-VIZ-TEXT-WORDCOUNT",
                    severity="HIGH",
                    message=(
                        f"Text class '{text.text_class}' allows at most {max_lines} "
                        f"lines but this element has {text.line_count}. Remove lines or "
                        "split the copy across multiple annotations."
                    ),
                    element_hint=text.hint,
                )
            )
    return violations


def _check_box_width_formula(
    rects: list[_RectInfo],
    texts: list[_TextInfo],
) -> list[GeometryViolation]:
    violations: list[GeometryViolation] = []
    for text in texts:
        container = _nearest_container(rects, text)
        if container is None or not container.is_node:
            continue
        font_size, weight_factor = _TEXT_CLASS_METRICS[text.text_class]
        required_width = math.ceil(
            text.longest_line_chars * font_size * weight_factor * _WIDTH_SAFETY
            + _SLOT_PADDING
        )
        if container.bbox.width + _EDGE_TOLERANCE < required_width:
            violations.append(
                GeometryViolation(
                    code="V-VIZ-BOX-WIDTH-FORMULA",
                    severity="HIGH",
                    message=(
                        "Node rect width is smaller than the docs-mandated budget. "
                        f"Rect width is {container.bbox.width:.0f}px but the '"
                        f"{text.text_class}' label needs at least {required_width}px "
                        "(longest_line_chars x font_size x weight x 1.08 + 24). "
                        "Widen the rect or shorten the label."
                    ),
                    element_hint=f"{container.hint} ↔ {text.hint}",
                )
            )
    return violations
