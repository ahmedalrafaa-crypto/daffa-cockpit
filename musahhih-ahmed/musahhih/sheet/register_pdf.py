"""طباعة سجل الدرجات: PDF أفقي A4 بجدول عربي، بالخط المضمَّن مع البرنامج."""
from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

from ..core.errors import AppError
from ..core.exams import format_marks, part_letter, question_title
from ..core.results import Register
from ..core.results_export import status_text
from ..core.roster import format_student_code
from .render import display_date
from .text import FONT_FAMILY, font


def _cell(value) -> str:
    return "—" if value is None else format_marks(value)


def register_html(register: Register, grade_name: str, section_name: str, with_parts: bool) -> str:
    exam, questions = register.exam, register.questions
    heads = ["ت", "الرقم", "اسم الطالب"]
    for qi, q in enumerate(questions):
        if with_parts and len(q.parts) > 1:
            heads += [f"{question_title(qi)}<br>{part_letter(pi, exam.label_style)} ({format_marks(p.max_marks)})"
                      for pi, p in enumerate(q.parts)]
        heads.append(f"{question_title(qi)}<br>({format_marks(q.total)})")
    heads += [f"النهائية<br>({format_marks(exam.total_marks)})", "الحالة"]
    rows = []
    for i, r in enumerate(register.results, start=1):
        cells = [str(i), format_student_code(r.student_id), escape(r.full_name)]
        for qi, q in enumerate(questions):
            if with_parts and len(q.parts) > 1:
                cells += [_cell(r.parts.get(p.id)) for p in q.parts]
            value = _cell(r.questions[qi])
            cells.append(value if r.counted[qi] or not r.complete else f"<i style='color:#888'>{value}</i>")
        cells += [f"<b>{_cell(r.final)}</b>", status_text(r)]
        shade = " style='background:#f4f6f8'" if i % 2 == 0 else ""
        rows.append(f"<tr{shade}>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    s = register.stats()
    avg = "—" if s["average"] is None else format_marks(round(s["average"], 2))
    note = f" · يُحتسب أفضل {exam.answer_count} أسئلة (غير المحتسب بخط مائل)" if exam.answer_count else ""
    return f"""
<html><body dir="rtl" style="font-family:'{FONT_FAMILY}'">
<h2 align="center">سجل درجات: {escape(exam.name)} — {escape(exam.subject)}</h2>
<p align="center">{escape(exam.school_name)} · الصف: {escape(grade_name)} / شعبة {escape(section_name)}
 · التاريخ: {display_date(exam.exam_date)} · الدرجة الكلية: {format_marks(exam.total_marks)}{note}</p>
<table width="100%" border="1" cellspacing="0" cellpadding="3" style="border-collapse:collapse" align="center">
<tr style="background:#eaf0f3">{''.join(f'<th>{h}</th>' for h in heads)}</tr>
{''.join(rows)}
</table>
<p>عدد الطلاب: {s['students']} · الغائبون: {s['absent']} · تصحيحهم ناقص: {s['incomplete']} ·
 المتوسط: {avg} · أعلى درجة: {_cell(s['highest'])} · أدنى درجة: {_cell(s['lowest'])} ·
 الناجحون (نصف الدرجة فأكثر): {s['passed']}</p>
</body></html>"""


def write_register_pdf(register: Register, path: Path | str, grade_name: str, section_name: str,
                       with_parts: bool = True) -> None:
    writer = QPdfWriter(str(path))
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Landscape,
                                     QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter))
    writer.setTitle(f"سجل درجات {register.exam.name}")
    writer.setResolution(96)   # تخطيط الجدول بمقياس الشاشة؛ بدقة الطابعة العالية يخرج الخط مجهرياً
    doc = QTextDocument()
    base = font(3.6)
    base.setPointSizeF(9)
    doc.setDefaultFont(base)
    doc.setHtml(register_html(register, grade_name, section_name, with_parts))
    doc.setPageSize(QSizeF(writer.width(), writer.height()))
    try:
        doc.print_(writer)
    except Exception:
        raise AppError("تعذر إنشاء ملف الطباعة.") from None
    if not Path(path).exists():
        raise AppError("تعذر إنشاء ملف الطباعة. قد يكون الملف مفتوحاً في برنامج آخر.")
