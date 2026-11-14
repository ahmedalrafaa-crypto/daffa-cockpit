import pymupdf
import pytest
from openpyxl import load_workbook

from musahhih.core import results
from musahhih.core.results_export import export_excel
from musahhih.sheet.register_pdf import write_register_pdf
from tests.test_grading import graded_exam  # noqa: F401  (fixture)


def _grade(grading, store, exam, sid, values):
    """values: درجات الفروع بالترتيب لكل الأسئلة."""
    parts = [p for q in store.questions(exam) for p in q.parts]
    for q in store.questions(exam):
        grading.save(exam, sid, {p.id: values[parts.index(p)] for p in q.parts})


def test_example_from_the_specification(graded_exam, store, conn):
    """مثال الطلب: الأول أ 5/5 ب 4/5 = 9/10؛ الثاني أ 8/10 ب 5/5 = 13/15؛ النهائية 22/25."""
    exam, grading, students = graded_exam
    sid = grading.students(exam)[0].student_id
    _grade(grading, store, exam, sid, [5, 4, 8, 5])
    r = next(x for x in results.build(conn, exam).results if x.student_id == sid)
    assert r.questions == [9, 13] and r.final == 22 and r.complete
    assert list(r.parts.values()) == [5, 4, 8, 5]


def test_absent_incomplete_and_stats(graded_exam, store, conn):
    exam, grading, students = graded_exam
    present = grading.students(exam)
    _grade(grading, store, exam, present[0].student_id, [5, 5, 10, 5])      # 25
    _grade(grading, store, exam, present[1].student_id, [2, 3, 4, 1])       # 10
    q1 = store.questions(exam)[0]
    grading.save(exam, present[2].student_id, {p.id: 1 for p in q1.parts})  # ناقص: السؤال الثاني
    reg = results.build(conn, exam)
    by_id = {r.student_id: r for r in reg.results}
    absent = by_id[students[1].student_id]
    assert absent.absent and absent.final is None
    partial = by_id[present[2].student_id]
    assert partial.final is None and partial.questions == [2, None] and partial.partial == 2
    s = reg.stats()
    assert (s["students"], s["absent"], s["incomplete"], s["graded"]) == (5, 1, 2, 2)
    assert (s["average"], s["highest"], s["lowest"], s["passed"]) == (17.5, 25, 10, 1)


def test_best_n_of_m(store, section, conn):
    from musahhih.core.exams import ExamStore
    assert results.counted_questions([20, 25, 10, 25, 15], 4) == [True, True, False, True, True]
    assert results.counted_questions([5, 5, 5], 2) == [True, True, False]       # التساوي: الأسبق
    assert results.counted_questions([1, 2], 0) == [True, True]


def test_academic_year():
    assert results.academic_year("2026-11-15") == "2026-2027"
    assert results.academic_year("2027-03-01") == "2026-2027"
    assert results.academic_year("2027-09-01") == "2027-2028"
    assert results.academic_year("bad") == ""


def test_excel_and_pdf_exports(graded_exam, store, conn, tmp_path):
    exam, grading, students = graded_exam
    present = grading.students(exam)
    for sid in [s.student_id for s in present]:
        _grade(grading, store, exam, sid, [5, 4, 8, 5])
    reg = results.build(conn, exam)
    path = tmp_path / "r.xlsx"
    export_excel(reg, path, "الرابع العلمي", "أ")
    ws = load_workbook(path).active
    assert ws.sheet_view.rightToLeft
    rows = list(ws.iter_rows(values_only=True))
    header_index = next(i for i, r in enumerate(rows) if r and r[0] == "ت")
    header = rows[header_index]
    final_col = next(i for i, h in enumerate(header) if h and str(h).startswith("الدرجة النهائية"))
    data = rows[header_index + 1: header_index + 1 + len(students)]
    assert [r[final_col] for r in data].count(22) == 4
    assert "غائب" in [r[final_col + 1] for r in data]
    # بلا فروع: أعمدة أقل
    export_excel(reg, tmp_path / "s.xlsx", "الرابع العلمي", "أ", with_parts=False)
    short = list(load_workbook(tmp_path / "s.xlsx").active.iter_rows(values_only=True))[header_index]
    assert len([h for h in short if h]) == len([h for h in header if h]) - 4

    pdf = tmp_path / "r.pdf"
    write_register_pdf(reg, pdf, "الرابع العلمي", "أ")
    doc = pymupdf.open(pdf)
    assert len(doc) >= 1 and doc[0].rect.width > doc[0].rect.height       # أفقي
    # الخط مقروء: ارتفاع سطر النص في الجدول لا يقل عن 6 نقاط
    sizes = [span["size"] for block in doc[0].get_text("dict")["blocks"] for line in block.get("lines", [])
             for span in line["spans"] if span["text"].strip()]
    assert sizes and min(sizes) >= 6


def test_results_page(graded_exam, store, conn):
    from musahhih.ui.main_window import MainWindow
    exam, grading, students = graded_exam
    present = grading.students(exam)
    _grade(grading, store, exam, present[0].student_id, [5, 4, 8, 5])
    _grade(grading, store, exam, present[1].student_id, [1, 1, 1, 1])
    window = MainWindow(conn)
    window.show_page(7)
    page = window.results
    page.select_exam(exam)
    assert page.year_box.findData("2026-2027") >= 0
    name_col = 2
    final_col = page.table.columnCount() - 2
    page.sort_box.setCurrentIndex(page.sort_box.findData("high"))
    finals = [page.table.item(r, final_col).text() for r in range(page.table.rowCount())]
    assert finals[:2] == ["22", "4"] and finals.count("—") == 3
    page.search.setText(present[1].full_name.split()[0])
    assert page.table.rowCount() >= 1
    assert present[1].full_name in [page.table.item(r, name_col).text() for r in range(page.table.rowCount())]
    page.search.clear()
    page.parts_box.setChecked(False)
    assert page.table.columnCount() == 3 + 2 + 2
    assert "الغائبون: 1" in page.summary.text()
