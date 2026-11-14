import pytest

from musahhih.core import exam_package
from musahhih.core.errors import AppError
from musahhih.core.roster import Roster
from musahhih.sheet import workflow


def _exam(store, section, **kw):
    exam_id = store.create_exam("x", "م", section, "2026-01-01", 50, **kw)
    for _ in range(2):
        q = store.add_question(exam_id)
        store.add_part(q, "أسئلة كلامية\n١. علّل\n٢. عرّف", 10, 25)
        store.add_part(q, "مسألة\nنص\n١. احسب", 15, 25)
    return exam_id


def test_fixed_part_keeps_its_lines_in_page_per_question(qapp, data_dir, store, section):
    exam_id = _exam(store, section, questions_per_page=1)
    q1 = store.questions(exam_id)[0]
    a, b = q1.parts
    _, auto = workflow.layout_info(store, exam_id)
    store.set_answer_lines({a.id: (9, True)})
    pages, fixed = workflow.layout_info(store, exam_id)
    assert fixed[a.id] == 9                                   # الثابت كما كُتب
    assert fixed[b.id] < auto[b.id]                           # والمساحة الباقية ذهبت للفرع الآخر
    assert pages == 2
    # فرع غير ثابت: الرقم حد أقصى فقط، والبرنامج يملأ المساحة
    store.set_answer_lines({a.id: (9, False)})
    assert workflow.layout_info(store, exam_id)[1][a.id] == auto[a.id]


def test_fixed_part_is_not_shrunk_by_target_pages(qapp, data_dir, store, section):
    exam_id = _exam(store, section, target_pages=1)
    q1 = store.questions(exam_id)[0]
    a = q1.parts[0]
    store.set_answer_lines({a.id: (6, True)})
    pages, lines = workflow.layout_info(store, exam_id)
    assert pages == 1 and lines[a.id] == 6
    others = [v for pid, v in lines.items() if pid != a.id]
    assert all(v < 25 for v in others)                        # الباقي صُغّر ليتسع في صفحة
    # ثابت أكبر من المساحة: رسالة واضحة
    store.set_answer_lines({p.id: (25, True) for q in store.questions(exam_id) for p in q.parts})
    with pytest.raises(AppError, match="لا يتسع"):
        workflow.layout_info(store, exam_id)


def test_set_answer_lines_validation_and_lock(qapp, data_dir, store, section, conn):
    exam_id = _exam(store, section)
    part = store.questions(exam_id)[0].parts[0]
    with pytest.raises(AppError):
        store.set_answer_lines({part.id: (99, False)})
    store.set_answer_lines({part.id: (4, True)})
    p = store.questions(exam_id)[0].parts[0]
    assert (p.answer_lines, p.lines_fixed) == (4, True)
    # تعديل نص الفرع لا يلغي «ثابت» ما لم يُمرَّر صراحة
    store.update_part(p.id, "نص جديد", 10, 4, None)
    assert store.questions(exam_id)[0].parts[0].lines_fixed
    data = exam_package.from_store(store, exam_id)
    assert data["questions"][0]["parts"][0]["lines_fixed"] is True
    copy = exam_package.import_exam(store, data, section, "2026-01-01")
    assert store.questions(copy)[0].parts[0].lines_fixed
    Roster(conn).add_student(section, "طالبة")
    workflow.approve(store, Roster(conn), exam_id)
    with pytest.raises(AppError):
        store.set_answer_lines({p.id: (3, False)})


def test_lines_dialog(qapp, data_dir, store, section, conn):
    from musahhih.ui.exam_dialogs import LinesDialog
    exam_id = _exam(store, section, questions_per_page=1)
    dialog = LinesDialog(None, store, exam_id, workflow.layout_info)
    assert dialog.table.rowCount() == 4 and dialog.table.columnCount() == 4
    assert "2" in dialog.pages.text()
    pid, spin, box = dialog.rows[0]
    spin.setValue(7)
    box.setChecked(True)
    assert dialog.apply()
    assert dialog.table.item(0, 2).text() == "7"
    p = store.questions(exam_id)[0].parts[0]
    assert (p.answer_lines, p.lines_fixed) == (7, True)
    plain = _exam(store, section)
    assert LinesDialog(None, store, plain, workflow.layout_info).table.columnCount() == 3   # بلا عمود «ثابت»


def test_lines_dialog_fill_mode_enables_number_only_when_fixed(qapp, data_dir, store, section):
    from musahhih.ui.exam_dialogs import LinesDialog
    exam_id = _exam(store, section, questions_per_page=1)
    dialog = LinesDialog(None, store, exam_id, workflow.layout_info)
    _, spin, box = dialog.rows[1]
    assert not spin.isEnabled()
    box.setChecked(True)
    assert spin.isEnabled()
    target_only = _exam(store, section, target_pages=2)
    other = LinesDialog(None, store, target_only, workflow.layout_info)
    assert other.rows[0][1].isEnabled()                    # هنا الرقم حد أقصى فيبقى قابلاً للتعديل
