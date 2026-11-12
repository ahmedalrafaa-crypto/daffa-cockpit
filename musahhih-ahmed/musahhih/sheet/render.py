"""إنشاء أوراق الامتحان A4 (PDF) لكل طالب مع QR وعلامات الزوايا وخانات الدرجات.

التخطيط يُحسب مرة واحدة (لا يعتمد على الطالب) ثم تُرسم الصفحات لكل طالب.
تعيد render قائمة LayoutBox بمواضع مناطق الإجابة وخانات الدرجات بالمليمتر.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import qrcode
from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen

from ..core.errors import AppError
from ..core.exams import (
    Exam, ExamStudent, LayoutBox, Question, format_marks, marks_word, part_letter, question_title,
)
from ..core.qr_payload import SheetCode, encode
from . import geometry as g
from .text import CENTER, LEFT, LRI, PDI, RIGHT, draw_text, font, px, rect, text_height

BLACK = QColor(0, 0, 0)
GREY = QColor(120, 120, 120)
LIGHT = QColor(232, 232, 232)

IMAGE_MAX_W = 110.0
IMAGE_MAX_H = 70.0
IMAGE_DPI = 150.0  # الصورة لا تُكبَّر فوق حجمها الطبيعي عند هذه الدقة


@dataclass
class _Page:
    draw: list[Callable[[QPainter], None]] = field(default_factory=list)


def _pen(width_mm: float, color: QColor = BLACK, style=Qt.PenStyle.SolidLine) -> QPen:
    pen = QPen(color)
    pen.setWidthF(px(width_mm))
    pen.setStyle(style)
    return pen


def open_pdf(path: Path | str, title: str) -> tuple[QPdfWriter, QPainter]:
    """يفتح ملف PDF بمقاس A4 الحقيقي بلا هوامش، والرسم فيه بوحدة البكسل عند 600 نقطة/إنش."""
    writer = QPdfWriter(str(path))
    writer.setResolution(g.DPI)
    writer.setPageLayout(QPageLayout(
        QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0),
        QPageLayout.Unit.Millimeter,
    ))
    writer.setTitle(title)
    writer.setCreator("مصحّح أحمد")
    painter = QPainter()
    if not painter.begin(writer):
        raise AppError("تعذر إنشاء ملف PDF. قد يكون الملف مفتوحاً في برنامج آخر؛ أغلقه ثم أعد المحاولة.")
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    return writer, painter


def draw_mark_box(painter: QPainter, x: float, y: float, w: float, h: float) -> None:
    painter.setPen(_pen(0.35))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(rect(x, y, w, h))


def display_date(iso: str) -> str:
    """2026-11-15 ← 15/11/2026 معزولاً حتى لا يقلب النص العربي ترتيب أجزائه."""
    parts = iso.split("-")
    if len(parts) != 3:
        return iso
    return f"{LRI}{int(parts[2])}/{int(parts[1])}/{parts[0]}{PDI}"


IMAGE_MARKER = "{صورة}"   # يوضع في نص الفرع ليحدد مكان الصورة بين جزأيه


def _marks_suffix(marks: float) -> str:
    # علامة RLM تفصل عبارة الدرجة عن أي معادلة في آخر السطر
    return f" \u200f({format_marks(marks)} {marks_word(marks)})"


def _add_marks(text: str, marks: float) -> str:
    """تُلحق عبارة الدرجة بالسطر الأول (عنوان المجموعة مثل «أسئلة كلامية»)."""
    first, newline, rest = text.partition("\n")
    return (first + _marks_suffix(marks)).strip() + newline + rest


@dataclass
class _Block:
    before: str
    before_h: float
    after: str
    after_h: float
    image: QImage | None
    image_w: float
    image_h: float
    lines: int
    height: float


class SheetRenderer:
    def __init__(self, exam: Exam, questions: list[Question]):
        self.exam = exam
        self.questions = questions
        self.pages: list[_Page] = []
        self.boxes: list[LayoutBox] = []

    # ---------- التخطيط ----------
    def _layout(self, painter: QPainter) -> None:
        self.pages = [_Page()]
        self.boxes = [LayoutBox(1, "final_mark", None, None, *g.FINAL_BOX)]
        body = font(4.2)
        self.instructions_h = 0.0
        if self.exam.instructions.strip():
            self.instructions_h = text_height(painter, self.exam.instructions, font(3.6), g.CONTENT_R - g.GUTTER_X - 4) + 4
        self.first_top = g.FIRST_PAGE_TOP + (self.instructions_h + 3 if self.instructions_h else 0)
        self._y = self.first_top
        box_x = g.GUTTER_X + (g.GUTTER_W - g.MARK_BOX_W) / 2

        for qi, question in enumerate(self.questions):
            single = len(question.parts) == 1
            intro_h = text_height(painter, question.intro, body, g.CONTENT_W) + 2 if question.intro else 0
            blocks = [self._measure_part(painter, part, body, single) for part in question.parts]
            head_h = g.QUESTION_BAND_H + 2 + intro_h
            self._ensure(head_h + (blocks[0].height if blocks else 0))

            # شريط عنوان السؤال + خانة مجموع السؤال في عمود الدرجات
            y = self._y
            title = question_title(qi)
            total = f"({format_marks(question.total)} {marks_word(question.total)})"
            self._add(lambda p, y=y, title=title, total=total: self._draw_band(p, y, title, total))
            self._box("question_mark", question.id, None, box_x, y, g.MARK_BOX_W, g.QUESTION_BAND_H)
            self._y += g.QUESTION_BAND_H + 2
            if question.intro:
                y = self._y
                self._add(lambda p, y=y, t=question.intro, h=intro_h: draw_text(p, t, body, g.CONTENT_X, y, g.CONTENT_W, h))
                self._y += intro_h

            for pi, (part, b) in enumerate(zip(question.parts, blocks)):
                self._ensure(b.height)
                top = self._y
                label = "" if single else f"{part_letter(pi)})"
                self._add(lambda p, top=top, label=label, b=b: self._draw_part_text(p, top, label, b.before, b.before_h, body))
                if not single:
                    caption = f"من {format_marks(part.max_marks)}"
                    self._add(lambda p, top=top, caption=caption: self._draw_part_box(p, box_x, top, caption))
                    self._box("part_mark", question.id, part.id, box_x, top, g.MARK_BOX_W, g.MARK_BOX_H)
                y = top + b.before_h + 1
                if b.image is not None:
                    ix = g.CONTENT_X + (g.CONTENT_W - b.image_w) / 2
                    self._add(lambda p, ix=ix, y=y, b=b: p.drawImage(rect(ix, y, b.image_w, b.image_h), b.image))
                    y += b.image_h + 2
                if b.after:
                    width = g.CONTENT_W - (0 if single else 8)
                    self._add(lambda p, y=y, b=b, width=width: (p.setPen(BLACK),
                              draw_text(p, b.after, body, g.CONTENT_X, y, width, b.after_h + 2)))
                    y += b.after_h + 1
                if b.lines:
                    self._add(lambda p, y=y, lines=b.lines: self._draw_lines(p, y, lines))
                self._box("answer", question.id, part.id, g.CONTENT_X - 1, top, g.CONTENT_W + 2, b.height)
                self._y = top + b.height
            self._y += 3

    def _measure_part(self, painter: QPainter, part, body, single: bool) -> _Block:
        text = part.text if single else _add_marks(part.text, part.max_marks)
        image, image_w, image_h = None, 0.0, 0.0
        if part.image:
            image = QImage.fromData(part.image)
            if image.isNull():
                image = None
            else:
                scale = min(IMAGE_MAX_W / image.width(), IMAGE_MAX_H / image.height(), 25.4 / IMAGE_DPI)
                image_w, image_h = image.width() * scale, image.height() * scale
        if image is not None and IMAGE_MARKER in text:
            before, after = text.split(IMAGE_MARKER, 1)
        else:
            before, after = text.replace(IMAGE_MARKER, ""), ""
        before, after = before.strip(), after.strip()
        width = g.CONTENT_W - (0 if single else 8)
        before_h = text_height(painter, before, body, width) if before else 0.0
        if not single:
            before_h = max(before_h, g.MARK_BOX_H + 4.5)  # مكان الخانة وعبارة «من ..» تحتها
        after_h = text_height(painter, after, body, width) if after else 0.0
        fixed = before_h + 1 + (image_h + 2 if image is not None else 0) + (after_h + 1 if after else 0) + 2
        capacity = g.CONTENT_BOTTOM - g.NEXT_PAGE_TOP - g.QUESTION_BAND_H - 4
        lines = max(0, min(part.answer_lines, int((capacity - fixed) // g.LINE_STEP)))
        return _Block(before, before_h, after, after_h, image, image_w, image_h, lines, fixed + lines * g.LINE_STEP)

    def _ensure(self, height: float) -> None:
        if self._y + height > g.CONTENT_BOTTOM and self._y > g.NEXT_PAGE_TOP + 0.01:
            self.pages.append(_Page())
            self._y = g.NEXT_PAGE_TOP

    def _add(self, command: Callable[[QPainter], None]) -> None:
        self.pages[-1].draw.append(command)

    def _box(self, kind: str, question_id, part_id, x: float, y: float, w: float, h: float) -> None:
        self.boxes.append(LayoutBox(len(self.pages), kind, question_id, part_id, x, y, w, h))

    # ---------- رسم العناصر ----------
    @staticmethod
    def _draw_band(p: QPainter, y: float, title: str, total: str) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(LIGHT)
        p.drawRect(rect(g.CONTENT_X, y, g.CONTENT_W, g.QUESTION_BAND_H))
        p.setPen(BLACK)
        center = Qt.AlignmentFlag.AlignVCenter
        draw_text(p, title, font(4.6, True), g.CONTENT_X + 2, y, g.CONTENT_W - 4, g.QUESTION_BAND_H, RIGHT, center, False)
        draw_text(p, total, font(3.8), g.CONTENT_X + 2, y, g.CONTENT_W - 4, g.QUESTION_BAND_H, LEFT, center, False)
        draw_mark_box(p, g.GUTTER_X + (g.GUTTER_W - g.MARK_BOX_W) / 2, y, g.MARK_BOX_W, g.QUESTION_BAND_H)

    @staticmethod
    def _draw_part_text(p: QPainter, top: float, label: str, text: str, text_h: float, body) -> None:
        p.setPen(BLACK)
        width = g.CONTENT_W
        if label:
            draw_text(p, label, font(4.2, True), g.CONTENT_R - 8, top, 8, 8, RIGHT, wrap=False)
            width -= 8
        if text:
            draw_text(p, text, body, g.CONTENT_X, top, width, text_h + 2)

    @staticmethod
    def _draw_part_box(p: QPainter, x: float, top: float, caption: str) -> None:
        draw_mark_box(p, x, top, g.MARK_BOX_W, g.MARK_BOX_H)
        p.setPen(GREY)
        draw_text(p, caption, font(2.8), x, top + g.MARK_BOX_H + 0.3, g.MARK_BOX_W, 4, CENTER, wrap=False)

    @staticmethod
    def _draw_lines(p: QPainter, y: float, lines: int) -> None:
        p.setPen(_pen(0.2, GREY, Qt.PenStyle.DotLine))
        for i in range(1, lines + 1):
            yy = px(y + i * g.LINE_STEP - 1)
            p.drawLine(int(px(g.CONTENT_X)), int(yy), int(px(g.CONTENT_R)), int(yy))

    # ---------- رسم الصفحة لطالب ----------
    def _draw_frame(self, p: QPainter, student: ExamStudent, page: int) -> None:
        exam = self.exam
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BLACK)
        for x, y in g.corner_marks():
            p.drawRect(rect(x, y, g.CORNER_SIZE, g.CORNER_SIZE))

        code = SheetCode(exam.id, student.student_id, page)
        self._draw_qr(p, encode(code))

        p.setPen(BLACK)
        text_x, text_w = 68.0, g.CONTENT_R - 68.0
        if page == 1:
            x, y, w, h = g.FINAL_BOX
            draw_text(p, "الدرجة النهائية", font(3.2, True), x - 3, y - 5, w + 6, 5, CENTER, wrap=False)
            draw_mark_box(p, x, y, w, h)
            p.setPen(GREY)
            draw_text(p, f"من {format_marks(exam.total_marks)}", font(2.8), x, y + h + 0.3, w, 4, CENTER, wrap=False)
            p.setPen(BLACK)
            if exam.school_name:
                draw_text(p, exam.school_name, font(5.2, True), text_x, 15, text_w, 8, CENTER, wrap=False)
            draw_text(p, f"{exam.name} — {exam.subject}", font(4.6, True), text_x, 23, text_w, 7, CENTER, wrap=False)
            info = [f"الصف: {exam.grade_name} / شعبة {exam.section_name}", f"التاريخ: {display_date(exam.exam_date)}"]
            if exam.duration_minutes:
                info.append(f"المدة: {exam.duration_minutes} دقيقة")
            draw_text(p, "     ".join(info), font(3.7), text_x, 31, text_w, 6, CENTER, wrap=False)
            draw_text(p, f"اسم الطالب: {student.full_name}", font(4.4, True), text_x, 39, text_w, 7, RIGHT, wrap=False)
            p.setPen(_pen(0.4))
            p.drawLine(int(px(g.GUTTER_X)), int(px(48)), int(px(g.CONTENT_R)), int(px(48)))
            if self.instructions_h:
                p.setPen(_pen(0.25, GREY))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(rect(g.GUTTER_X, 50, g.CONTENT_R - g.GUTTER_X, self.instructions_h))
                p.setPen(BLACK)
                draw_text(p, exam.instructions, font(3.6), g.GUTTER_X + 2, 52, g.CONTENT_R - g.GUTTER_X - 4,
                          self.instructions_h)
            top = self.first_top
        else:
            draw_text(p, f"{exam.name} — {exam.subject}", font(4.0, True), text_x, 18, text_w, 6, RIGHT, wrap=False)
            draw_text(p, f"اسم الطالب: {student.full_name}", font(4.0), text_x, 26, text_w, 6, RIGHT, wrap=False)
            top = g.NEXT_PAGE_TOP

        # الخط الفاصل بين عمود الدرجات ومنطقة الإجابة
        p.setPen(_pen(0.25, GREY))
        sep = int(px(g.GUTTER_X + g.GUTTER_W + 2))
        p.drawLine(sep, int(px(top)), sep, int(px(g.CONTENT_BOTTOM)))

        p.setPen(BLACK)
        small = font(3.0)
        draw_text(p, f"صفحة {page} من {len(self.pages)}", small, 60, g.FOOTER_Y, 90, 5, CENTER, wrap=False)
        draw_text(p, code.human(), small, g.GUTTER_X, g.FOOTER_Y, 50, 5, LEFT, wrap=False)

    @staticmethod
    def _draw_qr(p: QPainter, payload: str) -> None:
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
        qr.add_data(payload)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        n = len(matrix)
        # حدود صحيحة بالبكسل لكل وحدة حتى لا تظهر فواصل بيضاء بين المربعات
        edges = [round(px(g.QR_SIZE) * i / n) for i in range(n + 1)]
        x0, y0 = round(px(g.QR_X)), round(px(g.QR_Y))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BLACK)
        for r, row in enumerate(matrix):
            for c, dark in enumerate(row):
                if dark:
                    p.drawRect(QRectF(x0 + edges[c], y0 + edges[r], edges[c + 1] - edges[c], edges[r + 1] - edges[r]))

    # ---------- الواجهة العامة ----------
    def render(self, path: Path | str, students: list[ExamStudent],
               progress: Callable[[int, int], None] | None = None) -> list[LayoutBox]:
        writer, painter = open_pdf(path, f"{self.exam.name} — {self.exam.subject}")
        try:
            self._layout(painter)
            first = True
            for index, student in enumerate(students):
                for number, page in enumerate(self.pages, start=1):
                    if not first:
                        writer.newPage()
                    first = False
                    self._draw_frame(painter, student, number)
                    for command in page.draw:
                        command(painter)
                if progress:
                    progress(index + 1, len(students))
        finally:
            painter.end()
        return list(self.boxes)
