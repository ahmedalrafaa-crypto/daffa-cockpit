"""طبقة الطباعة فوق الأوراق الأصلية: نصوص في مواضع الخانات فقط، بلا أي خلفية."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from ..core.exams import LayoutBox, Question, format_marks
from . import geometry as g
from .render import _pen, open_pdf
from .text import CENTER, draw_text, font, rect


@dataclass(frozen=True)
class OverlayItem:
    box: LayoutBox
    text: str


def write_overlay(path: Path | str, pages: list[list[OverlayItem]], dx_mm: float = 0.0, dy_mm: float = 0.0,
                  guides: bool = False, title: str = "طبقة الدرجات") -> None:
    """يكتب صفحة PDF لكل قائمة عناصر. dx/dy إزاحة معايرة الطابعة (يمين/أسفل موجب).

    guides=True يرسم إطاراً رفيعاً داخل كل خانة وحول علامات الزوايا لاختبار المحاذاة.
    """
    writer, painter = open_pdf(path, title)
    try:
        ink = QColor(0, 0, 0)
        for index, items in enumerate(pages):
            if index:
                writer.newPage()
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
                draw_text(painter, item.text, font(size, True), x, y, b.w, b.h, CENTER,
                          Qt.AlignmentFlag.AlignVCenter, wrap=False)
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
