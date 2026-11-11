"""استيراد قوائم الطلاب من Excel وتصديرها إليه."""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils.exceptions import InvalidFileException

from .errors import AppError
from .roster import Roster, clean_name, name_key


@dataclass(frozen=True)
class ImportReport:
    found: int        # عدد الأسماء المقروءة من الملف
    added: int        # ما أضيف فعلاً
    duplicates: int   # ما تُخطّي لأنه موجود أو مكرر داخل الملف


# كلمة كاملة حتى لا يُحسب اسم مثل «قاسم» أو «باسم» عنواناً للعمود.
_HEADER_WORDS = {"اسم", "الاسم", "اسماء", "الاسماء"}


def read_names(path: Path | str) -> list[str]:
    """يقرأ أسماء الطلاب من أول ورقة في ملف xlsx.

    إن وُجد عنوان عمود يحتوي كلمة «اسم» يؤخذ ذلك العمود، وإلا يؤخذ
    العمود الذي يحتوي أكبر عدد من الخلايا النصية.
    """
    path = Path(path)
    if path.suffix.lower() == ".xls":
        raise AppError("صيغة xls القديمة غير مدعومة. افتح الملف في Excel واحفظه بصيغة xlsx ثم أعد المحاولة.")
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except FileNotFoundError:
        raise AppError("الملف غير موجود.") from None
    except PermissionError:
        raise AppError("تعذر فتح الملف. أغلقه في Excel ثم أعد المحاولة.") from None
    except (InvalidFileException, zipfile.BadZipFile, OSError, KeyError, ValueError):
        raise AppError("تعذر قراءة الملف. تأكد أنه ملف Excel سليم بصيغة xlsx.") from None
    try:
        rows = [list(row) for row in wb.worksheets[0].iter_rows(values_only=True)]
    finally:
        wb.close()

    def text(value) -> str:
        return clean_name(value) if isinstance(value, str) else ""

    column, start = None, 0
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if _HEADER_WORDS & set(name_key(text(value)).split()):
                column, start = c, r + 1
                break
        if column is not None:
            break
    if column is None:
        counts: dict[int, int] = {}
        for row in rows:
            for c, value in enumerate(row):
                if text(value):
                    counts[c] = counts.get(c, 0) + 1
        if not counts:
            raise AppError("لم يُعثر على أسماء في الملف.")
        column = max(counts, key=lambda c: (counts[c], -c))

    names = [text(row[column]) for row in rows[start:] if column < len(row)]
    names = [n for n in names if n]
    if not names:
        raise AppError("لم يُعثر على أسماء في الملف.")
    return names


def import_students(roster: Roster, section_id: int, names: list[str]) -> ImportReport:
    added = roster.add_students(section_id, names)
    return ImportReport(found=len(names), added=len(added), duplicates=len(names) - len(added))


def export_students(roster: Roster, section_id: int, path: Path | str) -> int:
    """يكتب قائمة طلاب الشعبة في ملف xlsx ويعيد عددهم."""
    section, grade_name = roster.get_section(section_id)
    students = roster.list_students(section_id)
    wb = Workbook()
    ws = wb.active
    ws.title = "الطلاب"
    ws.sheet_view.rightToLeft = True
    ws.append(["ت", "الرقم التعريفي", "اسم الطالب", "الصف", "الشعبة"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for i, s in enumerate(students, start=1):
        ws.append([i, s.code, s.full_name, grade_name, section.name])
    for letter, width in zip("ABCDE", (6, 16, 38, 20, 12)):
        ws.column_dimensions[letter].width = width
    try:
        wb.save(path)
    except PermissionError:
        raise AppError("تعذر حفظ الملف. قد يكون مفتوحاً في Excel؛ أغلقه ثم أعد المحاولة.") from None
    except OSError:
        raise AppError("تعذر حفظ الملف في هذا المكان. اختر مكاناً آخر.") from None
    return len(students)
