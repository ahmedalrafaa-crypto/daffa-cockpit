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
