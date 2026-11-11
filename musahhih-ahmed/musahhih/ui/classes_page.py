"""صفحة الصفوف والشعب."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from ..core.errors import AppError
from ..core.roster import Roster
from . import dialogs


def _button(text: str, slot, name: str = "") -> QPushButton:
    button = QPushButton(text)
    if name:
        button.setObjectName(name)
    button.clicked.connect(slot)
    # حد أدنى للعرض حتى لا يُقصّ نص الزر في النوافذ الصغيرة (15% احتياطاً للخط العريض)
    padding = 22 if name == "icon" else 36
    button.setMinimumWidth(int(button.fontMetrics().horizontalAdvance(text) * 1.15) + padding)
    return button


class ClassesPage(QWidget):
    open_section = Signal(int)

    def __init__(self, roster: Roster):
        super().__init__()
        self.setObjectName("page")
        self.roster = roster
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        title = QLabel("الصفوف والشعب")
        title.setObjectName("pageTitle")
        self.common = _button("إضافة الصفوف الشائعة", self._add_common)
        self.common.setToolTip("يضيف صفوف المتوسطة والإعدادية العلمي مع شعبها، ويمكنك تعديلها بعد ذلك")
        top = QHBoxLayout()
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.common)
        root.addLayout(top)

        panels = QHBoxLayout()
        panels.setSpacing(20)
        root.addLayout(panels, 1)

        # --- الصفوف ---
        left = QVBoxLayout()
        head = QLabel("الصفوف الدراسية")
        head.setObjectName("panelTitle")
        left.addWidget(head)
        self.grades = QListWidget()
        self.grades.setAlternatingRowColors(True)
        self.grades.currentItemChanged.connect(lambda *_: self._load_sections())
        self.grades.itemDoubleClicked.connect(lambda *_: self._rename_grade())
        left.addWidget(self.grades, 1)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_button("إضافة صف", self._add_grade, "primary"))
        self.grade_rename = _button("تعديل", self._rename_grade)
        self.grade_up = _button("▲", lambda: self._move_grade(-1), "icon")
        self.grade_down = _button("▼", lambda: self._move_grade(1), "icon")
        self.grade_up.setToolTip("تحريك الصف للأعلى")
        self.grade_down.setToolTip("تحريك الصف للأسفل")
        self.grade_delete = _button("حذف", self._delete_grade, "danger")
        for b in (self.grade_rename, self.grade_up, self.grade_down, self.grade_delete):
            row.addWidget(b)
        row.addStretch()
        left.addLayout(row)
        panels.addLayout(left, 1)

        # --- الشعب ---
        right = QVBoxLayout()
        self.sections_title = QLabel("الشعب")
        self.sections_title.setObjectName("panelTitle")
        right.addWidget(self.sections_title)
        self.sections = QListWidget()
        self.sections.setAlternatingRowColors(True)
        self.sections.currentItemChanged.connect(lambda *_: self._update_buttons())
        self.sections.itemDoubleClicked.connect(lambda *_: self._open_students())
        right.addWidget(self.sections, 1)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.section_add = _button("إضافة شعبة", self._add_section, "primary")
        self.section_rename = _button("تعديل", self._rename_section)
        self.section_students = _button("الطلاب", self._open_students)
        self.section_delete = _button("حذف", self._delete_section, "danger")
        for b in (self.section_add, self.section_rename, self.section_students, self.section_delete):
            row.addWidget(b)
        row.addStretch()
        right.addLayout(row)
        panels.addLayout(right, 1)

    # ---------- تحميل ----------
    def refresh(self) -> None:
        self._load_grades(self._grade_id())

    def _grade_id(self) -> int | None:
        item = self.grades.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _section_id(self) -> int | None:
        item = self.sections.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _load_grades(self, select_id: int | None = None) -> None:
        self.grades.blockSignals(True)
        self.grades.clear()
        for g in self.roster.list_grades():
            item = QListWidgetItem(f"{g.name}   ·   الشعب: {g.section_count}   ·   الطلاب: {g.student_count}")
            item.setData(Qt.ItemDataRole.UserRole, g.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, g.name)
            self.grades.addItem(item)
            if g.id == select_id:
                self.grades.setCurrentItem(item)
        if self.grades.currentItem() is None and self.grades.count():
            self.grades.setCurrentRow(0)
        self.grades.blockSignals(False)
        self._load_sections()

    def _load_sections(self, select_id: int | None = None) -> None:
        select_id = select_id or self._section_id()
        self.sections.blockSignals(True)
        self.sections.clear()
        grade_item = self.grades.currentItem()
        if grade_item:
            self.sections_title.setText(f"شعب {grade_item.data(Qt.ItemDataRole.UserRole + 1)}")
            for s in self.roster.list_sections(self._grade_id()):
                item = QListWidgetItem(f"شعبة {s.name}   ·   الطلاب: {s.student_count}")
                item.setData(Qt.ItemDataRole.UserRole, s.id)
                item.setData(Qt.ItemDataRole.UserRole + 1, s.name)
                self.sections.addItem(item)
                if s.id == select_id:
                    self.sections.setCurrentItem(item)
            if self.sections.currentItem() is None and self.sections.count():
                self.sections.setCurrentRow(0)
        else:
            self.sections_title.setText("الشعب")
        self.sections.blockSignals(False)
        self._update_buttons()

    def _update_buttons(self) -> None:
        has_grade = self.grades.currentItem() is not None
        has_section = self.sections.currentItem() is not None
        for b in (self.grade_rename, self.grade_up, self.grade_down, self.grade_delete, self.section_add):
            b.setEnabled(has_grade)
        for b in (self.section_rename, self.section_students, self.section_delete):
            b.setEnabled(has_section)

    def _run(self, action) -> bool:
        try:
            action()
            return True
        except AppError as exc:
            dialogs.error(self, str(exc))
            return False

    # ---------- الصفوف ----------
    def _add_grade(self) -> None:
        name = dialogs.ask_text(self, "إضافة صف", "اسم الصف (مثال: الرابع العلمي):")
        if name is None:
            return
        new_id: list[int] = []
        if self._run(lambda: new_id.append(self.roster.add_grade(name))):
            self._load_grades(new_id[0])

    def _rename_grade(self) -> None:
        item = self.grades.currentItem()
        if not item:
            return
        name = dialogs.ask_text(self, "تعديل اسم الصف", "اسم الصف:", item.data(Qt.ItemDataRole.UserRole + 1))
        if name is not None and self._run(lambda: self.roster.rename_grade(self._grade_id(), name)):
            self._load_grades(self._grade_id())

    def _move_grade(self, step: int) -> None:
        grade_id = self._grade_id()
        if grade_id is not None:
            self.roster.move_grade(grade_id, step)
            self._load_grades(grade_id)

    def _delete_grade(self) -> None:
        item = self.grades.currentItem()
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole + 1)
        if dialogs.confirm(self, f"هل تريد حذف الصف «{name}»؟", yes="حذف"):
            if self._run(lambda: self.roster.delete_grade(self._grade_id())):
                self._load_grades()

    def _add_common(self) -> None:
        added = self.roster.add_common_grades()
        self._load_grades(self._grade_id())
        if added:
            dialogs.info(self, f"أضيف {added} من الصفوف مع شعبها. يمكنك تعديلها أو حذفها بحرية.")
        else:
            dialogs.info(self, "الصفوف الشائعة موجودة كلها مسبقاً.")

    # ---------- الشعب ----------
    def _add_section(self) -> None:
        name = dialogs.ask_text(self, "إضافة شعبة", "اسم الشعبة (مثال: أ):")
        if name is None:
            return
        new_id: list[int] = []
        if self._run(lambda: new_id.append(self.roster.add_section(self._grade_id(), name))):
            grade_id = self._grade_id()
            self._load_grades(grade_id)
            self._load_sections(new_id[0])

    def _rename_section(self) -> None:
        item = self.sections.currentItem()
        if not item:
            return
        name = dialogs.ask_text(self, "تعديل اسم الشعبة", "اسم الشعبة:", item.data(Qt.ItemDataRole.UserRole + 1))
        if name is not None and self._run(lambda: self.roster.rename_section(self._section_id(), name)):
            self._load_sections()

    def _delete_section(self) -> None:
        item = self.sections.currentItem()
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole + 1)
        if dialogs.confirm(self, f"هل تريد حذف الشعبة «{name}»؟", yes="حذف"):
            if self._run(lambda: self.roster.delete_section(self._section_id())):
                self._load_grades(self._grade_id())

    def _open_students(self) -> None:
        section_id = self._section_id()
        if section_id is not None:
            self.open_section.emit(section_id)
