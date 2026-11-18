"""المرحلة السادسة: ملف طباعة الدرجات فوق الأوراق الأصلية."""
import numpy as np
import pymupdf
import pytest

from musahhih.core import printing
from musahhih.core.errors import AppError
from musahhih.core.printing import ORDER_SCAN, ORDER_STUDENT, PrintSettings
from musahhih.core.scans import ScanStore
from musahhih.core.settings import Settings
from musahhih.sheet import geometry as g
from musahhih.sheet import workflow
from tests.test_grading import graded_exam  # noqa: F401  (fixture)

DPI = 150
K = DPI / 25.4


def _gray(page):
    pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def _grade_all(grading, store, exam, values=(5, 4, 8, 5)):
    parts = [p for q in store.questions(exam) for p in q.parts]
    for s in grading.students(exam):
        for q in store.questions(exam):
            grading.save(exam, s.student_id, {p.id: values[parts.index(p)] for p in q.parts})


def test_pages_follow_scan_order_and_carry_marks(graded_exam, store, conn):
    exam, grading, students = graded_exam
    present = grading.students(exam)
    q1, q2 = store.questions(exam)
    # الطالب الأول مكتمل، والثاني صُحح سؤاله الأول فقط، والبقية بلا درجات
    grading.save(exam, present[0].student_id, {q1.parts[0].id: 5, q1.parts[1].id: 4})
    grading.save(exam, present[0].student_id, {q2.parts[0].id: 8, q2.parts[1].id: 5})
    grading.save(exam, present[1].student_id, {q1.parts[0].id: 2, q1.parts[1].id: 1})
    pages = printing.build_pages(conn, exam, ORDER_SCAN)
    scans = ScanStore(conn).pages(exam)
    assert [p.scan_id for p in pages] == [s.id for s in scans]                  # ترتيب الرزمة نفسه
    first = [p for p in pages if p.student_id == present[0].student_id]
    texts = {(b.kind, b.part_id or b.question_id): t for p in first for b, t in p.items}
    assert texts[("part_mark", q1.parts[0].id)] == "5" and texts[("question_mark", q1.id)] == "9"
    assert texts[("question_mark", q2.id)] == "13" and texts[("final_mark", None)] == "22"
    second = {(b.kind, b.part_id or b.question_id): t
              for p in pages if p.student_id == present[1].student_id for b, t in p.items}
    assert second[("question_mark", q1.id)] == "3"
    assert ("question_mark", q2.id) not in second and ("final_mark", None) not in second   # غير مكتمل: فارغ
    untouched = [p for p in pages if p.student_id == present[2].student_id]
    assert untouched and all(not p.items for p in untouched)


def test_student_order(graded_exam, store, conn):
    exam, grading, students = graded_exam
    order = {s.student_id: i for i, s in enumerate(store.exam_students(exam))}
    pages = printing.build_pages(conn, exam, ORDER_STUDENT)
    keys = [(order[p.student_id], p.page) for p in pages]
    assert keys == sorted(keys) and len(pages) == len(ScanStore(conn).pages(exam))


def test_print_file_inside_boxes_and_not_on_the_printed_lines(graded_exam, store, conn):
    exam, grading, students = graded_exam
    _grade_all(grading, store, exam)
    ps = PrintSettings((0.0, 0.0), (0.0, 0.0), False, "black", ticks="off")     # الأرقام وحدها
    path, count = workflow.print_marks(conn, exam, ORDER_STUDENT, ps)
    doc = pymupdf.open(path)
    assert len(doc) == count == len(ScanStore(conn).pages(exam))
    sheets = pymupdf.open(workflow.sheets_path(store, exam))
    per = sheets.page_count // len(students)
    boxes = store.layout(exam)
    pages = printing.build_pages(conn, exam, ORDER_STUDENT)
    for page, info in zip(doc, pages):
        assert abs(page.rect.width - 595.28) < 0.5 and abs(page.rect.height - 841.89) < 0.5
        assert not page.get_images()                                       # درجات فقط بلا خلفية
        ink = _gray(page) < 128
        allowed = np.zeros_like(ink)
        for b in boxes:
            if b.page == info.page and b.kind != "answer":
                allowed[round(b.y * K):round((b.y + b.h) * K), round(b.x * K):round((b.x + b.w) * K)] = True
        assert ink.any() and not (ink & ~allowed).any()
        # فوق الورقة الأصلية نفسها: حبر الدرجات لا يلامس حدود الخانات المطبوعة
        student_index = [s.student_id for s in students].index(info.student_id)
        original = _gray(sheets[student_index * per + info.page - 1]) < 128
        assert not (ink & original).any()


def test_duplex_back_offset_applies_to_every_second_page(graded_exam, store, conn):
    exam, grading, students = graded_exam
    _grade_all(grading, store, exam)

    def ink_corner(ps, index):
        path, _ = workflow.print_marks(conn, exam, ORDER_STUDENT, ps)
        ys, xs = np.nonzero(_gray(pymupdf.open(path)[index]) < 128)
        return xs.min() / K, ys.min() / K

    plain = PrintSettings((1.0, 0.5), (1.0, 0.5), False, "black", ticks="off")
    duplex = PrintSettings((1.0, 0.5), (3.0, -1.5), True, "black", ticks="off")
    for index, expected in ((0, (0.0, 0.0)), (1, (2.0, -2.0))):
        a, b = ink_corner(plain, index), ink_corner(duplex, index)
        assert abs((b[0] - a[0]) - expected[0]) < 0.15 and abs((b[1] - a[1]) - expected[1]) < 0.15


def test_settings_roundtrip_and_colors(conn):
    settings = Settings(conn)
    default = PrintSettings.load(settings)
    assert default.color == "red" and not default.duplex and default.front == (0.0, 0.0)
    PrintSettings((1.5, -0.5), (2.0, 1.0), True, "blue").save(settings)
    loaded = PrintSettings.load(settings)
    assert (loaded.front, loaded.back, loaded.duplex, loaded.color) == ((1.5, -0.5), (2.0, 1.0), True, "blue")
    assert loaded.offset(0) == (1.5, -0.5) and loaded.offset(1) == (2.0, 1.0) and loaded.offset(2) == (1.5, -0.5)
    settings.set(printing.COLOR, "purple")
    assert PrintSettings.load(settings).color == "red"


def test_print_jobs_and_changed_marks(graded_exam, store, conn):
    exam, grading, students = graded_exam
    _grade_all(grading, store, exam)
    assert printing.jobs(conn, exam) == []
    ps = PrintSettings((0, 0), (0, 0), False, "red")
    workflow.print_marks(conn, exam, ORDER_SCAN, ps)
    jobs = printing.jobs(conn, exam)
    assert len(jobs) == 1 and jobs[0].pages == len(ScanStore(conn).pages(exam))
    assert jobs[0].marks_hash == printing.marks_signature(conn, exam)
    sid = grading.students(exam)[0].student_id
    q1 = store.questions(exam)[0]
    grading.save(exam, sid, {q1.parts[0].id: 1, q1.parts[1].id: 1})          # تعديل بعد الطباعة
    assert jobs[0].marks_hash != printing.marks_signature(conn, exam)
    info = printing.readiness(conn, exam)
    assert info["complete"] == info["students"] == 4 and info["incomplete"] == []


def test_unapproved_exam_cannot_print(store, section, conn):
    exam = store.create_exam("x", "م", section, "2026-01-01", 10)
    with pytest.raises(AppError):
        printing.build_pages(conn, exam)


def test_print_page_flow(graded_exam, store, conn, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    from musahhih.ui import dialogs
    from musahhih.ui.main_window import MainWindow
    from musahhih.ui.print_page import PreviewDialog
    exam, grading, students = graded_exam
    _grade_all(grading, store, exam)
    opened, asked, infos = [], [], []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()))
    monkeypatch.setattr(dialogs, "info", lambda *a, **k: infos.append(a[1]))
    answers = iter([False, True])          # الطباعة الثانية: رفض ثم موافقة
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: asked.append(a[1]) or next(answers))

    window = MainWindow(conn)
    window.show_page(8)
    page = window.printing
    page.select_exam(exam)
    assert page.print_button.isEnabled() and "صفحات للطباعة" in page.info.text()

    page.duplex.setChecked(True)
    page.back_x.setValue(2.5)
    assert page.back_x.isEnabled()
    loaded = PrintSettings.load(Settings(conn))
    assert loaded.duplex and loaded.back[0] == 2.5

    dialog = PreviewDialog(page, conn, exam, ORDER_SCAN, "#c00000")
    assert dialog.list.count() == len(ScanStore(conn).pages(exam)) and dialog.view.scene().items()

    # ضبط وضع الورق عبر المساعد (كما يفعل المستخدم بعد تجربة الورقتين)
    from musahhih.ui.print_page import OrientationDialog
    wizard = OrientationDialog(page, Settings(conn), exam)
    for (key, box), value in zip(wizard.boxes, ("down", "first", "top")):
        box.setCurrentIndex(box.findData(value))
    assert "إلى الأسفل" in wizard.result.text()
    wizard.accept()
    page._show_loading()
    assert "وضع الأوراق في طابعتك" in page.loading.text()
    page._print()                                             # الأول: بلا سؤال
    assert not asked and len(printing.jobs(conn, exam)) == 1 and opened[-1].endswith(".pdf")
    page._print()                                             # الثاني: يسأل، والجواب «لا»
    assert asked and len(printing.jobs(conn, exam)) == 1
    page._print()                                             # الثالث: يسأل، والجواب «نعم»
    assert len(printing.jobs(conn, exam)) == 2 and "آخر ملف طباعة" in page.info.text()

    page._alignment()
    assert opened[-1].endswith("alignment-test.pdf")


def test_orientation_test_page_and_instructions(qapp, data_dir, conn, tmp_path, monkeypatch):
    from musahhih.sheet.orientation import write_orientation_test
    from musahhih.ui import dialogs
    from musahhih.ui.print_page import OrientationDialog
    path = tmp_path / "o.pdf"
    write_orientation_test(path)
    doc = pymupdf.open(path)
    assert len(doc) == 2 and abs(doc[0].rect.width - 595.28) < 0.5
    # الرقم الكبير مختلف في الصفحتين، والسهم في أعلى الصفحة (حبر في الربع العلوي)
    tops = []
    for page in doc:
        ink = _gray(page) < 128
        ys = np.nonzero(ink.any(axis=1))[0]
        tops.append(ys.min() / K)
    assert all(t < 25 for t in tops)
    assert printing.loading_instructions("", "first", "top") == ""
    text = printing.loading_instructions("up", "last", "bottom")
    assert "إلى الأعلى" in text and "أسفل الورقة يدخل" in text and "في أسفل الرزمة" in text
    settings = Settings(conn)
    dialog = OrientationDialog(None, settings, None)
    assert "أجب عن الأسئلة" in dialog.result.text()
    dialog.reject()
    assert printing.saved_instructions(settings) == ""


def test_print_warns_when_orientation_not_set(graded_exam, store, conn, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    from musahhih.ui import dialogs
    from musahhih.ui.main_window import MainWindow
    exam, grading, students = graded_exam
    _grade_all(grading, store, exam)
    asked = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: None)
    monkeypatch.setattr(dialogs, "info", lambda *a, **k: None)
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: asked.append(a[1]) or False)
    window = MainWindow(conn)
    window.printing.select_exam(exam)
    assert "لم يُضبط بعد" in window.printing.loading.text()
    window.printing._print()
    assert asked and "وضع الورق" in asked[0] and printing.jobs(conn, exam) == []    # رُفض: لا ملف



def test_tick_kind_follows_the_teachers_mark():
    assert printing.kind_for(4, 4) == printing.RIGHT
    assert printing.kind_for(0, 4) == printing.WRONG
    assert printing.kind_for(2.5, 4) == printing.HALF
    assert printing.kind_for(None, 4) is None


def _tick_exam(graded_exam, store, grading):
    """الفرع أ كامل ✓، والفرع ب صفر ✗، وفرعا السؤال الثاني نصف صح."""
    exam, _, _ = graded_exam
    _grade_all(grading, store, exam, values=(5, 0, 4, 2))
    return exam


def test_ticks_built_per_part(graded_exam, store, conn):
    exam, grading, students = graded_exam
    _tick_exam(graded_exam, store, grading)
    q1, q2 = store.questions(exam)
    kinds = {}
    for p in printing.build_pages(conn, exam, ORDER_STUDENT):
        for box, answer, kind in p.ticks:
            assert answer.kind == "answer" and answer.part_id == box.part_id
            kinds[box.part_id] = kind
    assert kinds[q1.parts[0].id] == "right" and kinds[q1.parts[1].id] == "wrong"
    assert kinds[q2.parts[0].id] == "half" and kinds[q2.parts[1].id] == "half"


def _ink_regions(conn, store, exam, position):
    from musahhih.sheet import ticks as t
    ps = PrintSettings((0, 0), (0, 0), False, "black", ticks=position)
    path, _ = workflow.print_marks(conn, exam, ORDER_STUDENT, ps)
    return pymupdf.open(path), printing.build_pages(conn, exam, ORDER_STUDENT), t


def test_gutter_ticks_sit_in_the_blank_strip_left_of_the_boxes(graded_exam, store, conn):
    exam, grading, students = graded_exam
    _tick_exam(graded_exam, store, grading)
    doc, pages, t = _ink_regions(conn, store, exam, "gutter")
    sheets = pymupdf.open(workflow.sheets_path(store, exam))
    per = sheets.page_count // len(students)
    for page, info in zip(doc, pages):
        ink = _gray(page) < 128
        allowed = np.zeros_like(ink)
        for b in store.layout(exam):                                  # الأرقام داخل الخانات
            if b.page == info.page and b.kind != "answer":
                allowed[round(b.y * K):round((b.y + b.h) * K), round(b.x * K):round((b.x + b.w) * K)] = True
        for box, _, _ in info.ticks:                                  # والعلامات في الشريط يسار الخانة
            cx, cy = t.gutter_center(box)
            r = t.GUTTER_SIZE * 0.62
            allowed[round((cy - r) * K):round((cy + r) * K), round((cx - r) * K):round((cx + r) * K)] = True
        assert not (ink & ~allowed).any()
        student_index = [s.student_id for s in students].index(info.student_id)
        original = _gray(sheets[student_index * per + info.page - 1]) < 128
        assert not (ink & original).any()                             # لا تلمس شيئاً مطبوعاً على الورقة
        assert len(info.ticks) == sum(1 for b in store.layout(exam) if b.page == info.page and b.kind == "part_mark")


def test_answer_ticks_are_large_and_inside_the_answer_area(graded_exam, store, conn):
    exam, grading, students = graded_exam
    _tick_exam(graded_exam, store, grading)
    doc, pages, t = _ink_regions(conn, store, exam, "answer")
    for page, info in zip(doc, pages):
        ink = _gray(page) < 128
        for _, answer, _ in info.ticks:
            region = ink[round(answer.y * K):round((answer.y + answer.h) * K),
                         round(answer.x * K):round((answer.x + answer.w) * K)]
            ys, xs = np.nonzero(region)
            assert len(xs) and (xs.max() - xs.min()) / K > 8                   # علامة كبيرة (أكثر من 8 ملم)
    none_doc, _, _ = _ink_regions(conn, store, exam, "off")
    with_doc, _, _ = _ink_regions(conn, store, exam, "gutter")
    assert (_gray(with_doc[0]) < 128).sum() > (_gray(none_doc[0]) < 128).sum()     # «بدون» لا يرسم علامات
