import json

import pytest

from musahhih.core import exam_package
from musahhih.core.errors import AppError
from musahhih.core.roster import Roster
from musahhih.sheet import geometry as g
from musahhih.sheet import workflow


def test_answer_n_of_m_validation(store, section):
    exam_id = store.create_exam("x", "م", section, "2026-01-01", 100, answer_count=4)
    for _ in range(5):
        store.add_part(store.add_question(exam_id), "س", 25)
    assert store.marks_sum(exam_id) == 125 and store.counted_total(exam_id) == 100
    store.check_ready(exam_id)
    store.update_exam(exam_id, "x", "م", section, "2026-01-01", 100, 0, "", answer_count=6)
    with pytest.raises(AppError, match="عدد الأسئلة"):
        store.check_ready(exam_id)
    store.update_exam(exam_id, "x", "م", section, "2026-01-01", 125, 0, "", answer_count=0)
    store.check_ready(exam_id)
    store.update_exam(exam_id, "x", "م", section, "2026-01-01", 100, 0, "", answer_count=3)
    with pytest.raises(AppError, match="أفضل 3"):
        store.check_ready(exam_id)
    with pytest.raises(AppError):
        store.update_exam(exam_id, "x", "م", section, "2026-01-01", 100, 0, "", answer_count=-1)


def test_package_roundtrip_with_image(store, section, tmp_path):
    exam_id = store.create_exam("امتحان", "فيزياء", section, "2026-01-01", 10, 90, answer_count=1,
                                instructions="أجب عن سؤال واحد")
    store.add_part(store.add_question(exam_id, "مقدمة"), "نص {صورة} تتمة", 10, 4, b"\x89PNGfake")
    path = tmp_path / "e.mexam"
    exam_package.write(path, exam_package.from_store(store, exam_id))
    data = exam_package.read(path)
    new_id = exam_package.import_exam(store, data, section, "2026-02-02", "مدرسة")
    old, new = store.get_exam(exam_id), store.get_exam(new_id)
    assert (new.name, new.subject, new.total_marks, new.duration_minutes, new.answer_count, new.instructions) == \
           (old.name, old.subject, 10, 90, 1, "أجب عن سؤال واحد")
    assert new.exam_date == "2026-02-02" and new.school_name == "مدرسة" and not new.approved
    p = store.questions(new_id)[0].parts[0]
    assert (store.questions(new_id)[0].intro, p.text, p.image, p.answer_lines) == ("مقدمة", "نص {صورة} تتمة", b"\x89PNGfake", 4)
    # القيم المعدلة في النافذة تتقدم على ما في الملف
    other = exam_package.import_exam(store, data, section, "2026-02-02", name="اسم آخر", total_marks=20)
    assert store.get_exam(other).name == "اسم آخر" and store.get_exam(other).total_marks == 20


def test_bad_packages(tmp_path):
    def write(text):
        path = tmp_path / "b.mexam"
        path.write_text(text, encoding="utf-8")
        return path

    for text in ("not json", "[]", json.dumps({"format": "other"}),
                 json.dumps({"format": "musahhih-exam", "version": 99}),
                 json.dumps({"format": "musahhih-exam", "version": 1, "name": "a", "subject": "b",
                             "total_marks": 1, "questions": []}),
                 json.dumps({"format": "musahhih-exam", "version": 1, "name": "a", "subject": "b", "total_marks": 1,
                             "questions": [{"parts": [{"text": "x", "max_marks": 0, "answer_lines": 3}]}]})):
        with pytest.raises(AppError):
            exam_package.read(write(text))
    with pytest.raises(AppError):
        exam_package.read(tmp_path / "missing.mexam")


def test_failed_import_leaves_no_exam(store, section):
    data = {"name": "a", "subject": "b", "total_marks": 10, "questions": [
        {"parts": [{"text": "x", "max_marks": 5, "answer_lines": 3}]},
        {"parts": [{"text": "y", "max_marks": 5, "answer_lines": 999}]}]}
    with pytest.raises(AppError):
        exam_package.import_exam(store, data, section, "2026-01-01")
    assert store.list_exams() == []


def test_instructions_and_image_marker_layout(qapp, data_dir, store, conn, section):
    Roster(conn).add_student(section, "طالبة")

    def layout(instructions):
        exam_id = store.create_exam("x", "م", section, "2026-01-01", 20, instructions=instructions)
        q = store.add_question(exam_id)
        store.add_part(q, "عنوان\nقبل {صورة} بعد", 10, 3, _png())
        store.add_part(q, "الفرع الثاني", 10, 3)
        workflow.approve(store, Roster(conn), exam_id)
        return {b.kind + str(b.part_id): b for b in store.layout(exam_id)}, exam_id

    plain, _ = layout("")
    with_text, _ = layout("تعليمات مهمة\nالسطر الثاني")
    assert min(b.y for k, b in with_text.items() if k.startswith("question_mark")) > \
           min(b.y for k, b in plain.items() if k.startswith("question_mark")) + 6
    assert all(b.y + b.h <= g.CONTENT_BOTTOM for b in with_text.values())


def _png() -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage
    image = QImage(300, 120, QImage.Format.Format_RGB32)
    image.fill(QColor(200, 200, 255))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)
