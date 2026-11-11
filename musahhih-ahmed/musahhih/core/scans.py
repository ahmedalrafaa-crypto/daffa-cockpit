"""سجل الأوراق الممسوحة: المطابقة، التكرار، الأوراق المجهولة، والنواقص."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .. import paths
from .errors import AppError
from .exams import ExamStore

MATCHED, DUPLICATE, UNKNOWN = "matched", "duplicate", "unknown"


@dataclass(frozen=True)
class ScanPage:
    id: int
    exam_id: int
    seq: int
    source: str
    file: str
    status: str
    student_id: int | None
    page: int | None
    aligned: bool
    note: str

    @property
    def path(self) -> Path:
        return paths.data_dir() / self.file


@dataclass(frozen=True)
class StudentPages:
    student_id: int
    full_name: str
    present: list[int]
    missing: list[int]


@dataclass(frozen=True)
class ScanSummary:
    total: int
    matched: int
    duplicate: int
    unknown: int
    misaligned: int
    students: int
    complete: int      # طلاب اكتملت صفحاتهم
    absent: int        # طلاب بلا أي صفحة


def _scan(r: sqlite3.Row) -> ScanPage:
    return ScanPage(r["id"], r["exam_id"], r["seq"], r["source"], r["file"], r["status"], r["student_id"],
                    r["page"], bool(r["aligned"]), r["note"])


class ScanStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.exams = ExamStore(conn)

    # ---------- قراءة ----------
    def pages(self, exam_id: int, status: str | None = None) -> list[ScanPage]:
        sql, args = "SELECT * FROM scan_pages WHERE exam_id = ?", [exam_id]
        if status:
            sql += " AND status = ?"
            args.append(status)
        return [_scan(r) for r in self.conn.execute(sql + " ORDER BY seq, id", args)]

    def get(self, scan_id: int) -> ScanPage:
        r = self.conn.execute("SELECT * FROM scan_pages WHERE id = ?", (scan_id,)).fetchone()
        if r is None:
            raise AppError("الورقة غير موجودة.")
        return _scan(r)

    def matched_page(self, exam_id: int, student_id: int, page: int) -> ScanPage | None:
        r = self.conn.execute(
            "SELECT * FROM scan_pages WHERE exam_id = ? AND student_id = ? AND page = ? AND status = 'matched'",
            (exam_id, student_id, page),
        ).fetchone()
        return _scan(r) if r else None

    def student_report(self, exam_id: int) -> list[StudentPages]:
        count = self.exams.page_count(exam_id)
        present: dict[int, set[int]] = {}
        for p in self.pages(exam_id, MATCHED):
            present.setdefault(p.student_id, set()).add(p.page)
        return [
            StudentPages(s.student_id, s.full_name, sorted(present.get(s.student_id, ())),
                         [n for n in range(1, count + 1) if n not in present.get(s.student_id, ())])
            for s in self.exams.exam_students(exam_id)
        ]

    def summary(self, exam_id: int) -> ScanSummary:
        pages = self.pages(exam_id)
        report = self.student_report(exam_id)
        return ScanSummary(
            total=len(pages),
            matched=sum(p.status == MATCHED for p in pages),
            duplicate=sum(p.status == DUPLICATE for p in pages),
            unknown=sum(p.status == UNKNOWN for p in pages),
            misaligned=sum(p.status == MATCHED and not p.aligned for p in pages),
            students=len(report),
            complete=sum(not s.missing for s in report),
            absent=sum(not s.present for s in report),
        )

    def is_confirmed(self, exam_id: int) -> bool:
        r = self.conn.execute("SELECT import_confirmed_at FROM exams WHERE id = ?", (exam_id,)).fetchone()
        return bool(r and r[0])

    # ---------- كتابة ----------
    def _unconfirm(self, exam_id: int) -> None:
        self.conn.execute("UPDATE exams SET import_confirmed_at = NULL WHERE id = ?", (exam_id,))

    def classify(self, exam_id: int, student_id: int | None, page: int | None) -> str:
        """حالة ورقة جديدة تحمل هذا الطالب وهذه الصفحة."""
        if student_id is None or page is None:
            return UNKNOWN
        return DUPLICATE if self.matched_page(exam_id, student_id, page) else MATCHED

    def add(self, exam_id: int, source: str, image: bytes, student_id: int | None, page: int | None,
            aligned: bool, note: str = "") -> ScanPage:
        """يحفظ صورة الورقة وسجلها معاً؛ إن فشل حفظ الملف لا يبقى سجل."""
        status = self.classify(exam_id, student_id, page)
        folder = paths.exam_dir(exam_id) / "scans"
        folder.mkdir(exist_ok=True)
        with self.conn:
            seq = self.conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM scan_pages WHERE exam_id = ?", (exam_id,)
            ).fetchone()[0]
            cur = self.conn.execute(
                "INSERT INTO scan_pages (exam_id, seq, source, file, status, student_id, page, aligned, note)"
                " VALUES (?, ?, ?, '', ?, ?, ?, ?, ?)",
                (exam_id, seq, source, status, student_id, page, int(aligned), note),
            )
            path = folder / f"{cur.lastrowid:06d}.jpg"
            try:
                path.write_bytes(image)
            except OSError:
                raise AppError(f"تعذر حفظ صورة الورقة في:\n{folder}\nتأكد من وجود مساحة كافية على القرص.") from None
            self.conn.execute(
                "UPDATE scan_pages SET file = ? WHERE id = ?",
                (path.relative_to(paths.data_dir()).as_posix(), cur.lastrowid),
            )
            self._unconfirm(exam_id)
        return self.get(cur.lastrowid)

    def replace_image(self, scan_id: int, image: bytes, aligned: bool) -> None:
        scan = self.get(scan_id)
        scan.path.write_bytes(image)
        with self.conn:
            self.conn.execute("UPDATE scan_pages SET aligned = ? WHERE id = ?", (int(aligned), scan_id))

    def assign(self, scan_id: int, student_id: int, page: int) -> ScanPage:
        """يعيّن ورقة (مجهولة غالباً) لطالب وصفحة يدوياً."""
        scan = self.get(scan_id)
        if student_id not in {s.student_id for s in self.exams.exam_students(scan.exam_id)}:
            raise AppError("هذا الطالب ليس ضمن طلاب الامتحان.")
        if not 1 <= page <= self.exams.page_count(scan.exam_id):
            raise AppError("رقم الصفحة خارج عدد صفحات الامتحان.")
        existing = self.matched_page(scan.exam_id, student_id, page)
        status = DUPLICATE if existing and existing.id != scan_id else MATCHED
        with self.conn:
            self.conn.execute(
                "UPDATE scan_pages SET status = ?, student_id = ?, page = ?, note = 'عُيّنت يدوياً' WHERE id = ?",
                (status, student_id, page, scan_id),
            )
            self._unconfirm(scan.exam_id)
        return self.get(scan_id)

    def promote(self, scan_id: int) -> None:
        """يعتمد الورقة المكررة بدل الأصلية (تصبح الأصلية هي المكررة)."""
        scan = self.get(scan_id)
        if scan.status != DUPLICATE:
            raise AppError("هذه الورقة ليست مكررة.")
        with self.conn:
            self.conn.execute(
                "UPDATE scan_pages SET status = 'duplicate' WHERE exam_id = ? AND student_id = ? AND page = ?"
                " AND status = 'matched'", (scan.exam_id, scan.student_id, scan.page),
            )
            self.conn.execute("UPDATE scan_pages SET status = 'matched' WHERE id = ?", (scan_id,))
            self._unconfirm(scan.exam_id)

    def delete(self, scan_id: int) -> None:
        """يحذف الورقة وصورتها. إن كانت معتمدة ولها نسخة مكررة تُعتمد النسخة الأقدم مكانها."""
        scan = self.get(scan_id)
        with self.conn:
            self.conn.execute("DELETE FROM scan_pages WHERE id = ?", (scan_id,))
            if scan.status == MATCHED:
                r = self.conn.execute(
                    "SELECT id FROM scan_pages WHERE exam_id = ? AND student_id = ? AND page = ?"
                    " AND status = 'duplicate' ORDER BY seq LIMIT 1", (scan.exam_id, scan.student_id, scan.page),
                ).fetchone()
                if r:
                    self.conn.execute("UPDATE scan_pages SET status = 'matched' WHERE id = ?", (r[0],))
            self._unconfirm(scan.exam_id)
        scan.path.unlink(missing_ok=True)

    def delete_duplicates(self, exam_id: int) -> int:
        duplicates = self.pages(exam_id, DUPLICATE)
        for scan in duplicates:
            self.delete(scan.id)
        return len(duplicates)

    def confirm(self, exam_id: int) -> None:
        """يثبت اكتمال الاستيراد. يُرفض ما دامت هناك أوراق مجهولة أو مكررة لم تُراجع."""
        s = self.summary(exam_id)
        if s.matched == 0:
            raise AppError("لم تُستورد أي ورقة مطابقة بعد.")
        if s.unknown:
            raise AppError(f"توجد {s.unknown} ورقة غير معروفة. عيّنها لطلابها أو احذفها أولاً.")
        if s.duplicate:
            raise AppError(f"توجد {s.duplicate} ورقة مكررة. احذفها أو اعتمدها بدل الأصل أولاً.")
        with self.conn:
            self.conn.execute("UPDATE exams SET import_confirmed_at = datetime('now') WHERE id = ?", (exam_id,))
