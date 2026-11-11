import pytest

from musahhih.core import qr_payload
from musahhih.core.errors import AppError
from musahhih.core.exams import ExamStudent, LayoutBox, format_marks, part_letter, question_title
from musahhih.core.qr_payload import SheetCode
from musahhih.core.settings import Settings


def test_titles_and_formatting():
    assert question_title(0) == "السؤال الأول" and question_title(25) == "السؤال 26"
    assert part_letter(1) == "ب"
    assert format_marks(5.0) == "5" and format_marks(2.5) == "2.5"


def test_create_with_question_count_and_validation(store, section):
    exam_id = store.create_exam("شهري", "فيزياء", section, "2026-01-01", 20, question_count=3)
    assert len(store.questions(exam_id)) == 3
    for bad in (dict(name=" "), dict(subject=""), dict(total_marks=0)):
        args = dict(name="a", subject="b", section_id=section, exam_date="2026-01-01", total_marks=10) | bad
        with pytest.raises(AppError):
            store.create_exam(**args)


def test_sum_and_question_totals(store, exam):
    questions = store.questions(exam)
    assert [q.total for q in questions] == [10, 15]
    assert store.marks_sum(exam) == 25
    store.check_ready(exam)


def test_reorder_and_edit(store, exam):
    q1, q2 = store.questions(exam)
    store.move_question(q2.id, -1)
    assert [q.id for q in store.questions(exam)] == [q2.id, q1.id]
    a, b = q1.parts
    store.move_part(b.id, -1)
    store.move_part(b.id, -1)  # في القمة: لا تغيير
    assert [p.id for p in store.questions(exam)[1].parts] == [b.id, a.id]
    store.update_part(a.id, "نص جديد", 2.5, 3, b"img")
    part = store.questions(exam)[1].parts[1]
    assert (part.text, part.max_marks, part.answer_lines, part.image) == ("نص جديد", 2.5, 3, b"img")
    with pytest.raises(AppError):
        store.update_part(a.id, "x", 0, 3, None)
    with pytest.raises(AppError):
        store.add_part(q1.id, "x", 5, 999)


def test_not_ready_cases(store, exam, section):
    q1 = store.questions(exam)[0]
    store.update_part(q1.parts[0].id, "x", 4, 4, None)
    with pytest.raises(AppError, match="لا يساوي"):
        store.check_ready(exam)
    store.update_part(q1.parts[0].id, "x", 5, 4, None)
    store.add_question(exam)
    with pytest.raises(AppError, match="بلا فروع"):
        store.check_ready(exam)
    empty = store.create_exam("فارغ", "م", section, "2026-01-01", 10)
    with pytest.raises(AppError):
        store.check_ready(empty)


def test_approve_locks_and_unapprove_unlocks(store, roster, exam, section):
    students = [ExamStudent(s.id, s.full_name) for s in roster.list_students(section)]
    boxes = [LayoutBox(1, "final_mark", None, None, 40, 21, 24, 12)]
    with pytest.raises(AppError):
        store.approve(exam, [], boxes, "x.pdf")
    store.approve(exam, students, boxes, "exams/00001/sheets.pdf")
    assert store.get_exam(exam).approved
    assert store.exam_students(exam) == students
    assert store.layout(exam) == boxes
    q1 = store.questions(exam)[0]
    for action in (
        lambda: store.add_question(exam),
        lambda: store.delete_question(q1.id),
        lambda: store.update_part(q1.parts[0].id, "x", 1, 1, None),
        lambda: store.add_part(q1.id, "x", 1),
        lambda: store.delete_exam(exam),
        lambda: store.approve(exam, students, boxes, "x.pdf"),
    ):
        with pytest.raises(AppError):
            action()
    # اسم الطالب في الأرشيف لا يتغير بتعديل لاحق، وطالب له ورقة لا يُحذف
    roster.rename_student(students[0].student_id, "اسم معدّل")
    assert store.exam_students(exam)[0].full_name == students[0].full_name
    with pytest.raises(AppError):
        roster.delete_students([students[0].student_id])
    assert len(roster.list_students(section)) == 5

    store.unapprove(exam)
    assert not store.get_exam(exam).approved and store.layout(exam) == [] and store.exam_students(exam) == []
    store.add_question(exam)


def test_qr_payload_roundtrip_and_rejection():
    code = SheetCode(12, 345, 2)
    text = qr_payload.encode(code)
    assert qr_payload.decode(text) == code and code.human() == "12-00345-2"
    tampered = text.replace("|345|", "|346|")
    for bad in (tampered, "hello", "MA1|1|2|3", "MA2|1|2|3|00", text + "|x", "MA1|1|2|0|" + text[-2:]):
        assert qr_payload.decode(bad) is None


def test_settings(conn):
    settings = Settings(conn)
    assert settings.get("k", "d") == "d" and settings.get_float("x", 1.5) == 1.5
    settings.set("x", 2.5)
    settings.set("x", -0.5)
    assert settings.get_float("x") == -0.5
    settings.set("x", "abc")
    assert settings.get_float("x", 7) == 7


def test_add_question_with_part_is_atomic(store, section):
    exam_id = store.create_exam("x", "م", section, "2026-01-01", 10)
    question_id, part_id = store.add_question_with_part(exam_id, "عرّف الكثافة.", 4, 3)
    assert [(q.id, [p.id for p in q.parts]) for q in store.questions(exam_id)] == [(question_id, [part_id])]
    with pytest.raises(AppError):
        store.add_question_with_part(exam_id, "س", 0)          # درجة غير صالحة
    with pytest.raises(AppError):
        store.add_question_with_part(exam_id, "س", 5, 999)      # أسطر غير صالحة
    assert len(store.questions(exam_id)) == 1                   # لا سؤال فارغ متبقٍّ
