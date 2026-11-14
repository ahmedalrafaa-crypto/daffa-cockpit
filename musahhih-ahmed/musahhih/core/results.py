"""سجل الدرجات: مجموع كل سؤال من فروعه والدرجة النهائية لكل طالب، محسوبة من الدرجات المحفوظة فقط."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from .exams import Exam, ExamStore, Question
from .grading import GRADED, GradingStore


@dataclass(frozen=True)
class StudentResult:
    student_id: int
    full_name: str
    absent: bool
    parts: dict[int, float | None]           # درجة كل فرع (None = لم يُصحح)
    questions: list[float | None]            # مجموع كل سؤال (None = فرع فيه لم يُصحح)
    counted: list[bool]                      # هل يدخل السؤال في الدرجة النهائية (أجب عن N من M)
    final: float | None                      # None إن كان غائباً أو التصحيح ناقصاً
    partial: float                           # مجموع ما صُحح حتى الآن

    @property
    def complete(self) -> bool:
        return self.final is not None


@dataclass(frozen=True)
class Register:
    exam: Exam
    questions: list[Question]
    results: list[StudentResult]

    @property
    def finals(self) -> list[float]:
        return [r.final for r in self.results if r.final is not None]

    def stats(self) -> dict:
        finals = self.finals
        half = self.exam.total_marks / 2
        return {
            "students": len(self.results),
            "absent": sum(r.absent for r in self.results),
            "incomplete": sum(not r.absent and not r.complete for r in self.results),
            "graded": len(finals),
            "average": sum(finals) / len(finals) if finals else None,
            "highest": max(finals) if finals else None,
            "lowest": min(finals) if finals else None,
            "passed": sum(f >= half for f in finals),
        }


def counted_questions(totals: list[float], answer_count: int) -> list[bool]:
    """أعلى N أسئلة تُحتسب (أجب عن N من M)؛ عند التساوي يُحتسب الأسبق ترتيباً."""
    n = answer_count or len(totals)
    order = sorted(range(len(totals)), key=lambda i: (-totals[i], i))
    chosen = set(order[:n])
    return [i in chosen for i in range(len(totals))]


def build(conn: sqlite3.Connection, exam_id: int) -> Register:
    store = ExamStore(conn)
    grading = GradingStore(conn)
    exam = store.get_exam(exam_id)
    questions = store.questions(exam_id)
    marks = grading.marks(exam_id)
    present = {s.student_id for s in grading.students(exam_id)}
    results = []
    for s in store.exam_students(exam_id):
        parts: dict[int, float | None] = {}
        totals: list[float | None] = []
        for q in questions:
            values = []
            for p in q.parts:
                m = marks.get((s.student_id, p.id))
                value = m.value if m and m.status == GRADED else None
                parts[p.id] = value
                values.append(value)
            totals.append(None if None in values else round(sum(values), 2))
        absent = s.student_id not in present
        partial = round(sum(v for v in parts.values() if v is not None), 2)
        if absent or None in totals:
            counted = [True] * len(totals) if absent or not exam.answer_count else \
                counted_questions([t or 0 for t in totals], exam.answer_count)
            final = None
        else:
            counted = counted_questions(totals, exam.answer_count)
            final = round(sum(t for t, c in zip(totals, counted) if c), 2)
        results.append(StudentResult(s.student_id, s.full_name, absent, parts, totals, counted, final, partial))
    return Register(exam, questions, results)


def academic_year(iso_date: str) -> str:
    """السنة الدراسية العراقية تبدأ في أيلول: 2026-11-15 ← «2026-2027»، و 2027-03-01 ← «2026-2027»."""
    try:
        d = date.fromisoformat(iso_date)
    except ValueError:
        return ""
    start = d.year if d.month >= 9 else d.year - 1
    return f"{start}-{start + 1}"
