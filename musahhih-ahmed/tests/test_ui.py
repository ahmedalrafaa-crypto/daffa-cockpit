"""اختبار دخاني للواجهة: تُبنى النافذة وتعرض البيانات الحقيقية من القاعدة."""
import pytest
from PySide6.QtWidgets import QApplication

from musahhih.app import create_app
from musahhih.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or create_app([])


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
