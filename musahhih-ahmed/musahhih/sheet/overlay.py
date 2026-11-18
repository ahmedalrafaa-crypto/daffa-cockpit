"""طبقة الطباعة فوق الأوراق الأصلية: نصوص في مواضع الخانات فقط، بلا أي خلفية."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from ..core.exams import LayoutBox, Question, format_marks
from . import geometry as g
from .render import _pen, open_pdf
from .text import CENTER, draw_text, fitted_font, font, rect
from .ticks import (
    ANSWER_SIZE, GUTTER, GUTTER_SIZE, OVER_ANSWER, answer_center, draw_annotation, draw_tick, gutter_center,
)


@dataclass(frozen=True)
class OverlayItem:
    box: LayoutBox
    text: str


def write_overlay(path: Path | str, pages: list[list[OverlayItem]], dx_mm: float = 0.0, dy_mm: float = 0.0,
                  guides: bool = False, title: str = "طبقة الدرجات", color: str = "#000000",
                  offsets: list[tuple[float, float]] | None = None,
                  ticks: list[list[tuple]] | None = None, tick_position: str = "off",
                  annotations: list[list] | None = None) -> None:
    """يكتب صفحة PDF لكل قائمة عناصر. dx/dy إزاحة معايرة الطابعة (يمين/أسفل موجب).

    offsets: إزاحة خاصة لكل صفحة (مثلاً للوجه الخلفي في الطباعة على الوجهين)؛ إن غابت تُستعمل dx/dy للجميع.
    ticks: علامات التصحيح لكل صفحة [(خانة الدرجة، مساحة الإجابة، النوع)] تُرسم في tick_position.
    guides=True يرسم إطاراً رفيعاً داخل كل خانة وحول علامات الزوايا لاختبار المحاذاة.
    """
    writer, painter = open_pdf(path, title)
    try:
        ink = QColor(color)
        for index, items in enumerate(pages):
            if index:
                writer.newPage()
            if offsets is not None:
                dx_mm, dy_mm = offsets[index]
            if guides:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(_pen(0.2, ink))
                for x, y in g.corner_marks():
                    painter.drawRect(rect(x - 1 + dx_mm, y - 1 + dy_mm, g.CORNER_SIZE + 2, g.CORNER_SIZE + 2))
            for item in items:
                b = item.box
                x, y = b.x + dx_mm, b.y + dy_mm
                if guides:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(_pen(0.2, ink))
                    painter.drawRect(rect(x + 1.2, y + 1.2, b.w - 2.4, b.h - 2.4))
                painter.setPen(ink)
                size = min(5.5, b.h * 0.62)
                # يُصغَّر الخط عند الحاجة حتى يتسع النص (الدرجة كتابةً أطول من الرقم)
                draw_text(painter, item.text, fitted_font(painter, item.text, size, b.w - 1, True, min_mm=2.2),
                          x, y, b.w, b.h, CENTER, Qt.AlignmentFlag.AlignVCenter, wrap=False)
            if ticks and tick_position in (GUTTER, OVER_ANSWER):
                for box, answer, kind in ticks[index]:
                    cx, cy = gutter_center(box) if tick_position == GUTTER else answer_center(answer)
                    size = GUTTER_SIZE if tick_position == GUTTER else ANSWER_SIZE
                    draw_tick(painter, kind, cx + dx_mm, cy + dy_mm, size, color, g.PX_PER_MM)
            for a in (annotations[index] if annotations else ()):
                draw_annotation(painter, a, color, g.PX_PER_MM, dx_mm, dy_mm)
    finally:
        painter.end()


def alignment_test_pages(boxes: list[LayoutBox], questions: list[Question], total_marks: float) -> list[list[OverlayItem]]:
    """صفحات اختبار المحاذاة: الدرجة القصوى في كل خانة كنص تجريبي."""
    part_max = {p.id: p.max_marks for q in questions for p in q.parts}
    question_max = {q.id: q.total for q in questions}
    count = max((b.page for b in boxes), default=0)
    pages: list[list[OverlayItem]] = [[] for _ in range(count)]
    for b in boxes:
        if b.kind == "part_mark":
            value = part_max.get(b.part_id)
        elif b.kind == "question_mark":
            value = question_max.get(b.question_id)
        elif b.kind == "final_mark":
            value = total_marks
        else:
            continue
        if value is not None:
            pages[b.page - 1].append(OverlayItem(b, format_marks(value)))
    return pages
