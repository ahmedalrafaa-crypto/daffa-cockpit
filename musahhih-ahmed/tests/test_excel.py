import pytest
from openpyxl import Workbook, load_workbook

from musahhih.core import excel_io
from musahhih.core.errors import AppError


def _xlsx(tmp_path, rows, name="in.xlsx"):
    wb = Workbook()
    for row in rows:
        wb.active.append(row)
    path = tmp_path / name
    wb.save(path)
    return path


def test_read_with_header(tmp_path):
    path = _xlsx(tmp_path, [["قائمة الشعبة"], ["ت", "اسم الطالب", "ملاحظات"], [1, "قاسم محمد", "x"], [2, " باسم  علي ", None], [3, None, None]])
    assert excel_io.read_names(path) == ["قاسم محمد", "باسم علي"]


def test_read_without_header_picks_text_column(tmp_path):
    path = _xlsx(tmp_path, [[1, "قاسم محمد"], [2, "باسم علي"], [3, "زينب حسن"]])
    assert excel_io.read_names(path) == ["قاسم محمد", "باسم علي", "زينب حسن"]


def test_bad_files(tmp_path):
    with pytest.raises(AppError):
        excel_io.read_names(_xlsx(tmp_path, [[1, 2], [3, 4]]))
    junk = tmp_path / "junk.xlsx"
    junk.write_text("not excel")
    with pytest.raises(AppError):
        excel_io.read_names(junk)
    with pytest.raises(AppError):
        excel_io.read_names(tmp_path / "old.xls")
    with pytest.raises(AppError):
        excel_io.read_names(tmp_path / "missing.xlsx")


def test_import_skips_duplicates_then_roundtrip(tmp_path, roster, section):
    roster.add_student(section, "علي حسن")
    report = excel_io.import_students(roster, section, ["علي حسن", "حسين كاظم", "حسين كاظم", "مريم جواد"])
    assert (report.found, report.added, report.duplicates) == (4, 2, 2)

    out = tmp_path / "out.xlsx"
    assert excel_io.export_students(roster, section, out) == 3
    ws = load_workbook(out).active
    assert ws.sheet_view.rightToLeft
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == ("ت", "الرقم التعريفي", "اسم الطالب", "الصف", "الشعبة")
    assert rows[1][3:] == ("الرابع العلمي", "أ")
    codes = [r[1] for r in rows[1:]]
    assert len(set(codes)) == 3 and all(len(c) == 5 for c in codes)
    # الملف المصدَّر يُقرأ من جديد كما هو
    assert sorted(excel_io.read_names(out)) == sorted(s.full_name for s in roster.list_students(section))


def test_import_many_students_is_fast(roster, section):
    names = [f"طالب رقم {i}" for i in range(600)]
    assert excel_io.import_students(roster, section, names).added == 600
    assert len(roster.list_students(section)) == 600
