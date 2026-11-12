"""صفحة الامتحانات: القائمة، وإنشاء امتحان جديد."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..core import exam_package
from ..core.errors import AppError
from ..core.exams import ExamStore, format_marks
from ..core.roster import Roster
from ..core.settings import Settings
from . import dialogs
from .exam_dialogs import ExamDialog

SCHOOL_KEY = "school_name"


def ui_date(iso: str) -> str:
    parts = iso.split("-")
    return f"{parts[2]}/{parts[1]}/{parts[0]}" if len(parts) == 3 else iso


class ExamsPage(QWidget):
    open_exam = Signal(int)

    def __init__(self, store: ExamStore, roster: Roster, settings: Settings):
        super().__init__()
        self.setObjectName("page")
        self.store, self.roster, self.settings = store, roster, settings
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        top = QHBoxLayout()
        title = QLabel("الامتحانات")
        title.setObjectName("pageTitle")
        new = QPushButton("إنشاء امتحان جديد")
        new.setObjectName("primary")
        new.clicked.connect(self.new_exam)
        ready = QPushButton("استيراد امتحان جاهز")
        ready.clicked.connect(self.import_ready)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(ready)
        top.addWidget(new)
        root.addLayout(top)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["الامتحان", "المادة", "الصف والشعبة", "التاريخ", "الدرجة", "الحالة"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda *_: self._open())
        root.addWidget(self.table, 1)

        self.status = QLabel()
        self.status.setObjectName("pageHint")
        root.addWidget(self.status)
        row = QHBoxLayout()
        self.open_button = QPushButton("فتح الامتحان")
        self.open_button.setObjectName("primary")
        self.open_button.clicked.connect(self._open)
        self.delete_button = QPushButton("حذف")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self._delete)
        row.addWidget(self.open_button)
        row.addWidget(self.delete_button)
        row.addStretch()
        root.addLayout(row)

    def refresh(self) -> None:
        exams = self.store.list_exams()
        self.table.setRowCount(len(exams))
        for r, e in enumerate(exams):
            cells = (e.name, e.subject, f"{e.grade_name} / {e.section_name}", ui_date(e.exam_date),
                     format_marks(e.total_marks), "معتمد" if e.approved else "مسودة")
            for c, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, e.id)
                if c >= 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, c, item)
        self.status.setText("" if exams else "لا توجد امتحانات بعد. اضغط «إنشاء امتحان جديد» للبدء.")
        self._update_buttons()

    def _selected(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.selectedIndexes():
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _update_buttons(self) -> None:
        selected = self._selected() is not None
        self.open_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)

    def new_exam(self) -> None:
        if not any(g.section_count for g in self.roster.list_grades()):
            dialogs.error(self, "أضف صفاً وشعبة واحدة على الأقل قبل إنشاء امتحان.")
            return
        dialog = ExamDialog(self, self.roster, school_name=self.settings.get(SCHOOL_KEY))
        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                exam_id = self.store.create_exam(**dialog.values(), question_count=dialog.count.value())
            except AppError as exc:
                dialogs.error(self, str(exc))
                continue
            self.settings.set(SCHOOL_KEY, dialog.school.text().strip())
            self.open_exam.emit(exam_id)
            return

    def import_ready(self) -> None:
        """استيراد ملف امتحان جاهز (.mexam): تُراجع بياناته وتختار الشعبة ثم يُنشأ مسودة للمراجعة."""
        if not any(g.section_count for g in self.roster.list_grades()):
            dialogs.error(self, "أضف صفاً وشعبة واحدة على الأقل قبل استيراد امتحان.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "اختيار ملف الامتحان", "", "ملف امتحان جاهز (*.mexam)")
        if not path:
            return
        try:
            data = exam_package.read(path)
        except AppError as exc:
            dialogs.error(self, str(exc))
            return
        dialog = ExamDialog(self, self.roster, school_name=self.settings.get(SCHOOL_KEY), defaults=data)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                exam_id = exam_package.import_exam(self.store, data, **dialog.values())
            except AppError as exc:
                dialogs.error(self, str(exc))
                continue
            self.settings.set(SCHOOL_KEY, dialog.school.text().strip())
            self.open_exam.emit(exam_id)
            return

    def _open(self) -> None:
        exam_id = self._selected()
        if exam_id is not None:
            self.open_exam.emit(exam_id)

    def _delete(self) -> None:
        exam_id = self._selected()
        if exam_id is None:
            return
        name = self.table.item(self.table.currentRow(), 0).text()
        if not dialogs.confirm(self, f"هل تريد حذف الامتحان «{name}» مع أسئلته؟\nلا يمكن التراجع عن الحذف.", yes="حذف"):
            return
        try:
            self.store.delete_exam(exam_id)
        except AppError as exc:
            dialogs.error(self, str(exc))
        self.refresh()
