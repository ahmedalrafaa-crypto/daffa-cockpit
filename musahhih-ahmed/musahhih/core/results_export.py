"""تصدير سجل الدرجات إلى Excel."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .errors import AppError
from .exams import format_marks, part_letter, question_title
from .results import Register
from .roster import format_student_code


def status_text(r) -> str:
    if r.absent:
        return "غائب"
    return "مكتمل" if r.complete else "التصحيح ناقص"


def export_excel(register: Register, path: Path | str, grade_name: str, section_name: str,
                 with_parts: bool = True) -> None:
    exam, questions = register.exam, register.questions
    wb = Workbook()
    ws = wb.active
    ws.title = "سجل الدرجات"
    ws.sheet_view.rightToLeft = True
    bold = Font(bold=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(style="thin", color="999999")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="EAF0F3")

    ws.append([f"سجل درجات: {exam.name} — {exam.subject}"])
    ws.append([f"الصف: {grade_name} / شعبة {section_name}    التاريخ: \u2066{_dmy(exam.exam_date)}\u2069    "
               f"الدرجة الكلية: {format_marks(exam.total_marks)}"
               + (f"    يُحتسب أفضل {exam.answer_count} أسئلة" if exam.answer_count else "")])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])

    header = ["ت", "الرقم التعريفي", "اسم الطالب", "الصف", "الشعبة"]
    for qi, q in enumerate(questions):
        if with_parts and len(q.parts) > 1:
            header += [f"{question_title(qi)} / {part_letter(pi, exam.label_style)} (من {format_marks(p.max_marks)})"
                       for pi, p in enumerate(q.parts)]
        header.append(f"{question_title(qi)} (من {format_marks(q.total)})")
    header += [f"الدرجة النهائية (من {format_marks(exam.total_marks)})", "الحالة", "تاريخ الامتحان"]
    ws.append(header)
    header_row = ws.max_row
    for cell in ws[header_row]:
        cell.font, cell.alignment, cell.border, cell.fill = bold, center, border, head_fill

    for i, r in enumerate(register.results, start=1):
        row = [i, format_student_code(r.student_id), r.full_name, grade_name, section_name]
        for qi, q in enumerate(questions):
            if with_parts and len(q.parts) > 1:
                row += [r.parts.get(p.id) for p in q.parts]
            row.append(r.questions[qi])
        row += [r.final, status_text(r), _dmy(exam.exam_date)]
        ws.append(row)
        for cell in ws[ws.max_row]:
            cell.border = border
            cell.alignment = Alignment(horizontal="center") if cell.column != 3 else Alignment(horizontal="right")
        # السؤال غير المحتسب (أجب عن N من M) بخط مائل رمادي
        col = 6
        for qi, q in enumerate(questions):
            col += len(q.parts) if with_parts and len(q.parts) > 1 else 0
            if not r.counted[qi] and r.complete:
                ws.cell(ws.max_row, col).font = Font(italic=True, color="888888")
            col += 1
        ws.cell(ws.max_row, len(header) - 2).font = bold

    stats = register.stats()
    ws.append([])
    for label, value in (("عدد الطلاب", stats["students"]), ("الغائبون", stats["absent"]),
                         ("تصحيحهم ناقص", stats["incomplete"]), ("المتوسط", _round(stats["average"])),
                         ("أعلى درجة", stats["highest"]), ("أدنى درجة", stats["lowest"]),
                         ("الناجحون (نصف الدرجة فأكثر)", stats["passed"])):
        ws.append(["", "", label, value])
        ws.cell(ws.max_row, 3).font = bold

    widths = {1: 5, 2: 14, 3: 30, 4: 16, 5: 8}
    for c in range(1, len(header) + 1):
        ws.column_dimensions[get_column_letter(c)].width = widths.get(c, 14)
    ws.row_dimensions[header_row].height = 45
    ws.freeze_panes = ws.cell(header_row + 1, 4)
    try:
        wb.save(path)
    except PermissionError:
        raise AppError("تعذر حفظ الملف. قد يكون مفتوحاً في Excel؛ أغلقه ثم أعد المحاولة.") from None
    except OSError:
        raise AppError("تعذر حفظ الملف في هذا المكان. اختر مكاناً آخر.") from None


def _dmy(iso: str) -> str:
    parts = iso.split("-")
    return f"{parts[2]}/{parts[1]}/{parts[0]}" if len(parts) == 3 else iso


def _round(value):
    return round(value, 2) if value is not None else None
