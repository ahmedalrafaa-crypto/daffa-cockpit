"""علامات يرسمها المدرّس على إجابة الطالب (دائرة حول الخطأ أو خط تحته)، تُطبع لاحقاً في موضعها على الورقة.

الإحداثيات بالمليمتر من الزاوية العليا اليسرى للورقة، وهي نفسها على الصورة الممسوحة المقوَّمة وعلى الورقة الأصلية.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .errors import AppError
from ..sheet import geometry as g

CIRCLE, UNDERLINE = "circle", "underline"
MIN_SIZE_MM = 1.5      # ما هو أصغر من ذلك نقرة عابرة لا علامة


@dataclass(frozen=True)
class Annotation:
    id: int
    student_id: int
    page: int
    kind: str
    x1: float
    y1: float
    x2: float
    y2: float


def _row(r: sqlite3.Row) -> Annotation:
    return Annotation(r["id"], r["student_id"], r["page"], r["kind"], r["x1"], r["y1"], r["x2"], r["y2"])


class AnnotationStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, exam_id: int, student_id: int, page: int, kind: str,
            x1: float, y1: float, x2: float, y2: float) -> Annotation | None:
        """يحفظ العلامة؛ يعيد None لنقرة صغيرة جداً (لا تُعدّ علامة)."""
        if kind not in (CIRCLE, UNDERLINE):
            raise AppError("نوع العلامة غير معروف.")
        clamp = lambda v, hi: max(0.0, min(hi, v))  # noqa: E731
        x1, x2 = clamp(x1, g.PAGE_W), clamp(x2, g.PAGE_W)
        y1, y2 = clamp(y1, g.PAGE_H), clamp(y2, g.PAGE_H)
        if max(abs(x2 - x1), abs(y2 - y1)) < MIN_SIZE_MM:
            return None
        if kind == CIRCLE:   # الدائرة تُحفظ مستطيلاً محيطاً مرتّب الزوايا
            x1, x2 = sorted((x1, x2))
            y1, y2 = sorted((y1, y2))
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO annotations (exam_id, student_id, page, kind, x1, y1, x2, y2) VALUES (?,?,?,?,?,?,?,?)",
                (exam_id, student_id, page, kind, x1, y1, x2, y2))
        return _row(self.conn.execute("SELECT * FROM annotations WHERE id = ?", (cur.lastrowid,)).fetchone())

    def for_student(self, exam_id: int, student_id: int) -> list[Annotation]:
        return [_row(r) for r in self.conn.execute(
            "SELECT * FROM annotations WHERE exam_id = ? AND student_id = ? ORDER BY id", (exam_id, student_id))]

    def for_page(self, exam_id: int, student_id: int, page: int) -> list[Annotation]:
        return [a for a in self.for_student(exam_id, student_id) if a.page == page]

    def undo_last(self, exam_id: int, student_id: int, pages: set[int] | None = None) -> bool:
        """يحذف آخر علامة رسمها المدرّس لهذا الطالب (في الصفحات المعروضة إن حُدّدت)."""
        items = [a for a in self.for_student(exam_id, student_id) if pages is None or a.page in pages]
        if not items:
            return False
        with self.conn:
            self.conn.execute("DELETE FROM annotations WHERE id = ?", (items[-1].id,))
        return True

    def count(self, exam_id: int) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM annotations WHERE exam_id = ?", (exam_id,)).fetchone()[0]
