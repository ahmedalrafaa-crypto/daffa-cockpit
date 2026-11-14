import cv2
import numpy as np
import pymupdf
import pytest

from musahhih.core.errors import AppError
from musahhih.core.grading import GradingStore
from musahhih.core.roster import Roster
from musahhih.core.scans import ScanStore
from musahhih.scan import align, crops, importer
from musahhih.sheet import geometry as g
from musahhih.sheet import workflow


def _pages(pdf, dpi=150):
    out = []
    for page in pymupdf.open(pdf):
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
        out.append(cv2.cvtColor(np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3),
                                cv2.COLOR_RGB2BGR))
    return out


@pytest.fixture
def graded_exam(qapp, data_dir, store, conn, exam, tmp_path):
    """امتحان معتمد بأوراق ممسوحة لأربعة طلاب من خمسة (الثاني غائب)، والاستيراد مؤكَّد."""
    pdf = workflow.approve(store, Roster(conn), exam)
    pages = _pages(pdf)
    students = store.exam_students(exam)
    per = len(pages) // len(students)
    files = []
    for i, image in enumerate(pages):
        if i // per == 1:
            continue
        path = tmp_path / f"p{i}.png"
        cv2.imwrite(str(path), image)
        files.append(path)
    scans = ScanStore(conn)
    importer.import_files(scans, exam, files)
    grading = GradingStore(conn)
    with pytest.raises(AppError, match="أكّد"):
        grading.check_ready(exam)
    scans.confirm(exam)
    grading.check_ready(exam)
    return exam, grading, students


def test_present_and_absent(graded_exam):
    exam, grading, students = graded_exam
    assert [s.student_id for s in grading.absent(exam)] == [students[1].student_id]
    assert len(grading.students(exam)) == 4


def test_save_validates_and_never_duplicates(graded_exam, store):
    exam, grading, students = graded_exam
    q1 = store.questions(exam)[0]
    a, b = q1.parts
    sid = students[0].student_id
    with pytest.raises(AppError, match="أكبر"):
        grading.save(exam, sid, {a.id: 5.5, b.id: 1})
    with pytest.raises(AppError, match="سالبة"):
        grading.save(exam, sid, {a.id: -1})
    with pytest.raises(AppError, match="ليس له ورقة"):
        grading.save(exam, students[1].student_id, {a.id: 1})
    assert grading.marks(exam) == {}                                    # لا حفظ جزئي عند الخطأ
    grading.save(exam, sid, {a.id: 5, b.id: 4})
    grading.save(exam, sid, {a.id: 4.5, b.id: 4})                       # تعديل لاحق يستبدل ولا يكرر
    marks = grading.marks(exam)
    assert len(marks) == 2 and marks[(sid, a.id)].value == 4.5
    assert grading.question_progress(exam, q1) == (1, 4)


def test_skip_pending_and_resume_order(graded_exam, store):
    exam, grading, students = graded_exam
    q1, q2 = store.questions(exam)
    present = grading.students(exam)
    grading.skip(exam, present[0].student_id, [p.id for p in q1.parts])
    for s in present[1:]:
        grading.save(exam, s.student_id, {p.id: p.max_marks for p in q1.parts})
    pending = grading.pending(exam)
    assert [(p.question_index, p.student.student_id, p.skipped) for p in pending if p.question_index == 0] == \
           [(0, present[0].student_id, True)]
    assert grading.next_pending(exam, q1, 0) == 0                       # يلتف إلى المتخطّى
    grading.save(exam, present[0].student_id, {p.id: 0 for p in q1.parts})
    assert grading.next_pending(exam, q1, 0) is None
    assert grading.question_progress(exam, q1) == (4, 4)
    grading.skip(exam, present[0].student_id, [p.id for p in q1.parts])    # التخطي لا يمسح درجة محفوظة
    assert grading.question_progress(exam, q1) == (4, 4)
    done, total = grading.overall_progress(exam)
    assert (done, total) == (8, 16)
    assert grading.next_pending(exam, q2, len(present) - 1) == 0


def test_marks_survive_closing_the_program(tmp_path, monkeypatch):
    """الدرجة تُحفظ على القرص فور الاعتماد: إغلاق القاعدة وفتحها يعيدها كما هي."""
    from musahhih.core.db import open_db
    from musahhih.core.exams import ExamStore, ExamStudent

    path = tmp_path / "m.db"
    conn = open_db(path)
    roster = Roster(conn)
    section = roster.add_section(roster.add_grade("السادس"), "أ")
    sid = roster.add_student(section, "طالبة")
    store = ExamStore(conn)
    exam = store.create_exam("x", "م", section, "2026-01-01", 10)
    part = store.add_part(store.add_question(exam), "س", 10)
    grading = GradingStore(conn)
    monkeypatch.setattr(grading, "students", lambda exam_id: [ExamStudent(sid, "طالبة")])
    grading.save(exam, sid, {part: 7.5})
    conn.close()                                                       # كإغلاق البرنامج فجأة بعد الاعتماد
    reopened = open_db(path)
    assert GradingStore(reopened).marks(exam)[(sid, part)].value == 7.5
    reopened.close()


def test_question_crop_contains_its_boxes(graded_exam, store, conn):
    exam, grading, students = graded_exam
    boxes = store.layout(exam)
    questions = store.questions(exam)
    sid = grading.students(exam)[0].student_id
    for q in questions:
        images = crops.question_images(ScanStore(conn), exam, sid, boxes, q.id)
        assert images and all(ok and img is not None for _, img, ok in images)
        for region, image, _ in images:
            k = align.PX_PER_MM
            assert abs(image.shape[0] - region.h * k) <= 2 and abs(image.shape[1] - region.w * k) <= 2
            inside = [b for b in boxes if b.question_id == q.id and b.page == region.page]
            assert all(region.y <= b.y and b.y + b.h <= region.y + region.h for b in inside)
    # صفحة غائبة: لا صورة
    absent = grading.absent(exam)[0].student_id
    assert all(img is None for _, img, _ in crops.question_images(ScanStore(conn), exam, absent, boxes, questions[0].id))


def test_grading_screen_flow(graded_exam, store, conn, monkeypatch):
    from musahhih.ui import dialogs, grading_page
    from musahhih.ui.main_window import MainWindow

    errors, infos = [], []
    monkeypatch.setattr(dialogs, "error", lambda parent, text, title="": errors.append(text))
    monkeypatch.setattr(dialogs, "info", lambda parent, text, title="": infos.append(text))
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: True)
    exam, grading, students = graded_exam
    q1, q2 = store.questions(exam)

    window = MainWindow(conn)
    window.show_page(6)
    page = window.grading
    page.select_exam(exam)
    assert page.exam_box.count() == 1 and page.approve_button.isEnabled()
    assert "الحاضرون: 4" in page.info.text() and students[1].full_name in page.info.text()
    assert len(page.edits) == 2 and page.view.scene().items()            # صورة الإجابة معروضة

    # درجة أكبر من القصوى تُرفض ولا تُحفظ
    page.edits[0][1].setText("6")
    page.edits[1][1].setText("4")
    page.approve_next()
    assert errors and page.si == 0 and grading.marks(exam) == {}
    # أرقام عربية وفاصلة عشرية
    page.edits[0][1].setText("٤٫٥")
    page.approve_next()
    first = page.students[0].student_id
    assert page.si == 1 and grading.student_marks(exam, first)[q1.parts[0].id].value == 4.5

    page.skip()                                                          # الطالب الثاني متخطّى
    assert page.si == 2
    page.previous()
    assert page.si == 1 and "متخطّى" in page.status.text()
    page.previous()
    assert page.edits[0][1].text() == "4.5" and "مصحَّح" in page.status.text()   # تعديل درجة سابقة ممكن

    # إغلاق وإعادة فتح: يستكمل من الموضع نفسه
    page.si = 2
    page._show()
    again = MainWindow(conn)
    again.grading.select_exam(exam)
    assert (again.grading.qi, again.grading.si) == (0, 2)

    # إكمال السؤال الأول ثم الانتقال التلقائي للسؤال الثاني
    for _ in range(2):
        for _, edit, maximum in page.edits:
            edit.setText(str(maximum))
        page.approve_next()
    assert page.si == 1                                                   # التف إلى المتخطّى
    for _, edit, maximum in page.edits:
        edit.setText("0")
    page.approve_next()
    assert page.qi == 1                                                   # اكتمل الأول فانتقل للثاني
    assert grading.question_progress(exam, q1) == (4, 4)
    assert len(grading.pending(exam)) == 4

    page.page_button.setChecked(True)                                    # الصفحة كاملة
    assert page.view.scene().items()


def test_parse_mark():
    from musahhih.ui.grading_page import parse_mark
    assert parse_mark("٤٫٥") == 4.5 and parse_mark("4,5") == 4.5 and parse_mark(" 7 ") == 7
    assert parse_mark("") is None and parse_mark("abc") is None
