"""التصحيح اليدوي سؤالاً بسؤال: حفظ الدرجات فوراً، التخطي، التقدم، وقائمة غير المصحح.

البرنامج لا يقرر أي درجة؛ يحفظ ما يدخله المدرّس فقط بعد التحقق من حدوده.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .errors import AppError
from .exams import ExamStore, ExamStudent, Question, format_marks, question_title
from .scans import ScanStore

GRADED, SKIPPED = "graded", "skipped"


@dataclass(frozen=True)
class Mark:
    value: float | None
    status: str


@dataclass(frozen=True)
class Pending:
    question_index: int
    student: ExamStudent
    skipped: bool


class GradingStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.exams = ExamStore(conn)
        self.scans = ScanStore(conn)

    # ---------- الجاهزية والطلاب ----------
    def check_ready(self, exam_id: int) -> None:
        exam = self.exams.get_exam(exam_id)
        if not exam.approved:
            raise AppError("الامتحان غير معتمد.")
        if not self.scans.is_confirmed(exam_id):
            raise AppError("أكّد اكتمال استيراد الأوراق أولاً من صفحة «استيراد الأوراق».")

    def students(self, exam_id: int) -> list[ExamStudent]:
        """الطلاب الذين لهم ورقة واحدة على الأقل، بترتيب قائمة الامتحان."""
        present = {r.student_id for r in self.scans.student_report(exam_id) if r.present}
        return [s for s in self.exams.exam_students(exam_id) if s.student_id in present]

    def absent(self, exam_id: int) -> list[ExamStudent]:
        present = {s.student_id for s in self.students(exam_id)}
        return [s for s in self.exams.exam_students(exam_id) if s.student_id not in present]

    # ---------- الدرجات ----------
    def marks(self, exam_id: int) -> dict[tuple[int, int], Mark]:
        return {
            (r["student_id"], r["part_id"]): Mark(r["value"], r["status"])
            for r in self.conn.execute("SELECT * FROM marks WHERE exam_id = ?", (exam_id,))
        }

    def student_marks(self, exam_id: int, student_id: int) -> dict[int, Mark]:
        return {
            r["part_id"]: Mark(r["value"], r["status"])
            for r in self.conn.execute("SELECT * FROM marks WHERE exam_id = ? AND student_id = ?",
                                       (exam_id, student_id))
        }

    def _parts(self, exam_id: int) -> dict[int, float]:
        return {p.id: p.max_marks for q in self.exams.questions(exam_id) for p in q.parts}

    def save(self, exam_id: int, student_id: int, values: dict[int, float]) -> None:
        """يحفظ درجات فروع سؤال لطالب في عملية واحدة (كلها أو لا شيء)."""
        limits = self._parts(exam_id)
        if student_id not in {s.student_id for s in self.students(exam_id)}:
            raise AppError("هذا الطالب ليس له ورقة في هذا الامتحان.")
        for part_id, value in values.items():
            if part_id not in limits:
                raise AppError("الفرع ليس من هذا الامتحان.")
            if value is None or value < 0:
                raise AppError("الدرجة لا يمكن أن تكون سالبة أو فارغة.")
            if value > limits[part_id] + 1e-9:
                raise AppError(f"الدرجة {format_marks(value)} أكبر من الدرجة القصوى {format_marks(limits[part_id])}.")
        with self.conn:
            self.conn.executemany(
                "INSERT INTO marks (exam_id, student_id, part_id, value, status) VALUES (?, ?, ?, ?, 'graded')"
                " ON CONFLICT (exam_id, student_id, part_id) DO UPDATE SET value = excluded.value,"
                " status = 'graded', updated_at = datetime('now')",
                [(exam_id, student_id, part_id, round(float(v), 2)) for part_id, v in values.items()],
            )

    def skip(self, exam_id: int, student_id: int, part_ids: list[int]) -> None:
        """يعلّم الفروع غير المصححة «متخطّاة» للعودة إليها؛ الدرجة المحفوظة لا تُمسح."""
        with self.conn:
            self.conn.executemany(
                "INSERT INTO marks (exam_id, student_id, part_id, value, status) VALUES (?, ?, ?, NULL, 'skipped')"
                " ON CONFLICT (exam_id, student_id, part_id) DO NOTHING",
                [(exam_id, student_id, p) for p in part_ids],
            )

    # ---------- التقدم ----------
    @staticmethod
    def _done(marks: dict, student_id: int, question: Question) -> bool:
        return all((m := marks.get((student_id, p.id))) is not None and m.status == GRADED for p in question.parts)

    def question_progress(self, exam_id: int, question: Question) -> tuple[int, int]:
        """(عدد الطلاب المصحح سؤالهم، عدد الطلاب الحاضرين)."""
        students = self.students(exam_id)
        marks = self.marks(exam_id)
        return sum(self._done(marks, s.student_id, question) for s in students), len(students)

    def overall_progress(self, exam_id: int) -> tuple[int, int]:
        """(عدد درجات الفروع المدخلة، العدد الكلي المطلوب)."""
        students = self.students(exam_id)
        parts = self._parts(exam_id)
        marks = self.marks(exam_id)
        done = sum(1 for s in students for p in parts if (m := marks.get((s.student_id, p))) and m.status == GRADED)
        return done, len(students) * len(parts)

    def pending(self, exam_id: int) -> list[Pending]:
        """قائمة مراجعة الإجابات غير المصححة (ومنها المتخطّاة)، سؤالاً سؤالاً."""
        students = self.students(exam_id)
        marks = self.marks(exam_id)
        out = []
        for qi, q in enumerate(self.exams.questions(exam_id)):
            for s in students:
                if not self._done(marks, s.student_id, q):
                    skipped = any((m := marks.get((s.student_id, p.id))) and m.status == SKIPPED for p in q.parts)
                    out.append(Pending(qi, s, skipped))
        return out

    def next_pending(self, exam_id: int, question: Question, after: int) -> int | None:
        """أول طالب بعد الموضع after لم يُصحح سؤاله (يلتف إلى البداية)، أو None إن اكتمل."""
        students = self.students(exam_id)
        marks = self.marks(exam_id)
        n = len(students)
        for step in range(1, n + 1):
            i = (after + step) % n
            if not self._done(marks, students[i].student_id, question):
                return i
        return None

    @staticmethod
    def describe(question_index: int) -> str:
        return question_title(question_index)
