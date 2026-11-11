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


def preview(store: ExamStore, exam_id: int) -> Path:
    """ورقة معاينة بطالب افتراضي؛ لا تُعتمد ولا تُحفظ مواضعها."""
    exam = store.get_exam(exam_id)
    questions = [q for q in store.questions(exam_id) if q.parts]
    if not questions:
        raise AppError("أضف سؤالاً فيه فرع واحد على الأقل لمعاينة الورقة.")
    final = paths.exam_dir(exam_id) / "preview.pdf"
    tmp = final.with_suffix(".tmp")
    SheetRenderer(exam, questions).render(tmp, [ExamStudent(0, "(معاينة — ليست ورقة طالب)")])
    _replace(tmp, final)
    return final


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
    boxes = SheetRenderer(exam, store.questions(exam_id)).render(tmp, students, progress)
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
    pages = alignment_test_pages(store.layout(exam_id), store.questions(exam_id), exam.total_marks)
    final = paths.exam_dir(exam_id) / "alignment-test.pdf"
    tmp = final.with_suffix(".tmp")
    write_overlay(tmp, pages, settings.get_float(OFFSET_X_KEY), settings.get_float(OFFSET_Y_KEY),
                  guides=True, title="اختبار المحاذاة")
    _replace(tmp, final)
    return final
