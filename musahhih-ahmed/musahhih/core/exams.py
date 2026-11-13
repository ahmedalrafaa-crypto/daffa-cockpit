"""الامتحانات والأسئلة والفروع (منطق فقط، بلا واجهة)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from .errors import AppError
from .roster import clean_name

ORDINALS = [
    "الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس", "السابع", "الثامن", "التاسع", "العاشر",
    "الحادي عشر", "الثاني عشر", "الثالث عشر", "الرابع عشر", "الخامس عشر",
    "السادس عشر", "السابع عشر", "الثامن عشر", "التاسع عشر", "العشرون",
]
PART_LETTERS = ["أ", "ب", "ج", "د", "هـ", "و", "ز", "ح", "ط", "ي", "ك", "ل"]
LATIN_LETTERS = list("ABCDEFGHIJKL")
LABEL_STYLES = {"ar": "أ  ب  ج", "en": "A  B  C"}
MAX_TARGET_PAGES = 20
MAX_QUESTIONS_PER_PAGE = 3
MAX_ANSWER_LINES = 25


def question_title(index: int) -> str:
    return f"السؤال {ORDINALS[index]}" if index < len(ORDINALS) else f"السؤال {index + 1}"


def part_letter(index: int, style: str = "ar") -> str:
    letters = LATIN_LETTERS if style == "en" else PART_LETTERS
    return letters[index] if index < len(letters) else str(index + 1)


def format_marks(value: float) -> str:
    """5.0 ← «5» و 2.5 ← «2.5»."""
    return f"{value:g}"


def marks_word(value: float) -> str:
    return "درجات" if 3 <= value <= 10 and value == int(value) else "درجة"


@dataclass(frozen=True)
class Part:
    id: int
    question_id: int
    text: str
    image: bytes | None
    max_marks: float
    answer_lines: int


@dataclass(frozen=True)
class Question:
    id: int
    intro: str
    parts: list[Part] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(p.max_marks for p in self.parts)


@dataclass(frozen=True)
class Exam:
    id: int
    name: str
    subject: str
    section_id: int
    section_name: str
    grade_name: str
    exam_date: str
    total_marks: float
    duration_minutes: int
    school_name: str
    status: str
    sheets_file: str | None
    answer_count: int = 0        # 0 = الإجابة عن كل الأسئلة؛ N = أجب عن N من الأسئلة فقط
    instructions: str = ""
    label_style: str = "ar"      # ترقيم الفروع: ar = أ ب ج ، en = A B C
    target_pages: int = 0        # 0 = حسب المحتوى؛ N = اضبط أسطر الإجابة ليتسع الامتحان في N صفحات
    questions_per_page: int = 0  # 0 = حسب المحتوى؛ N = كل صفحة فيها N أسئلة تملؤها (الأول ربعها)

    @property
    def approved(self) -> bool:
        return self.status == "approved"


@dataclass(frozen=True)
class ExamStudent:
    student_id: int
    full_name: str


@dataclass(frozen=True)
class LayoutBox:
    page: int
    kind: str
    question_id: int | None
    part_id: int | None
    x: float
    y: float
    w: float
    h: float


_EXAM_SELECT = """
    SELECT e.*, s.name AS section_name, g.name AS grade_name
    FROM exams e JOIN sections s ON s.id = e.section_id JOIN grades g ON g.id = s.grade_id
"""


def _exam(r: sqlite3.Row) -> Exam:
    return Exam(
        r["id"], r["name"], r["subject"], r["section_id"], r["section_name"], r["grade_name"], r["exam_date"],
        r["total_marks"], r["duration_minutes"], r["school_name"], r["status"], r["sheets_file"],
        r["answer_count"], r["instructions"], r["label_style"], r["target_pages"],
        r["page_per_question"],
    )


class ExamStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ---------- الامتحان ----------
    @staticmethod
    def _validate(name: str, subject: str, total_marks: float, answer_count: int = 0,
                  label_style: str = "ar", target_pages: int = 0) -> tuple[str, str]:
        if label_style not in LABEL_STYLES:
            raise AppError("نمط ترقيم الفروع غير معروف.")
        if not 0 <= target_pages <= MAX_TARGET_PAGES:
            raise AppError(f"عدد صفحات الورقة يجب أن يكون بين 0 و {MAX_TARGET_PAGES}.")
        if answer_count < 0:
            raise AppError("عدد الأسئلة المطلوب الإجابة عنها لا يمكن أن يكون سالباً.")
        name, subject = clean_name(name), clean_name(subject)
        if not name:
            raise AppError("يرجى كتابة اسم الامتحان.")
        if not subject:
            raise AppError("يرجى كتابة اسم المادة.")
        if total_marks <= 0:
            raise AppError("الدرجة الكلية يجب أن تكون أكبر من صفر.")
        return name, subject

    @staticmethod
    def _validate_per_page(questions_per_page: int) -> None:
        if not 0 <= questions_per_page <= MAX_QUESTIONS_PER_PAGE:
            raise AppError(f"عدد الأسئلة في الصفحة يجب أن يكون بين 0 و {MAX_QUESTIONS_PER_PAGE}.")

    def create_exam(self, name: str, subject: str, section_id: int, exam_date: str, total_marks: float,
                    duration_minutes: int = 0, school_name: str = "", question_count: int = 0,
                    answer_count: int = 0, instructions: str = "", label_style: str = "ar",
                    target_pages: int = 0, questions_per_page: int = 0) -> int:
        self._validate_per_page(questions_per_page)
        name, subject = self._validate(name, subject, total_marks, answer_count, label_style, target_pages)
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO exams (name, subject, section_id, exam_date, total_marks, duration_minutes, school_name,"
                " answer_count, instructions, label_style, target_pages, page_per_question)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, subject, section_id, exam_date, total_marks, duration_minutes, clean_name(school_name),
                 answer_count, instructions.strip(), label_style, target_pages, questions_per_page),
            )
            for position in range(question_count):
                self.conn.execute("INSERT INTO questions (exam_id, position) VALUES (?, ?)", (cur.lastrowid, position))
        return cur.lastrowid

    def update_exam(self, exam_id: int, name: str, subject: str, section_id: int, exam_date: str,
                    total_marks: float, duration_minutes: int, school_name: str,
                    answer_count: int = 0, instructions: str = "", label_style: str = "ar",
                    target_pages: int = 0, questions_per_page: int = 0) -> None:
        self._require_draft(exam_id)
        self._validate_per_page(questions_per_page)
        name, subject = self._validate(name, subject, total_marks, answer_count, label_style, target_pages)
        with self.conn:
            self.conn.execute(
                "UPDATE exams SET name=?, subject=?, section_id=?, exam_date=?, total_marks=?, duration_minutes=?,"
                " school_name=?, answer_count=?, instructions=?, label_style=?, target_pages=?, page_per_question=?"
                " WHERE id=?",
                (name, subject, section_id, exam_date, total_marks, duration_minutes, clean_name(school_name),
                 answer_count, instructions.strip(), label_style, target_pages, questions_per_page, exam_id),
            )

    def get_exam(self, exam_id: int) -> Exam:
        r = self.conn.execute(_EXAM_SELECT + " WHERE e.id = ?", (exam_id,)).fetchone()
        if r is None:
            raise AppError("الامتحان غير موجود.")
        return _exam(r)

    def list_exams(self) -> list[Exam]:
        return [_exam(r) for r in self.conn.execute(_EXAM_SELECT + " ORDER BY e.exam_date DESC, e.id DESC")]

    def delete_exam(self, exam_id: int) -> None:
        self._require_draft(exam_id, "لا يمكن حذف امتحان معتمد. ألغِ اعتماده أولاً.")
        with self.conn:
            self.conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))

    def _require_draft(self, exam_id: int, message: str = "الامتحان معتمد ولا يمكن تعديله. ألغِ اعتماده أولاً.") -> None:
        if self.get_exam(exam_id).approved:
            raise AppError(message)

    def _exam_of_question(self, question_id: int) -> int:
        r = self.conn.execute("SELECT exam_id FROM questions WHERE id = ?", (question_id,)).fetchone()
        if r is None:
            raise AppError("السؤال غير موجود.")
        return r[0]

    def _question_of_part(self, part_id: int) -> int:
        r = self.conn.execute("SELECT question_id FROM parts WHERE id = ?", (part_id,)).fetchone()
        if r is None:
            raise AppError("الفرع غير موجود.")
        return r[0]

    # ---------- الأسئلة ----------
    def questions(self, exam_id: int) -> list[Question]:
        parts: dict[int, list[Part]] = {}
        for r in self.conn.execute(
            "SELECT p.* FROM parts p JOIN questions q ON q.id = p.question_id WHERE q.exam_id = ?"
            " ORDER BY p.position, p.id", (exam_id,),
        ):
            parts.setdefault(r["question_id"], []).append(
                Part(r["id"], r["question_id"], r["text"], r["image"], r["max_marks"], r["answer_lines"])
            )
        return [
            Question(r["id"], r["intro"], parts.get(r["id"], []))
            for r in self.conn.execute("SELECT * FROM questions WHERE exam_id = ? ORDER BY position, id", (exam_id,))
        ]

    def marks_sum(self, exam_id: int) -> float:
        return sum(q.total for q in self.questions(exam_id))

    def counted_total(self, exam_id: int) -> float:
        """مجموع الدرجات المحتسب: كل الأسئلة، أو أعلى N أسئلة إن كان المطلوب الإجابة عن N فقط."""
        totals = sorted((q.total for q in self.questions(exam_id)), reverse=True)
        n = self.get_exam(exam_id).answer_count or len(totals)
        return sum(totals[:n])

    def add_question(self, exam_id: int, intro: str = "") -> int:
        self._require_draft(exam_id)
        with self.conn:
            position = self.conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM questions WHERE exam_id = ?", (exam_id,)
            ).fetchone()[0]
            cur = self.conn.execute(
                "INSERT INTO questions (exam_id, position, intro) VALUES (?, ?, ?)", (exam_id, position, intro.strip())
            )
        return cur.lastrowid

    def add_question_with_part(self, exam_id: int, text: str, max_marks: float, answer_lines: int = 5,
                               image: bytes | None = None) -> tuple[int, int]:
        """يضيف سؤالاً مع فرعه الأول معاً؛ إن رُفض الفرع (درجة غير صالحة مثلاً) لا يبقى سؤال فارغ."""
        self._require_draft(exam_id)
        self._validate_part(max_marks, answer_lines)
        question_id = self.add_question(exam_id)
        try:
            return question_id, self.add_part(question_id, text, max_marks, answer_lines, image)
        except Exception:
            self.delete_question(question_id)
            raise

    def update_question(self, question_id: int, intro: str) -> None:
        self._require_draft(self._exam_of_question(question_id))
        with self.conn:
            self.conn.execute("UPDATE questions SET intro = ? WHERE id = ?", (intro.strip(), question_id))

    def delete_question(self, question_id: int) -> None:
        self._require_draft(self._exam_of_question(question_id))
        with self.conn:
            self.conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))

    def move_question(self, question_id: int, step: int) -> None:
        exam_id = self._exam_of_question(question_id)
        self._require_draft(exam_id)
        ids = [q.id for q in self.questions(exam_id)]
        self._reorder("questions", ids, question_id, step)

    # ---------- الفروع ----------
    @staticmethod
    def _validate_part(max_marks: float, answer_lines: int) -> None:
        if max_marks <= 0:
            raise AppError("درجة الفرع يجب أن تكون أكبر من صفر.")
        if not 0 <= answer_lines <= MAX_ANSWER_LINES:
            raise AppError(f"عدد أسطر الإجابة يجب أن يكون بين 0 و {MAX_ANSWER_LINES}.")

    def add_part(self, question_id: int, text: str, max_marks: float, answer_lines: int = 5,
                 image: bytes | None = None) -> int:
        self._require_draft(self._exam_of_question(question_id))
        self._validate_part(max_marks, answer_lines)
        with self.conn:
            position = self.conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM parts WHERE question_id = ?", (question_id,)
            ).fetchone()[0]
            cur = self.conn.execute(
                "INSERT INTO parts (question_id, position, text, image, max_marks, answer_lines) VALUES (?,?,?,?,?,?)",
                (question_id, position, text.strip(), image, max_marks, answer_lines),
            )
        return cur.lastrowid

    def update_part(self, part_id: int, text: str, max_marks: float, answer_lines: int, image: bytes | None) -> None:
        self._require_draft(self._exam_of_question(self._question_of_part(part_id)))
        self._validate_part(max_marks, answer_lines)
        with self.conn:
            self.conn.execute(
                "UPDATE parts SET text = ?, max_marks = ?, answer_lines = ?, image = ? WHERE id = ?",
                (text.strip(), max_marks, answer_lines, image, part_id),
            )

    def delete_part(self, part_id: int) -> None:
        self._require_draft(self._exam_of_question(self._question_of_part(part_id)))
        with self.conn:
            self.conn.execute("DELETE FROM parts WHERE id = ?", (part_id,))

    def move_part(self, part_id: int, step: int) -> None:
        question_id = self._question_of_part(part_id)
        self._require_draft(self._exam_of_question(question_id))
        ids = [r[0] for r in self.conn.execute(
            "SELECT id FROM parts WHERE question_id = ? ORDER BY position, id", (question_id,))]
        self._reorder("parts", ids, part_id, step)

    def _reorder(self, table: str, ids: list[int], item_id: int, step: int) -> None:
        i = ids.index(item_id)
        j = i + step
        if not 0 <= j < len(ids):
            return
        ids[i], ids[j] = ids[j], ids[i]
        with self.conn:
            self.conn.executemany(
                f"UPDATE {table} SET position = ? WHERE id = ?", [(pos, x) for pos, x in enumerate(ids)]
            )

    # ---------- الاعتماد ----------
    def check_ready(self, exam_id: int) -> None:
        """يرفع AppError برسالة واضحة إن لم يكن الامتحان جاهزاً للاعتماد."""
        exam = self.get_exam(exam_id)
        questions = self.questions(exam_id)
        if not questions:
            raise AppError("أضف سؤالاً واحداً على الأقل.")
        for i, q in enumerate(questions):
            if not q.parts:
                raise AppError(
                    f"{question_title(i)} بلا فروع ولا درجة. حدّده واضغط «تعديل» لإدخال درجته، أو احذفه."
                )
        if exam.answer_count > len(questions):
            raise AppError(
                f"المطلوب الإجابة عن {exam.answer_count} أسئلة لكن عدد الأسئلة {len(questions)} فقط."
            )
        total = self.counted_total(exam_id)
        if abs(total - exam.total_marks) > 1e-9:
            what = (f"مجموع درجات أفضل {exam.answer_count} أسئلة" if exam.answer_count
                    else "مجموع درجات الفروع")
            raise AppError(
                f"{what} ({format_marks(total)}) لا يساوي الدرجة الكلية "
                f"({format_marks(exam.total_marks)}). عدّل الدرجات حتى يتطابقا."
            )

    def approve(self, exam_id: int, students: list[ExamStudent], boxes: list[LayoutBox], sheets_file: str) -> None:
        """يثبّت الامتحان: لقطة الطلاب + تخطيط الورقة + ملف الأوراق."""
        self._require_draft(exam_id, "الامتحان معتمد مسبقاً.")
        self.check_ready(exam_id)
        if not students:
            raise AppError("لا يوجد طلاب في شعبة هذا الامتحان. أضف الطلاب أولاً.")
        with self.conn:
            self.conn.executemany(
                "INSERT INTO exam_students (exam_id, student_id, full_name, position) VALUES (?, ?, ?, ?)",
                [(exam_id, s.student_id, s.full_name, i) for i, s in enumerate(students)],
            )
            self.conn.executemany(
                "INSERT INTO layout_boxes (exam_id, page, kind, question_id, part_id, x_mm, y_mm, w_mm, h_mm)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(exam_id, b.page, b.kind, b.question_id, b.part_id, b.x, b.y, b.w, b.h) for b in boxes],
            )
            self.conn.execute(
                "UPDATE exams SET status = 'approved', approved_at = datetime('now'), sheets_file = ? WHERE id = ?",
                (sheets_file, exam_id),
            )

    def unapprove(self, exam_id: int) -> None:
        """يعيد الامتحان مسودة. الأوراق المطبوعة سابقاً تصبح غير صالحة."""
        if self.conn.execute("SELECT COUNT(*) FROM scan_pages WHERE exam_id = ?", (exam_id,)).fetchone()[0]:
            raise AppError("لا يمكن إلغاء اعتماد امتحان استُوردت له أوراق ممسوحة.")
        with self.conn:
            self.conn.execute("DELETE FROM exam_students WHERE exam_id = ?", (exam_id,))
            self.conn.execute("DELETE FROM layout_boxes WHERE exam_id = ?", (exam_id,))
            self.conn.execute(
                "UPDATE exams SET status = 'draft', approved_at = NULL, sheets_file = NULL WHERE id = ?", (exam_id,)
            )

    def exam_students(self, exam_id: int) -> list[ExamStudent]:
        return [
            ExamStudent(r["student_id"], r["full_name"])
            for r in self.conn.execute(
                "SELECT student_id, full_name FROM exam_students WHERE exam_id = ? ORDER BY position", (exam_id,))
        ]

    def layout(self, exam_id: int) -> list[LayoutBox]:
        return [
            LayoutBox(r["page"], r["kind"], r["question_id"], r["part_id"], r["x_mm"], r["y_mm"], r["w_mm"], r["h_mm"])
            for r in self.conn.execute("SELECT * FROM layout_boxes WHERE exam_id = ? ORDER BY page, id", (exam_id,))
        ]

    def page_count(self, exam_id: int) -> int:
        """عدد صفحات ورقة الطالب الواحد في الامتحان المعتمد."""
        return self.conn.execute(
            "SELECT COALESCE(MAX(page), 0) FROM layout_boxes WHERE exam_id = ?", (exam_id,)
        ).fetchone()[0]
