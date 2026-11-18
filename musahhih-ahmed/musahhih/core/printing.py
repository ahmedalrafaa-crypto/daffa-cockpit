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
from ..sheet import geometry as g
from .annotations import AnnotationStore
from .numwords import in_words
from .settings import Settings

ORDER_SCAN, ORDER_STUDENT = "scan", "student"
COLORS = {"red": "#c00000", "black": "#000000", "blue": "#1f3fbf"}

# مفاتيح الإعدادات (الوجه الأمامي يستعمل المفتاحين القديمين نفسيهما)
FRONT_X, FRONT_Y = "print_offset_x_mm", "print_offset_y_mm"
BACK_X, BACK_Y = "print_offset_back_x_mm", "print_offset_back_y_mm"
DUPLEX, COLOR = "print_duplex", "print_color"
TICKS = "print_ticks"          # موضع علامات التصحيح: gutter / answer / off
RIGHT, WRONG, HALF = "right", "wrong", "half"


def kind_for(value: float | None, maximum: float) -> str | None:
    """علامة التصحيح من درجة المدرّس: الكاملة ✓، والصفر ✗، وما بينهما «نصف صح»؛ غير المصحح بلا علامة."""
    if value is None:
        return None
    if value >= maximum - 1e-9:
        return RIGHT
    if value <= 1e-9:
        return WRONG
    return HALF
# اتجاه الورق في الطابعة، كما اكتشفه المستخدم بصفحة تحديد الاتجاه
FACE, TOP, STACK = "print_paper_face", "print_paper_top", "print_paper_stack"


def loading_instructions(face: str, top: str, stack: str) -> str:
    """تعليمات وضع أوراق الطلاب في درج الطابعة. face: up/down، top: first/last، stack: top/bottom."""
    if not (face and top and stack):
        return ""
    side = "إلى الأعلى" if face == "up" else "إلى الأسفل"
    edge = ("وأعلى الورقة (جهة الترويسة ورمز QR) يدخل الطابعة أولاً" if top == "first"
            else "وأسفل الورقة يدخل الطابعة أولاً (أعلاها جهتك)")
    first = "فوق الرزمة" if stack == "top" else "في أسفل الرزمة"
    return (f"ضع أوراق الطلاب ووجهها المكتوب (الصفحة الأولى) {side}، {edge}، "
            f"وتكون أول ورقة في ملف الطباعة {first}.")


def saved_instructions(settings: Settings) -> str:
    return loading_instructions(settings.get(FACE), settings.get(TOP), settings.get(STACK))


@dataclass(frozen=True)
class PrintSettings:
    front: tuple[float, float]
    back: tuple[float, float]
    duplex: bool
    color: str          # مفتاح من COLORS
    ticks: str = "gutter"   # موضع علامات التصحيح ✓ ✗ ½

    @classmethod
    def load(cls, settings: Settings) -> "PrintSettings":
        color = settings.get(COLOR, "red")
        ticks = settings.get(TICKS, "gutter")
        return cls((settings.get_float(FRONT_X), settings.get_float(FRONT_Y)),
                   (settings.get_float(BACK_X), settings.get_float(BACK_Y)),
                   settings.get(DUPLEX, "0") == "1", color if color in COLORS else "red",
                   ticks if ticks in ("gutter", "answer", "off") else "gutter")

    def save(self, settings: Settings) -> None:
        settings.set(FRONT_X, self.front[0])
        settings.set(FRONT_Y, self.front[1])
        settings.set(BACK_X, self.back[0])
        settings.set(BACK_Y, self.back[1])
        settings.set(DUPLEX, "1" if self.duplex else "0")
        settings.set(COLOR, self.color)
        settings.set(TICKS, self.ticks)

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
    ticks: list[tuple[LayoutBox, LayoutBox, str]] = ()   # (خانة الدرجة، مساحة الإجابة، right/wrong/half)
    annotations: list = ()   # دوائر وخطوط رسمها المدرّس على هذه الصفحة (core.annotations.Annotation)


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
    part_max = {p.id: p.max_marks for q in register.questions for p in q.parts}
    single_part = {q.id: q.parts[0] for q in register.questions if len(q.parts) == 1}
    boxes_by_page: dict[int, list[LayoutBox]] = {}
    answers: dict[int, LayoutBox] = {}
    for b in store.layout(exam_id):
        if b.kind == "answer":
            answers[b.part_id] = b
        else:
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
        items, ticks = [], []
        for b in boxes_by_page.get(scan.page, []):
            # علامة التصحيح لكل فرع (أو للسؤال ذي الفرع الواحد) مشتقة من درجة المدرّس
            part = None
            if b.kind == "part_mark":
                part = b.part_id
            elif b.kind == "question_mark" and b.question_id in single_part:
                part = single_part[b.question_id].id
            if part is not None and part in answers:
                kind = kind_for(r.parts.get(part), part_max[part])
                if kind:
                    ticks.append((b, answers[part], kind))
            if b.kind == "part_mark":
                value = r.parts.get(b.part_id)
            elif b.kind == "question_mark":
                value = r.questions[question_index[b.question_id]]
            else:  # final_mark
                value = r.final
            if value is not None:
                items.append((b, format_marks(value)))
                if b.kind == "final_mark":   # النهائية رقماً في خانتها، وكتابةً تحتها
                    words_box = LayoutBox(b.page, "final_words", None, None, *g.FINAL_WORDS_BOX)
                    items.append((words_box, in_words(value)))
        drawn = AnnotationStore(conn).for_page(exam_id, r.student_id, scan.page)
        pages.append(PrintPage(r.student_id, r.full_name, scan.page, scan.id, items, ticks, drawn))
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
