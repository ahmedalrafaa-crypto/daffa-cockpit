import sqlite3

import pytest

from musahhih.core import db
from musahhih.core.roster import Roster


def test_data_survives_reopen(tmp_path):
    path = tmp_path / "m.db"
    conn = db.open_db(path)
    roster = Roster(conn)
    section = roster.add_section(roster.add_grade("الأول المتوسط"), "أ")
    roster.add_student(section, "أحمد محمد علي")
    conn.close()

    conn = db.open_db(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert [s.full_name for s in Roster(conn).list_students(section)] == ["أحمد محمد علي"]
    conn.close()


def test_upgrade_keeps_data_and_makes_backup(tmp_path, monkeypatch):
    path = tmp_path / "m.db"
    conn = db.open_db(path)
    Roster(conn).add_grade("السادس العلمي")
    conn.close()

    monkeypatch.setattr(db, "MIGRATIONS", db.MIGRATIONS + ["CREATE TABLE extra (id INTEGER PRIMARY KEY);"])
    monkeypatch.setattr(db, "SCHEMA_VERSION", db.SCHEMA_VERSION + 1)
    conn = db.open_db(path)
    assert [g.name for g in Roster(conn).list_grades()] == ["السادس العلمي"]
    conn.execute("SELECT * FROM extra")
    conn.close()
    assert len(list((tmp_path / "backups").glob("before-upgrade-v1-*.db"))) == 1


def test_newer_database_is_refused(tmp_path):
    path = tmp_path / "m.db"
    raw = sqlite3.connect(path)
    raw.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION + 5}")
    raw.close()
    with pytest.raises(RuntimeError):
        db.open_db(path)


def test_foreign_keys_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO students (section_id, full_name, name_key) VALUES (999, 'x', 'x')")
