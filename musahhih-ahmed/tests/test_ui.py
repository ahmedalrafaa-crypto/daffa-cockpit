"""اختبار دخاني للواجهة: تُبنى النافذة وتعرض البيانات الحقيقية من القاعدة."""
import pytest
from PySide6.QtWidgets import QApplication

from musahhih.app import create_app
from musahhih.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app(qapp):
    return qapp


def test_navigation_and_live_data(app, conn, roster, section, tmp_path, monkeypatch):
    monkeypatch.setenv("MUSAHHIH_DATA", str(tmp_path))
    roster.add_students(section, ["زينب حسن", "أحمد كريم"])
    window = MainWindow(conn)
    assert [n.text() for n in window.home.numbers] == ["1", "1", "2"]

    window.show_page(1)
    assert window.classes.grades.count() == 1 and window.classes.sections.count() == 1
    window.classes._open_students()
    assert window.stack.currentWidget() is window.students
    assert window.students.section_id() == section
    table = window.students.table
    assert [table.item(r, 2).text() for r in range(table.rowCount())] == ["أحمد كريم", "زينب حسن"]

    window.students.search.setText("زينب")
    assert table.rowCount() == 1
    assert not window.students.rename_button.isEnabled()
    table.setCurrentCell(0, 2)
    assert window.students.rename_button.isEnabled() and window.students.delete_button.isEnabled()


def test_empty_database_disables_actions(app, conn, tmp_path, monkeypatch):
    monkeypatch.setenv("MUSAHHIH_DATA", str(tmp_path))
    window = MainWindow(conn)
    window.show_page(2)
    assert not window.students.add_button.isEnabled()
    assert not window.students.import_button.isEnabled()
    window.show_page(1)
    assert not window.classes.section_add.isEnabled()


def test_exam_editor_flow(qapp, conn, data_dir, store, exam):
    window = MainWindow(conn)
    window.show_page(3)
    assert window.exams.table.rowCount() == 1
    window._open_exam(exam)
    editor = window.editor
    assert window.stack.currentWidget() is editor
    assert editor.tree.topLevelItemCount() == 2 and editor.tree.topLevelItem(0).childCount() == 2
    assert "25 من 25" in editor.sum_label.text() and "✓" in editor.sum_label.text()
    assert editor.add_part.isEnabled() and not editor.approve.isHidden() and editor.open_sheets.isHidden()

    from musahhih.sheet import workflow
    workflow.approve(store, window.roster, exam)
    editor.refresh()
    assert not editor.add_question.isEnabled() and not editor.delete.isEnabled()
    assert editor.approve.isHidden() and not editor.open_sheets.isHidden() and not editor.alignment.isHidden()
    window.show_page(3)
    assert window.exams.table.item(0, 5).text() == "معتمد"


def test_scan_page_lists_only_approved_exams(qapp, conn, data_dir, store, exam):
    window = MainWindow(conn)
    window.show_page(5)
    assert window.scan.exam.count() == 0 and not window.scan.import_button.isEnabled()
    from musahhih.sheet import workflow
    workflow.approve(store, window.roster, exam)
    window.scan.select_exam(exam)
    assert window.scan.exam.count() == 1 and window.scan.import_button.isEnabled()
    assert "الأوراق المستوردة: 0" in window.scan.summary.text()
