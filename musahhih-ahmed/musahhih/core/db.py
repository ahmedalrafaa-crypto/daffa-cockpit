"""الاتصال بقاعدة البيانات SQLite وترقية بنيتها.

كل تغيير في البنية يُضاف كترقية جديدة في نهاية MIGRATIONS ولا تُعدَّل
ترقية سابقة أبداً؛ بهذا لا يفقد المستخدم بياناته عند تحديث البرنامج.
قبل ترقية قاعدة موجودة تُؤخذ منها نسخة احتياطية تلقائية.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

MIGRATIONS: list[str] = [
    # 1 — المرحلة الأولى: الصفوف والشعب والطلاب والإعدادات
    """
    CREATE TABLE grades (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL UNIQUE,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE sections (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        grade_id   INTEGER NOT NULL REFERENCES grades(id) ON DELETE RESTRICT,
        name       TEXT    NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT    NOT NULL DEFAULT (datetime('now')),
        UNIQUE (grade_id, name)
    );
    -- AUTOINCREMENT يضمن أن رقم الطالب لا يُعاد استعماله بعد الحذف،
    -- فهو الرقم التعريفي الثابت الذي سيُكتب داخل QR.
    CREATE TABLE students (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
        full_name  TEXT    NOT NULL,
        name_key   TEXT    NOT NULL,
        created_at TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_students_section ON students(section_id, name_key);
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    # 2 — المرحلة الثانية: الامتحانات والأسئلة والفروع وتخطيط الورقة المعتمدة
    """
    CREATE TABLE exams (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        name             TEXT    NOT NULL,
        subject          TEXT    NOT NULL,
        section_id       INTEGER NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
        exam_date        TEXT    NOT NULL,
        total_marks      REAL    NOT NULL,
        duration_minutes INTEGER NOT NULL DEFAULT 0,
        school_name      TEXT    NOT NULL DEFAULT '',
        status           TEXT    NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved')),
        sheets_file      TEXT,
        created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
        approved_at      TEXT
    );
    CREATE TABLE questions (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id  INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        intro    TEXT    NOT NULL DEFAULT ''
    );
    CREATE INDEX idx_questions_exam ON questions(exam_id, position);
    CREATE TABLE parts (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id  INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
        position     INTEGER NOT NULL,
        text         TEXT    NOT NULL DEFAULT '',
        image        BLOB,
        max_marks    REAL    NOT NULL,
        answer_lines INTEGER NOT NULL DEFAULT 5
    );
    CREATE INDEX idx_parts_question ON parts(question_id, position);
    -- لقطة من طلاب الشعبة لحظة اعتماد الامتحان: الأرشيف لا يتغير بتعديل لاحق.
    CREATE TABLE exam_students (
        exam_id    INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
        student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
        full_name  TEXT    NOT NULL,
        position   INTEGER NOT NULL,
        PRIMARY KEY (exam_id, student_id)
    );
    -- مواضع مناطق الإجابة وخانات الدرجات بالمليمتر من الزاوية العليا اليسرى للصفحة.
    CREATE TABLE layout_boxes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id     INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
        page        INTEGER NOT NULL,
        kind        TEXT    NOT NULL CHECK (kind IN ('answer', 'part_mark', 'question_mark', 'final_mark')),
        question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
        part_id     INTEGER REFERENCES parts(id) ON DELETE CASCADE,
        x_mm REAL NOT NULL, y_mm REAL NOT NULL, w_mm REAL NOT NULL, h_mm REAL NOT NULL
    );
    CREATE INDEX idx_layout_exam ON layout_boxes(exam_id, page);
    """,
    # 3 — المرحلة الثالثة: الأوراق الممسوحة
    """
    CREATE TABLE scan_pages (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id    INTEGER NOT NULL REFERENCES exams(id) ON DELETE RESTRICT,
        seq        INTEGER NOT NULL,   -- ترتيب دخول الورقة = ترتيب الرزمة في الماسح
        source     TEXT    NOT NULL,   -- اسم الملف ورقم الصفحة فيه
        file       TEXT    NOT NULL,   -- مسار الصورة المحفوظة نسبةً لمجلد البيانات
        status     TEXT    NOT NULL CHECK (status IN ('matched', 'duplicate', 'unknown')),
        student_id INTEGER REFERENCES students(id) ON DELETE RESTRICT,
        page       INTEGER,
        aligned    INTEGER NOT NULL DEFAULT 0,  -- 1 = الصورة مقوَّمة على مقاس A4 بالعلامات المرجعية
        note       TEXT    NOT NULL DEFAULT '',
        created_at TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_scans_exam ON scan_pages(exam_id, status);
    CREATE UNIQUE INDEX idx_scans_one_matched ON scan_pages(exam_id, student_id, page) WHERE status = 'matched';
    ALTER TABLE exams ADD COLUMN import_confirmed_at TEXT;
    """,
]

SCHEMA_VERSION = len(MIGRATIONS)


def _version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _backup_before_upgrade(conn: sqlite3.Connection, path: Path, old: int) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = path.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = sqlite3.connect(folder / f"before-upgrade-v{old}-{stamp}.db")
    try:
        conn.backup(target)
    finally:
        target.close()


def open_db(path: Path | str) -> sqlite3.Connection:
    """يفتح القاعدة (وينشئها إن لم توجد) ويطبّق الترقيات الناقصة."""
    in_memory = str(path) == ":memory:"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not in_memory:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")

    current = _version(conn)
    if current > SCHEMA_VERSION:
        conn.close()
        raise RuntimeError(
            "قاعدة البيانات أُنشئت بإصدار أحدث من البرنامج. "
            "يرجى تشغيل أحدث إصدار من البرنامج."
        )
    if 0 < current < SCHEMA_VERSION and not in_memory:
        _backup_before_upgrade(conn, Path(path), current)
    for number in range(current + 1, SCHEMA_VERSION + 1):
        conn.executescript(
            f"BEGIN;\n{MIGRATIONS[number - 1]}\nPRAGMA user_version = {number};\nCOMMIT;"
        )
    return conn
