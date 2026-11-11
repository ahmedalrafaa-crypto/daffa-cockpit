"""صفحة إدارة طلاب الشعبة مع الاستيراد والتصدير."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core import excel_io
from ..core.errors import AppError
from ..core.roster import Roster, clean_name
from . import dialogs

EXCEL_FILTER = "ملفات Excel (*.xlsx)"


class StudentsPage(QWidget):
    def __init__(self, roster: Roster):
        super().__init__()
        self.setObjectName("page")
        self.roster = roster
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        title = QLabel("إدارة الطلاب")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(QLabel("الصف:"))
        self.grade_box = QComboBox()
        self.grade_box.setMinimumWidth(190)
        self.grade_box.currentIndexChanged.connect(lambda *_: self._load_sections())
        top.addWidget(self.grade_box)
        top.addWidget(QLabel("الشعبة:"))
        self.section_box = QComboBox()
        self.section_box.setMinimumWidth(120)
        self.section_box.currentIndexChanged.connect(lambda *_: self._load_students())
        top.addWidget(self.section_box)
        top.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("بحث بالاسم أو الرقم التعريفي")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(260)
        self.search.textChanged.connect(lambda *_: self._load_students())
        top.addWidget(self.search)
        root.addLayout(top)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ت", "الرقم التعريفي", "اسم الطالب"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda *_: self._rename())
        root.addWidget(self.table, 1)

        self.status = QLabel()
        self.status.setObjectName("pageHint")
        root.addWidget(self.status)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.add_button = QPushButton("إضافة طالب")
        self.add_button.setObjectName("primary")
        self.add_button.clicked.connect(self._add)
        self.rename_button = QPushButton("تعديل الاسم")
        self.rename_button.clicked.connect(self._rename)
        self.delete_button = QPushButton("حذف")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self._delete)
        self.import_button = QPushButton("استيراد من Excel")
        self.import_button.clicked.connect(self._import)
        self.export_button = QPushButton("تصدير إلى Excel")
        self.export_button.clicked.connect(self._export)
        for b in (self.add_button, self.rename_button, self.delete_button):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(self.import_button)
        row.addWidget(self.export_button)
        root.addLayout(row)

    # ---------- تحميل ----------
    def refresh(self) -> None:
        self._load_grades(self.section_id())

    def show_section(self, section_id: int) -> None:
        self.search.clear()
        self._load_grades(section_id)

    def section_id(self) -> int | None:
        return self.section_box.currentData()

    def _load_grades(self, select_section: int | None = None) -> None:
        grade_id = self.grade_box.currentData()
        if select_section is not None:
            try:
                grade_id = self.roster.get_section(select_section)[0].grade_id
            except AppError:
                select_section = None
        self.grade_box.blockSignals(True)
        self.grade_box.clear()
        for g in self.roster.list_grades():
            self.grade_box.addItem(g.name, g.id)
        index = self.grade_box.findData(grade_id)
        if index >= 0:
            self.grade_box.setCurrentIndex(index)
        self.grade_box.blockSignals(False)
        self._load_sections(select_section)

    def _load_sections(self, select_section: int | None = None) -> None:
        self.section_box.blockSignals(True)
        self.section_box.clear()
        grade_id = self.grade_box.currentData()
        if grade_id is not None:
            for s in self.roster.list_sections(grade_id):
                self.section_box.addItem(s.name, s.id)
        index = self.section_box.findData(select_section)
        if index >= 0:
            self.section_box.setCurrentIndex(index)
        self.section_box.blockSignals(False)
        self._load_students()

    def _load_students(self) -> None:
        section_id = self.section_id()
        students = self.roster.list_students(section_id, self.search.text()) if section_id is not None else []
        self.table.setRowCount(len(students))
        for r, s in enumerate(students):
            cells = (str(r + 1), s.code, s.full_name)
            for c, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, s.id)
                if c < 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, c, item)
        if self.grade_box.count() == 0:
            self.status.setText("لا توجد صفوف بعد. أضف الصفوف والشعب أولاً من صفحة «الصفوف والشعب».")
        elif section_id is None:
            self.status.setText("لا توجد شعب في هذا الصف. أضف شعبة من صفحة «الصفوف والشعب».")
        elif self.search.text().strip():
            self.status.setText(f"نتائج البحث: {len(students)}")
        else:
            self.status.setText(f"عدد طلاب الشعبة: {len(students)}")
        self._update_buttons()

    def _selected_ids(self) -> list[int]:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows]

    def _update_buttons(self) -> None:
        has_section = self.section_id() is not None
        count = len(self._selected_ids())
        self.add_button.setEnabled(has_section)
        self.import_button.setEnabled(has_section)
        self.export_button.setEnabled(has_section and self.table.rowCount() > 0)
        self.rename_button.setEnabled(count == 1)
        self.delete_button.setEnabled(count >= 1)

    # ---------- العمليات ----------
    def _add(self) -> None:
        section_id = self.section_id()
        name = dialogs.ask_text(self, "إضافة طالب", "اسم الطالب الكامل:")
        if name is None:
            return
        try:
            duplicate = bool(clean_name(name)) and self.roster.student_exists(section_id, name)
            if duplicate and not dialogs.confirm(
                self, f"يوجد طالب بالاسم «{clean_name(name)}» في هذه الشعبة.\nهل تريد إضافة طالب آخر بالاسم نفسه؟",
                yes="إضافة",
            ):
                return
            self.roster.add_student(section_id, name, allow_duplicate=duplicate)
        except AppError as exc:
            dialogs.error(self, str(exc))
            return
        self._load_students()

    def _rename(self) -> None:
        ids = self._selected_ids()
        if len(ids) != 1:
            return
        current = self.table.item(self.table.currentRow(), 2).text()
        name = dialogs.ask_text(self, "تعديل اسم الطالب", "اسم الطالب الكامل:", current)
        if name is None:
            return
        try:
            self.roster.rename_student(ids[0], name)
        except AppError as exc:
            dialogs.error(self, str(exc))
            return
        self._load_students()

    def _delete(self) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        if len(ids) == 1:
            name = self.table.item(self.table.selectedIndexes()[0].row(), 2).text()
            question = f"هل تريد حذف الطالب «{name}»؟"
        else:
            question = f"هل تريد حذف {len(ids)} طلاب؟"
        if dialogs.confirm(self, question + "\nلا يمكن التراجع عن الحذف.", yes="حذف"):
            self.roster.delete_students(ids)
            self._load_students()

    def _import(self) -> None:
        section_id = self.section_id()
        path, _ = QFileDialog.getOpenFileName(self, "اختيار ملف الطلاب", "", "ملفات Excel (*.xlsx *.xls)")
        if not path:
            return
        try:
            names = excel_io.read_names(path)
            preview = "، ".join(names[:3]) + (" …" if len(names) > 3 else "")
            section, grade_name = self.roster.get_section(section_id)
            if not dialogs.confirm(
                self,
                f"عُثر على {len(names)} اسماً في الملف:\n{preview}\n\n"
                f"هل تريد إضافتهم إلى {grade_name} / شعبة {section.name}؟",
                yes="استيراد",
            ):
                return
            report = excel_io.import_students(self.roster, section_id, names)
        except AppError as exc:
            dialogs.error(self, str(exc))
            return
        self.search.clear()
        self._load_students()
        message = f"تمت إضافة {report.added} طالباً."
        if report.duplicates:
            message += f"\nتم تخطي {report.duplicates} اسماً لأنه موجود مسبقاً أو مكرر في الملف."
        dialogs.info(self, message)

    def _export(self) -> None:
        section_id = self.section_id()
        section, grade_name = self.roster.get_section(section_id)
        default = f"طلاب {grade_name} - {section.name}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "حفظ قائمة الطلاب", default, EXCEL_FILTER)
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            count = excel_io.export_students(self.roster, section_id, path)
        except AppError as exc:
            dialogs.error(self, str(exc))
            return
        dialogs.info(self, f"تم تصدير {count} طالباً إلى:\n{path}")
