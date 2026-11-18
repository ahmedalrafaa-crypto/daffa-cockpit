"""دائرة حول الخطأ أو خط تحته: يرسمها المدرّس على صورة الإجابة، وتُطبع في موضعها على الورقة."""
import numpy as np
import pymupdf
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from musahhih.core import printing
from musahhih.core.annotations import AnnotationStore
from musahhih.core.errors import AppError
from musahhih.core.printing import ORDER_STUDENT, PrintSettings
from musahhih.scan import align
from musahhih.sheet import workflow
from tests.test_grading import graded_exam  # noqa: F401  (fixture)

DPI = 150
K = DPI / 25.4


def test_store_rules(store, section, conn, roster):
    exam = store.create_exam("x", "م", section, "2026-01-01", 10)
    sid = roster.add_student(section, "طالبة")
    a = AnnotationStore(conn)
    circle = a.add(exam, sid, 1, "circle", 120, 90, 100, 80)          # تُرتَّب زوايا الدائرة
    assert (circle.x1, circle.y1, circle.x2, circle.y2) == (100, 80, 120, 90)
    assert a.add(exam, sid, 1, "underline", 50, 50, 50.5, 50.4) is None    # نقرة عابرة ليست علامة
    line = a.add(exam, sid, 2, "underline", 60, 100, 300, 100)              # تُقصّ عند حافة الورقة
    assert line.x2 == 210
    with pytest.raises(AppError):
        a.add(exam, sid, 1, "star", 1, 1, 30, 30)
    assert a.undo_last(exam, sid, pages={1}) and [x.page for x in a.for_student(exam, sid)] == [2]
    assert a.undo_last(exam, sid) and not a.undo_last(exam, sid)


def test_drawing_with_the_mouse_saves_the_true_position_and_prints_it(graded_exam, store, conn, qapp):
    from musahhih.ui.main_window import MainWindow
    exam, grading, students = graded_exam
    window = MainWindow(conn)
    window.resize(1280, 800)
    window.show()
    window.show_page(6)
    page = window.grading
    page.select_exam(exam)
    qapp.processEvents()
    view = page.view
    item, meta = next((i, m) for i, m in view._items if m)
    page_no, ox, oy = meta
    # دائرة مقصودة حول نقطة معروفة على الورقة: من (110، oy+12) إلى (150، oy+20) ملم
    target = (110.0, oy + 12, 150.0, oy + 20)
    k = align.PX_PER_MM

    def to_view(x_mm, y_mm):
        point = view.mapFromScene(item.x() + (x_mm - ox) * k, item.y() + (y_mm - oy) * k)
        return QPoint(point.x(), point.y())

    page.circle_tool.setChecked(True)
    start, end = to_view(target[0], target[1]), to_view(target[2], target[3])
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(view.viewport(), end)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    sid = page.students[page.si].student_id
    saved = AnnotationStore(conn).for_student(exam, sid)
    assert len(saved) == 1 and saved[0].kind == "circle" and saved[0].page == page_no
    got = (saved[0].x1, saved[0].y1, saved[0].x2, saved[0].y2)
    assert all(abs(a - b) < 1.0 for a, b in zip(got, target)), got        # خطأ أقل من 1 ملم
    assert view._marks                                                    # ظاهرة فوق الصورة

    page.line_tool.setChecked(True)                                       # الأداتان لا تعملان معاً
    assert not page.circle_tool.isChecked() and view.tool == "underline"
    page.line_tool.setChecked(False)
    assert view.tool is None

    # تُطبع في الموضع نفسه: حبر على محيط الدائرة، ولا حبر في مركزها
    path, _ = workflow.print_marks(conn, exam, ORDER_STUDENT, PrintSettings((0, 0), (0, 0), False, "black", "off"))
    pages = printing.build_pages(conn, exam, ORDER_STUDENT)
    index = next(i for i, p in enumerate(pages) if p.student_id == sid and p.page == page_no)
    pix = pymupdf.open(path)[index].get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
    ink = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width) < 128
    x1, y1, x2, y2 = got
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    left_edge = ink[round((cy - 1) * K):round((cy + 1) * K), round((x1 - 1) * K):round((x1 + 1) * K)]
    top_edge = ink[round((y1 - 1) * K):round((y1 + 1) * K), round((cx - 1) * K):round((cx + 1) * K)]
    centre = ink[round((cy - 2) * K):round((cy + 2) * K), round((cx - 5) * K):round((cx + 5) * K)]
    assert left_edge.any() and top_edge.any() and not centre.any()

    page._undo_annotation()
    assert AnnotationStore(conn).for_student(exam, sid) == [] and not view._marks
