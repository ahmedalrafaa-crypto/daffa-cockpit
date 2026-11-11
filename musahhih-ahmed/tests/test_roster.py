import pytest

from musahhih.core.errors import AppError
from musahhih.core.roster import COMMON_GRADES, clean_name, name_key


def test_name_cleaning_and_key():
    assert clean_name("  أحمــد   محمد \n علي ") == "أحمد محمد علي"
    assert name_key("أَحْمَد إبراهيم فاطمة") == name_key("احمد ابراهيم فاطمه")


def test_grades_crud_and_order(roster):
    a = roster.add_grade("الأول المتوسط")
    b = roster.add_grade("الثاني المتوسط")
    with pytest.raises(AppError):
        roster.add_grade(" الاول المتوسط ")
    with pytest.raises(AppError):
        roster.add_grade("   ")
    roster.move_grade(b, -1)
    assert [g.id for g in roster.list_grades()] == [b, a]
    roster.move_grade(b, -1)  # في القمة أصلاً: لا تغيير
    assert [g.id for g in roster.list_grades()] == [b, a]
    roster.rename_grade(a, "الثالث المتوسط")
    with pytest.raises(AppError):
        roster.rename_grade(a, "الثاني المتوسط")
    roster.delete_grade(a)
    assert [g.name for g in roster.list_grades()] == ["الثاني المتوسط"]


def test_sections_and_delete_protection(roster):
    g = roster.add_grade("الخامس العلمي")
    s = roster.add_section(g, "أ")
    roster.add_section(g, "ب")
    with pytest.raises(AppError):
        roster.add_section(g, "أ")
    other = roster.add_grade("الرابع العلمي")
    roster.add_section(other, "أ")  # الاسم نفسه مسموح في صف آخر
    student = roster.add_student(s, "علي حسن")
    with pytest.raises(AppError):
        roster.delete_grade(g)
    with pytest.raises(AppError):
        roster.delete_section(s)
    roster.delete_students([student])
    roster.delete_section(s)
    assert [x.name for x in roster.list_sections(g)] == ["ب"]
    assert roster.list_grades()[0].section_count == 1


def test_student_ids_are_unique_and_never_reused(roster, section):
    first = roster.add_student(section, "علي حسن")
    second = roster.add_student(section, "حسين كاظم")
    roster.delete_students([second])
    third = roster.add_student(section, "مصطفى جواد")
    assert len({first, second, third}) == 3 and third > second
    assert roster.list_students(section)[0].code == f"{first:05d}"


def test_duplicates_rename_search_sort(roster, section):
    roster.add_student(section, "محمد علي")
    with pytest.raises(AppError):
        roster.add_student(section, "محمد  علي")
    roster.add_student(section, "محمد علي", allow_duplicate=True)
    sid = roster.add_student(section, "أحمد كريم")
    assert [s.full_name for s in roster.list_students(section)] == ["أحمد كريم", "محمد علي", "محمد علي"]
    roster.rename_student(sid, "إبراهيم كريم")
    assert [s.full_name for s in roster.list_students(section, "ابراهيم")] == ["إبراهيم كريم"]
    assert [s.id for s in roster.list_students(section, f"{sid:05d}")] == [sid]
    with pytest.raises(AppError):
        roster.rename_student(sid, "")
    assert roster.totals() == (1, 1, 3)


def test_common_grades_added_once(roster):
    roster.add_grade("الأول المتوسط")
    assert roster.add_common_grades() == len(COMMON_GRADES) - 1
    assert roster.add_common_grades() == 0
    grades = {g.name: g for g in roster.list_grades()}
    assert grades["السادس العلمي"].section_count == 1
    assert grades["الأول المتوسط"].section_count == 0  # صف المستخدم لا يُمَس
