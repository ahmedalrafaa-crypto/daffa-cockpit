"""طباعة الدرجات فوق أوراق الإجابة الأصلية: بناء الصفحات وترتيبها، إعدادات الطابعة، وسجل الطباعة."""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

from .errors import AppError
from .exams import ExamStore, LayoutBox, format_marks
from .grading import GradingStore
from .results import build
from .scans import MATCHED, ScanStore
from .settings import Settings

ORDER_SCAN, ORDER_STUDENT = "scan", "student"
COLORS = {"red": "#c00000", "black": "#000000", "blue": "#1f3fbf"}

# مفاتيح الإعدادات (الوجه الأمامي يستعمل المفتاحين القديمين نفسيهما)
FRONT_X, FRONT_Y = "print_offset_x_mm", "print_offset_y_mm"
BACK_X, BACK_Y = "print_offset_back_x_mm", "print_offset_back_y_mm"
DUPLEX, COLOR = "print_duplex", "print_color"


@dataclass(frozen=True)
class PrintSettings:
    front: tuple[float, float]
    back: tuple[float, float]
    duplex: bool
    color: str          # مفتاح من COLORS

    @classmethod
    def load(cls, settings: Settings) -> "PrintSettings":
        color = settings.get(COLOR, "red")
        return cls((settings.get_float(FRONT_X), settings.get_float(FRONT_Y)),
                   (settings.get_float(BACK_X), settings.get_float(BACK_Y)),
                   settings.get(DUPLEX, "0") == "1", color if color in COLORS else "red")

    def save(self, settings: Settings) -> None:
        settings.set(FRONT_X, self.front[0])
        settings.set(FRONT_Y, self.front[1])
        settings.set(BACK_X, self.back[0])
        settings.set(BACK_Y, self.back[1])
        settings.set(DUPLEX, "1" if self.duplex else "0")
        settings.set(COLOR, self.color)

    def offset(self, index: int) -> tuple[float, float]:
        """إزاحة الصفحة رقم index (من الصفر) في ملف الطباعة: الفردية خلفية عند الطباعة على الوجهين."""
        return self.back if self.duplex and index % 2 == 1 else self.front

    @property
    def ink(self) -> str:
        return COLORS[self.color]


@dataclass(frozen=True)
class PrintPage:
    student_id: int
    full_name: str
    page: int
    scan_id: int | None
    items: list[tuple[LayoutBox, str]]   # (الخانة، النص المطبوع فيها)


@dataclass(frozen=True)
class PrintJob:
    id: int
    created_at: str
    pages: int
    file: str
    order_mode: str
    marks_hash: str


def marks_signature(conn: sqlite3.Connection, exam_id: int) -> str:
    """بصمة الدرجات الحالية: تتغير إذا عُدّلت أي درجة بعد آخر طباعة."""
    rows = conn.execute(
        "SELECT student_id, part_id, value, status FROM marks WHERE exam_id = ? ORDER BY student_id, part_id",
        (exam_id,),
    ).fetchall()
    return hashlib.sha1(repr([tuple(r) for r in rows]).encode()).hexdigest()


def build_pages(conn: sqlite3.Connection, exam_id: int, order: str = ORDER_SCAN) -> list[PrintPage]:
    """صفحة لكل ورقة ممسوحة مطابقة، فيها نصوص الدرجات في مواضع خاناتها.

    ORDER_SCAN: بترتيب دخول الأوراق إلى الماسح، فتوضع الرزمة في الطابعة كما خرجت منه.
    ORDER_STUDENT: بترتيب قائمة الطلاب ثم رقم الصفحة (إذا رُتّبت الأوراق يدوياً بهذا الترتيب).
    الخانة التي لم تُصحح تبقى فارغة؛ ومجموع السؤال والنهائية لا يُطبعان إلا عند اكتمالهما.
    """
    store = ExamStore(conn)
    exam = store.get_exam(exam_id)
    if not exam.approved:
        raise AppError("الامتحان غير معتمد.")
    register = build(conn, exam_id)
    results = {r.student_id: r for r in register.results}
    question_index = {q.id: i for i, q in enumerate(register.questions)}
    boxes_by_page: dict[int, list[LayoutBox]] = {}
    for b in store.layout(exam_id):
        if b.kind != "answer":
            boxes_by_page.setdefault(b.page, []).append(b)

    scans = ScanStore(conn).pages(exam_id, MATCHED)
    if order == ORDER_STUDENT:
        position = {s.student_id: i for i, s in enumerate(store.exam_students(exam_id))}
        scans.sort(key=lambda s: (position.get(s.student_id, 1e9), s.page))
    pages = []
    for scan in scans:
        r = results.get(scan.student_id)
        if r is None:
            continue
        items = []
        for b in boxes_by_page.get(scan.page, []):
            if b.kind == "part_mark":
                value = r.parts.get(b.part_id)
            elif b.kind == "question_mark":
                value = r.questions[question_index[b.question_id]]
            else:  # final_mark
                value = r.final
            if value is not None:
                items.append((b, format_marks(value)))
        pages.append(PrintPage(r.student_id, r.full_name, scan.page, scan.id, items))
    return pages


def readiness(conn: sqlite3.Connection, exam_id: int) -> dict:
    """ملخص قبل الطباعة: عدد الصفحات، والمكتمل تصحيحهم، ومن تصحيحه ناقص."""
    register = build(conn, exam_id)
    present = [r for r in register.results if not r.absent]
    return {
        "pages": len(ScanStore(conn).pages(exam_id, MATCHED)),
        "students": len(present),
        "complete": sum(r.complete for r in present),
        "incomplete": [r.full_name for r in present if not r.complete],
        "confirmed": ScanStore(conn).is_confirmed(exam_id),
        "graded_any": bool(GradingStore(conn).marks(exam_id)),
    }


def record_job(conn: sqlite3.Connection, exam_id: int, pages: int, file: str, order: str) -> None:
    with conn:
        conn.execute("INSERT INTO print_jobs (exam_id, pages, file, order_mode, marks_hash) VALUES (?, ?, ?, ?, ?)",
                     (exam_id, pages, file, order, marks_signature(conn, exam_id)))


def jobs(conn: sqlite3.Connection, exam_id: int) -> list[PrintJob]:
    return [PrintJob(r["id"], r["created_at"], r["pages"], r["file"], r["order_mode"], r["marks_hash"])
            for r in conn.execute("SELECT * FROM print_jobs WHERE exam_id = ? ORDER BY id", (exam_id,))]
