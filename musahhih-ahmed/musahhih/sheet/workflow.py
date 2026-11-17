"""خطوات إنتاج ملفات الامتحان: المعاينة، الاعتماد، واختبار المحاذاة."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .. import paths
from ..core.errors import AppError
from ..core.exams import ExamStore, ExamStudent
from ..core.roster import Roster
from ..core.settings import Settings
from .overlay import alignment_test_pages, write_overlay
from .render import SheetRenderer

OFFSET_X_KEY = "print_offset_x_mm"
OFFSET_Y_KEY = "print_offset_y_mm"


def _replace(tmp: Path, final: Path) -> None:
    try:
        os.replace(tmp, final)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise AppError(f"تعذر حفظ الملف:\n{final}\nأغلقه إن كان مفتوحاً في برنامج آخر ثم أعد المحاولة.") from None


def _render(renderer: SheetRenderer, tmp: Path, students, progress=None):
    """يرسم الملف المؤقت، ولا يترك ملفاً ناقصاً إن فشل الرسم."""
    try:
        return renderer.render(tmp, students, progress)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def preview(store: ExamStore, exam_id: int) -> Path:
    """ورقة معاينة بطالب افتراضي؛ لا تُعتمد ولا تُحفظ مواضعها."""
    exam = store.get_exam(exam_id)
    questions = [q for q in store.questions(exam_id) if q.parts]
    if not questions:
        raise AppError("أضف سؤالاً فيه فرع واحد على الأقل لمعاينة الورقة.")
    final = paths.exam_dir(exam_id) / "preview.pdf"
    tmp = final.with_suffix(".tmp")
    _render(SheetRenderer(exam, questions), tmp, [ExamStudent(0, "(معاينة — ليست ورقة طالب)")])
    _replace(tmp, final)
    return final


def layout_info(store: ExamStore, exam_id: int) -> tuple[int, dict[int, int]]:
    """(عدد صفحات ورقة الطالب، الأسطر المطبوعة فعلاً لكل فرع) كما ستخرج عند الاعتماد."""
    exam = store.get_exam(exam_id)
    questions = [q for q in store.questions(exam_id) if q.parts]
    if not questions:
        return 0, {}
    tmp = paths.exam_dir(exam_id) / "layout-check.tmp"
    renderer = SheetRenderer(exam, questions)
    try:
        _render(renderer, tmp, [ExamStudent(0, "")])
    finally:
        tmp.unlink(missing_ok=True)
    return len(renderer.pages), dict(renderer.part_lines)


def sheet_pages(store: ExamStore, exam_id: int) -> int:
    """عدد صفحات ورقة الطالب الواحد كما ستُطبع (من ورقة المعاينة)."""
    import pymupdf
    with pymupdf.open(preview(store, exam_id)) as doc:
        return doc.page_count


def approve(store: ExamStore, roster: Roster, exam_id: int,
            progress: Callable[[int, int], None] | None = None) -> Path:
    """يعتمد الامتحان وينشئ ملف أوراق جميع طلاب الشعبة."""
    store.check_ready(exam_id)
    exam = store.get_exam(exam_id)
    if exam.approved:
        raise AppError("الامتحان معتمد مسبقاً.")
    students = [ExamStudent(s.id, s.full_name) for s in roster.list_students(exam.section_id)]
    if not students:
        raise AppError("لا يوجد طلاب في شعبة هذا الامتحان. أضف الطلاب أولاً.")
    final = paths.exam_dir(exam_id) / "sheets.pdf"
    tmp = final.with_suffix(".tmp")
    boxes = _render(SheetRenderer(exam, store.questions(exam_id)), tmp, students, progress)
    _replace(tmp, final)
    store.approve(exam_id, students, boxes, final.relative_to(paths.data_dir()).as_posix())
    return final


def sheets_path(store: ExamStore, exam_id: int) -> Path:
    exam = store.get_exam(exam_id)
    path = paths.data_dir() / (exam.sheets_file or "")
    if not exam.sheets_file or not path.exists():
        raise AppError("ملف أوراق الطلاب غير موجود.")
    return path


def alignment_test(store: ExamStore, settings: Settings, exam_id: int) -> Path:
    """ملف يُطبع فوق ورقة طالب مطبوعة للتأكد من وقوع الدرجات داخل خاناتها."""
    exam = store.get_exam(exam_id)
    if not exam.approved:
        raise AppError("اعتمد الامتحان أولاً.")
    from ..core.printing import PrintSettings
    pages = alignment_test_pages(store.layout(exam_id), store.questions(exam_id), exam.total_marks)
    final = paths.exam_dir(exam_id) / "alignment-test.pdf"
    tmp = final.with_suffix(".tmp")
    ps = PrintSettings.load(settings)
    # على الوجهين: الصفحة الثانية من ورقة الطالب على الوجه الخلفي فتأخذ إزاحته
    write_overlay(tmp, pages, guides=True, title="اختبار المحاذاة", color=ps.ink,
                  offsets=[ps.offset(i) for i in range(len(pages))])
    _replace(tmp, final)
    return final


def print_marks(conn, exam_id: int, order: str, print_settings) -> tuple[Path, int]:
    """ينشئ ملف طباعة الدرجات (درجات فقط بلا خلفية) ويسجّله في سجل الطباعة. يعيد (المسار، عدد الصفحات)."""
    from datetime import datetime

    from ..core import printing
    from .overlay import OverlayItem
    pages = printing.build_pages(conn, exam_id, order)
    if not pages:
        raise AppError("لا توجد أوراق ممسوحة لهذا الامتحان.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    final = paths.exam_dir(exam_id) / f"marks-print-{stamp}.pdf"
    tmp = final.with_suffix(".tmp")
    try:
        write_overlay(tmp, [[OverlayItem(b, t) for b, t in p.items] for p in pages],
                      title="طباعة الدرجات", color=print_settings.ink,
                      offsets=[print_settings.offset(i) for i in range(len(pages))])
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    _replace(tmp, final)
    printing.record_job(conn, exam_id, len(pages), final.relative_to(paths.data_dir()).as_posix(), order)
    return final, len(pages)
