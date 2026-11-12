"""اختبارات ورقة الامتحان: مقاس A4، قراءة QR، علامات الزوايا، مواضع الخانات، وطبقة الطباعة."""
import cv2
import numpy as np
import pymupdf
import pytest

from musahhih.core import qr_payload
from musahhih.core.errors import AppError
from musahhih.core.roster import Roster
from musahhih.core.settings import Settings
from musahhih.sheet import geometry as g
from musahhih.sheet import workflow
from musahhih.sheet.text import LRI, PDI, isolate_formulas

SCAN_DPI = 150


def _gray(page, dpi=SCAN_DPI):
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def _mm(image, x, y, w, h, dpi=SCAN_DPI):
    k = dpi / 25.4
    return image[round(y * k):round((y + h) * k), round(x * k):round((x + w) * k)]


@pytest.fixture
def approved(qapp, data_dir, store, conn, exam):
    path = workflow.approve(store, Roster(conn), exam)
    return exam, path


def test_isolate_formulas():
    nb = "\u00a0"
    assert isolate_formulas("احسب F = m × a الآن") == f"احسب {LRI}F{nb}={nb}m{nb}×{nb}a{PDI} الآن"
    assert isolate_formulas("السعة (5 درجات)") == "السعة (5 درجات)"            # عدد مجرد لا يُعزل
    assert isolate_formulas("الطاقة (PE = ½ C V²).") == f"الطاقة {LRI}(PE{nb}={nb}½{nb}C{nb}V²){PDI}."
    assert isolate_formulas("الطاقة (PE = ½ C V²). (10 درجات)") == f"الطاقة {LRI}(PE{nb}={nb}½{nb}C{nb}V²){PDI}. (10 درجات)"
    assert isolate_formulas("(س = x + 1)") == f"(س = {LRI}x{nb}+{nb}1{PDI})"
    # درجة البند في آخر السطر لا تُدمج مع معادلة سبقتها
    assert isolate_formulas("فرق الجهد من C₁ و C₂. (4)") == f"فرق الجهد من {LRI}C₁{PDI} و {LRI}C₂{PDI}. (4)"
    assert isolate_formulas("احسب f(5) الآن") == f"احسب {LRI}f(5){PDI} الآن"
    assert isolate_formulas("قيمة f(x) = 2(x+1) صحيحة") == f"قيمة {LRI}f(x){nb}={nb}2(x+1){PDI} صحيحة"


def test_sheets_are_true_a4_one_set_per_student(approved, store):
    exam, path = approved
    doc = pymupdf.open(path)
    pages_per_student = max(b.page for b in store.layout(exam))
    assert len(doc) == 5 * pages_per_student
    for page in doc:
        assert abs(page.rect.width - 595.28) < 0.5 and abs(page.rect.height - 841.89) < 0.5
    assert store.get_exam(exam).sheets_file == "exams/00001/sheets.pdf"


def test_every_page_qr_identifies_student_exam_and_page(approved, store):
    exam, path = approved
    doc = pymupdf.open(path)
    students = store.exam_students(exam)
    per = len(doc) // len(students)
    detector = cv2.QRCodeDetector()
    seen = set()
    for index, page in enumerate(doc):
        text, _, _ = detector.detectAndDecode(_gray(page))
        code = qr_payload.decode(text)
        assert code is not None, f"تعذر قراءة QR في الصفحة {index + 1}"
        assert code.exam_id == exam
        assert code.student_id == students[index // per].student_id
        assert code.page == index % per + 1
        seen.add(code)
    assert len(seen) == len(doc)


def test_corner_marks_and_empty_mark_boxes(approved, store):
    exam, path = approved
    doc = pymupdf.open(path)
    image = _gray(doc[0])
    for x, y in g.corner_marks():
        assert _mm(image, x + 0.5, y + 0.5, g.CORNER_SIZE - 1, g.CORNER_SIZE - 1).max() < 60
    # داخل كل خانة درجة أبيض تماماً (محجوزة للطباعة اللاحقة)
    for box in store.layout(exam):
        if box.kind != "answer":
            inside = _mm(_gray(doc[box.page - 1]), box.x + 1, box.y + 1, box.w - 2, box.h - 2)
            assert inside.min() > 240, box


def test_layout_boxes_are_complete_and_never_overlap_answers(approved, store):
    exam, _ = approved
    boxes = store.layout(exam)
    questions = store.questions(exam)
    parts = [p for q in questions for p in q.parts]
    assert sorted(b.part_id for b in boxes if b.kind == "part_mark") == sorted(p.id for p in parts)
    assert sorted(b.part_id for b in boxes if b.kind == "answer") == sorted(p.id for p in parts)
    assert sorted(b.question_id for b in boxes if b.kind == "question_mark") == sorted(q.id for q in questions)
    assert [b.page for b in boxes if b.kind == "final_mark"] == [1]
    for b in boxes:
        assert b.x >= g.GUTTER_X - 2 and b.x + b.w <= g.CONTENT_R + 1.01
        assert b.y >= g.QR_Y and b.y + b.h <= g.CONTENT_BOTTOM + 0.01
    marks = [b for b in boxes if b.kind != "answer"]
    answers = [b for b in boxes if b.kind == "answer"]

    def overlap(a, b):
        return a.page == b.page and a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h

    assert not any(overlap(m, a) for m in marks for a in answers)
    assert not any(overlap(a, b) for i, a in enumerate(answers) for b in answers[i + 1:])
    assert not any(overlap(a, b) for i, a in enumerate(marks) for b in marks[i + 1:])


def test_single_part_question_uses_question_box_and_long_exam_paginates(qapp, data_dir, store, conn, section):
    Roster(conn).add_student(section, "طالب واحد")
    exam_id = store.create_exam("طويل", "م", section, "2026-01-01", 60)
    for _ in range(6):
        store.add_part(store.add_question(exam_id), "اشرح بالتفصيل.", 10, 12)
    workflow.approve(store, Roster(conn), exam_id)
    boxes = store.layout(exam_id)
    assert not [b for b in boxes if b.kind == "part_mark"]
    assert len([b for b in boxes if b.kind == "question_mark"]) == 6
    assert max(b.page for b in boxes) >= 3
    assert all(b.y + b.h <= g.CONTENT_BOTTOM + 0.01 for b in boxes)


def test_approve_requires_students_and_matching_sum(qapp, data_dir, store, conn, section):
    exam_id = store.create_exam("x", "م", section, "2026-01-01", 10)
    store.add_part(store.add_question(exam_id), "س", 10)
    with pytest.raises(AppError, match="لا يوجد طلاب"):
        workflow.approve(store, Roster(conn), exam_id)
    assert not store.get_exam(exam_id).approved


def test_preview_does_not_approve(qapp, data_dir, store, exam):
    path = workflow.preview(store, exam)
    assert len(pymupdf.open(path)) >= 1
    assert not store.get_exam(exam).approved and store.layout(exam) == []


def test_alignment_overlay_prints_only_marks_inside_their_boxes(approved, store, conn):
    exam, sheets = approved
    settings = Settings(conn)
    path = workflow.alignment_test(store, settings, exam)
    overlay = pymupdf.open(path)
    boxes = store.layout(exam)
    assert len(overlay) == max(b.page for b in boxes)
    sheet = pymupdf.open(sheets)
    for number, page in enumerate(overlay, start=1):
        assert abs(page.rect.width - 595.28) < 0.5
        assert not page.get_images()                      # لا خلفية ولا صورة للورقة
        ink = _gray(page) < 128
        allowed = np.zeros_like(ink)
        k = SCAN_DPI / 25.4
        for b in [b for b in boxes if b.page == number and b.kind != "answer"]:
            allowed[round(b.y * k):round((b.y + b.h) * k), round(b.x * k):round((b.x + b.w) * k)] = True
            assert _mm(_gray(page), b.x, b.y, b.w, b.h).min() < 128, "خانة بلا درجة مطبوعة"
        for x, y in g.corner_marks():
            allowed[round((y - 2) * k):round((y + g.CORNER_SIZE + 2) * k),
                    round((x - 2) * k):round((x + g.CORNER_SIZE + 2) * k)] = True
        assert not (ink & ~allowed).any(), "حبر خارج خانات الدرجات"
        # فوق الورقة الأصلية: حبر الطبقة لا يلامس حدود الخانات المطبوعة
        printed = _gray(sheet[number - 1]) < 128
        assert not (ink & printed & ~_corner_mask(ink.shape, k)).any()


def _corner_mask(shape, k):
    mask = np.zeros(shape, dtype=bool)
    for x, y in g.corner_marks():
        mask[round((y - 2) * k):round((y + g.CORNER_SIZE + 2) * k),
             round((x - 2) * k):round((x + g.CORNER_SIZE + 2) * k)] = True
    return mask


def test_printer_offset_shifts_overlay(approved, store, conn):
    exam, _ = approved
    settings = Settings(conn)

    def ink_corner():
        page = pymupdf.open(workflow.alignment_test(store, settings, exam))[0]
        ys, xs = np.nonzero(_gray(page, 300) < 128)
        return xs.min() * 25.4 / 300, ys.min() * 25.4 / 300   # الحافة العليا اليسرى للحبر

    x0, y0 = ink_corner()
    settings.set(workflow.OFFSET_X_KEY, 2.0)
    settings.set(workflow.OFFSET_Y_KEY, -1.5)
    x1, y1 = ink_corner()
    assert abs((x1 - x0) - 2.0) < 0.15 and abs((y1 - y0) + 1.5) < 0.15
