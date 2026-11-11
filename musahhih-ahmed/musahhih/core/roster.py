"""إدارة الصفوف والشعب والطلاب (منطق فقط، بلا واجهة)."""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass

from .errors import AppError

# الهيكل الشائع في المدارس العراقية؛ يُضاف فقط إذا طلبه المستخدم.
COMMON_GRADES: list[tuple[str, list[str]]] = [
    ("الأول المتوسط", ["أ", "ب"]),
    ("الثاني المتوسط", ["واحدة"]),
    ("الثالث المتوسط", ["أ", "ب"]),
    ("الرابع العلمي", ["أ", "ب"]),
    ("الخامس العلمي", ["أ", "ب"]),
    ("السادس العلمي", ["واحدة"]),
]


@dataclass(frozen=True)
class Grade:
    id: int
    name: str
    section_count: int
    student_count: int


@dataclass(frozen=True)
class Section:
    id: int
    grade_id: int
    name: str
    student_count: int


@dataclass(frozen=True)
class Student:
    id: int
    section_id: int
    full_name: str

    @property
    def code(self) -> str:
        return format_student_code(self.id)


def format_student_code(student_id: int) -> str:
    return f"{student_id:05d}"


def clean_name(text: str) -> str:
    """ينظّف الاسم للعرض: يزيل التطويل والفراغات الزائدة."""
    text = unicodedata.normalize("NFC", str(text)).replace("ـ", "")
    return re.sub(r"\s+", " ", text).strip()


_KEY_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def name_key(text: str) -> str:
    """مفتاح للمقارنة والترتيب: يتجاهل التشكيل واختلاف الهمزات والتاء المربوطة."""
    text = clean_name(text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.translate(_KEY_MAP).casefold()


def _require_name(text: str, what: str) -> str:
    name = clean_name(text)
    if not name:
        raise AppError(f"يرجى كتابة {what}.")
    return name


class Roster:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ---------- الصفوف ----------
    def list_grades(self) -> list[Grade]:
        rows = self.conn.execute(
            """
            SELECT g.id, g.name,
                   (SELECT COUNT(*) FROM sections s WHERE s.grade_id = g.id) AS sc,
                   (SELECT COUNT(*) FROM students t JOIN sections s ON s.id = t.section_id
                     WHERE s.grade_id = g.id) AS tc
            FROM grades g ORDER BY g.sort_order, g.id
            """
        ).fetchall()
        return [Grade(r["id"], r["name"], r["sc"], r["tc"]) for r in rows]

    def add_grade(self, name: str) -> int:
        name = _require_name(name, "اسم الصف")
        self._ensure_grade_name_free(name)
        with self.conn:
            order = self.conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM grades").fetchone()[0]
            cur = self.conn.execute("INSERT INTO grades (name, sort_order) VALUES (?, ?)", (name, order))
        return cur.lastrowid

    def rename_grade(self, grade_id: int, name: str) -> None:
        name = _require_name(name, "اسم الصف")
        self._ensure_grade_name_free(name, exclude_id=grade_id)
        with self.conn:
            self.conn.execute("UPDATE grades SET name = ? WHERE id = ?", (name, grade_id))

    def delete_grade(self, grade_id: int) -> None:
        count = self.conn.execute("SELECT COUNT(*) FROM sections WHERE grade_id = ?", (grade_id,)).fetchone()[0]
        if count:
            raise AppError("لا يمكن حذف صف يحتوي على شعب. احذف شعبه أولاً.")
        with self.conn:
            self.conn.execute("DELETE FROM grades WHERE id = ?", (grade_id,))

    def move_grade(self, grade_id: int, step: int) -> None:
        """يحرّك الصف في الترتيب: step = -1 للأعلى، +1 للأسفل."""
        ids = [g.id for g in self.list_grades()]
        i = ids.index(grade_id)
        j = i + step
        if not 0 <= j < len(ids):
            return
        ids[i], ids[j] = ids[j], ids[i]
        with self.conn:
            self.conn.executemany(
                "UPDATE grades SET sort_order = ? WHERE id = ?",
                [(order, gid) for order, gid in enumerate(ids, start=1)],
            )

    def _ensure_grade_name_free(self, name: str, exclude_id: int | None = None) -> None:
        key = name_key(name)
        for g in self.list_grades():
            if g.id != exclude_id and name_key(g.name) == key:
                raise AppError(f"يوجد صف بالاسم «{g.name}» مسبقاً.")

    # ---------- الشعب ----------
    def list_sections(self, grade_id: int) -> list[Section]:
        rows = self.conn.execute(
            """
            SELECT s.id, s.grade_id, s.name,
                   (SELECT COUNT(*) FROM students t WHERE t.section_id = s.id) AS tc
            FROM sections s WHERE s.grade_id = ? ORDER BY s.sort_order, s.id
            """,
            (grade_id,),
        ).fetchall()
        return [Section(r["id"], r["grade_id"], r["name"], r["tc"]) for r in rows]

    def get_section(self, section_id: int) -> tuple[Section, str]:
        """يعيد الشعبة مع اسم صفها."""
        r = self.conn.execute(
            """
            SELECT s.id, s.grade_id, s.name, g.name AS grade_name,
                   (SELECT COUNT(*) FROM students t WHERE t.section_id = s.id) AS tc
            FROM sections s JOIN grades g ON g.id = s.grade_id WHERE s.id = ?
            """,
            (section_id,),
        ).fetchone()
        if r is None:
            raise AppError("الشعبة غير موجودة.")
        return Section(r["id"], r["grade_id"], r["name"], r["tc"]), r["grade_name"]

    def add_section(self, grade_id: int, name: str) -> int:
        name = _require_name(name, "اسم الشعبة")
        self._ensure_section_name_free(grade_id, name)
        with self.conn:
            order = self.conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM sections WHERE grade_id = ?", (grade_id,)
            ).fetchone()[0]
            cur = self.conn.execute(
                "INSERT INTO sections (grade_id, name, sort_order) VALUES (?, ?, ?)", (grade_id, name, order)
            )
        return cur.lastrowid

    def rename_section(self, section_id: int, name: str) -> None:
        name = _require_name(name, "اسم الشعبة")
        section, _ = self.get_section(section_id)
        self._ensure_section_name_free(section.grade_id, name, exclude_id=section_id)
        with self.conn:
            self.conn.execute("UPDATE sections SET name = ? WHERE id = ?", (name, section_id))

    def delete_section(self, section_id: int) -> None:
        count = self.conn.execute("SELECT COUNT(*) FROM students WHERE section_id = ?", (section_id,)).fetchone()[0]
        if count:
            raise AppError(f"لا يمكن حذف شعبة فيها طلاب ({count}). احذف طلابها أولاً.")
        with self.conn:
            self.conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))

    def _ensure_section_name_free(self, grade_id: int, name: str, exclude_id: int | None = None) -> None:
        key = name_key(name)
        for s in self.list_sections(grade_id):
            if s.id != exclude_id and name_key(s.name) == key:
                raise AppError(f"توجد شعبة بالاسم «{s.name}» في هذا الصف مسبقاً.")

    def add_common_grades(self) -> int:
        """يضيف الصفوف الشائعة غير الموجودة مع شعبها. يعيد عدد الصفوف المضافة."""
        existing = {name_key(g.name) for g in self.list_grades()}
        added = 0
        for grade_name, sections in COMMON_GRADES:
            if name_key(grade_name) in existing:
                continue
            grade_id = self.add_grade(grade_name)
            for section_name in sections:
                self.add_section(grade_id, section_name)
            added += 1
        return added

    # ---------- الطلاب ----------
    def list_students(self, section_id: int, search: str = "") -> list[Student]:
        rows = self.conn.execute(
            "SELECT id, section_id, full_name, name_key FROM students WHERE section_id = ? ORDER BY name_key, id",
            (section_id,),
        ).fetchall()
        needle = name_key(search)
        return [
            Student(r["id"], r["section_id"], r["full_name"])
            for r in rows
            if not needle or needle in r["name_key"] or needle in format_student_code(r["id"])
        ]

    def student_exists(self, section_id: int, name: str, exclude_id: int | None = None) -> bool:
        row = self.conn.execute(
            "SELECT id FROM students WHERE section_id = ? AND name_key = ? AND id IS NOT ?",
            (section_id, name_key(name), exclude_id),
        ).fetchone()
        return row is not None

    def add_student(self, section_id: int, name: str, allow_duplicate: bool = False) -> int:
        ids = self.add_students(section_id, [name], allow_duplicate=allow_duplicate)
        if not ids:
            raise AppError(f"الطالب «{clean_name(name)}» موجود في هذه الشعبة مسبقاً.")
        return ids[0]

    def add_students(self, section_id: int, names: list[str], allow_duplicate: bool = False) -> list[int]:
        """يضيف مجموعة طلاب في عملية واحدة، ويتخطى المكرر ما لم يُسمح به."""
        self.get_section(section_id)
        seen = set() if allow_duplicate else {
            r[0] for r in self.conn.execute("SELECT name_key FROM students WHERE section_id = ?", (section_id,))
        }
        ids: list[int] = []
        with self.conn:
            for raw in names:
                name = _require_name(raw, "اسم الطالب")
                key = name_key(name)
                if not allow_duplicate:
                    if key in seen:
                        continue
                    seen.add(key)
                cur = self.conn.execute(
                    "INSERT INTO students (section_id, full_name, name_key) VALUES (?, ?, ?)",
                    (section_id, name, key),
                )
                ids.append(cur.lastrowid)
        return ids

    def rename_student(self, student_id: int, name: str) -> None:
        name = _require_name(name, "اسم الطالب")
        with self.conn:
            self.conn.execute(
                "UPDATE students SET full_name = ?, name_key = ? WHERE id = ?", (name, name_key(name), student_id)
            )

    def delete_students(self, student_ids: list[int]) -> None:
        with self.conn:
            self.conn.executemany("DELETE FROM students WHERE id = ?", [(i,) for i in student_ids])

    # ---------- إحصاءات ----------
    def totals(self) -> tuple[int, int, int]:
        """(عدد الصفوف، عدد الشعب، عدد الطلاب)."""
        r = self.conn.execute(
            "SELECT (SELECT COUNT(*) FROM grades), (SELECT COUNT(*) FROM sections), (SELECT COUNT(*) FROM students)"
        ).fetchone()
        return r[0], r[1], r[2]
