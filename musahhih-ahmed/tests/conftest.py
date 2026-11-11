import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from musahhih.core.db import open_db
from musahhih.core.roster import Roster


@pytest.fixture
def conn():
    connection = open_db(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def roster(conn):
    return Roster(conn)


@pytest.fixture
def section(roster):
    grade_id = roster.add_grade("الرابع العلمي")
    return roster.add_section(grade_id, "أ")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    from musahhih.app import create_app
    return QApplication.instance() or create_app([])


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSAHHIH_DATA", str(tmp_path))
    return tmp_path


@pytest.fixture
def store(conn):
    from musahhih.core.exams import ExamStore
    return ExamStore(conn)


@pytest.fixture
def exam(store, roster, section):
    """امتحان من سؤالين وأربعة فروع مجموعها 25، وخمسة طلاب."""
    roster.add_students(section, ["أحمد محمد علي", "زينب حسن كاظم", "مصطفى جواد", "حسين علي", "مريم كريم"])
    exam_id = store.create_exam("امتحان الشهر الأول", "الفيزياء", section, "2026-11-15", 25, 45, "ثانوية الاختبار")
    q1 = store.add_question(exam_id)
    store.add_part(q1, "عرّف السعة الكهربائية.", 5, 4)
    store.add_part(q1, "ما العوامل المؤثرة في السعة؟ C = ε₀ A / d", 5, 5)
    q2 = store.add_question(exam_id, "متسعة سعتها 4 μF ربطت إلى بطارية 12 V.")
    store.add_part(q2, "احسب الشحنة Q = C × ΔV.", 10, 8)
    store.add_part(q2, "علل: تزداد السعة عند إدخال عازل.", 5, 4)
    return exam_id
