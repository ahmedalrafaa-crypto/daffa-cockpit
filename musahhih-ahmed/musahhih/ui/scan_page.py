"""صفحة استيراد أوراق الإجابة الممسوحة ومراجعتها."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QProgressDialog, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.errors import AppError
from ..core.exams import ExamStore
from ..core.scans import DUPLICATE, MATCHED, UNKNOWN, ScanStore
from ..scan import importer
from . import dialogs

STATUS_TEXT = {MATCHED: "مطابقة", DUPLICATE: "مكررة", UNKNOWN: "غير معروفة"}


class AssignDialog(QDialog):
    def __init__(self, parent, students, page_count: int):
        super().__init__(parent)
        self.setWindowTitle("تعيين الورقة لطالب")
        form = QFormLayout()
        self.student = QComboBox()
        for s in students:
            self.student.addItem(s.full_name, s.student_id)
        self.page = QSpinBox()
        self.page.setRange(1, max(page_count, 1))
        form.addRow("الطالب:", self.student)
        form.addRow("رقم الصفحة:", self.page)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        box = QDialogButtonBox()
        box.addButton("تعيين", QDialogButtonBox.ButtonRole.AcceptRole).setObjectName("primary")
        box.addButton("إلغاء", QDialogButtonBox.ButtonRole.RejectRole)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)


class ViewDialog(QDialog):
    def __init__(self, parent, path: Path, title: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        label = QLabel()
        label.setPixmap(QPixmap(str(path)).scaledToHeight(820, Qt.TransformationMode.SmoothTransformation))
        layout = QVBoxLayout(self)
        layout.addWidget(label)


class ScanPage(QWidget):
    def __init__(self, store: ExamStore, scans: ScanStore):
        super().__init__()
        self.setObjectName("page")
        self.store, self.scans = store, scans
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)
        title = QLabel("استيراد أوراق الإجابة")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        top = QHBoxLayout()
        top.addWidget(QLabel("الامتحان:"))
        self.exam = QComboBox()
        self.exam.setMinimumWidth(320)
        self.exam.currentIndexChanged.connect(lambda *_: self._load())
        top.addWidget(self.exam)
        top.addStretch()
        self.import_button = QPushButton("استيراد ملفات المسح (PDF أو صور)")
        self.import_button.setObjectName("primary")
        self.import_button.clicked.connect(self._import)
        top.addWidget(self.import_button)
        root.addLayout(top)

        self.summary = QLabel()
        self.summary.setObjectName("pageHint")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["الحالة", "الطالب", "الصفحة", "المصدر", "ملاحظة"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda *_: self._view())
        root.addWidget(self.table, 1)

        self.missing = QLabel()
        self.missing.setObjectName("pageHint")
        self.missing.setWordWrap(True)
        root.addWidget(self.missing)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.view_button = QPushButton("عرض الورقة")
        self.view_button.clicked.connect(self._view)
        self.assign_button = QPushButton("تعيين لطالب")
        self.assign_button.clicked.connect(self._assign)
        self.promote_button = QPushButton("اعتماد المكررة بدل الأصل")
        self.promote_button.clicked.connect(self._promote)
        self.delete_button = QPushButton("حذف الورقة")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self._delete)
        self.confirm_button = QPushButton("تأكيد اكتمال الاستيراد")
        self.confirm_button.setObjectName("primary")
        self.confirm_button.clicked.connect(self._confirm)
        for b in (self.view_button, self.assign_button, self.promote_button, self.delete_button):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(self.confirm_button)
        root.addLayout(row)

    def refresh(self) -> None:
        current = self.exam.currentData()
        self.exam.blockSignals(True)
        self.exam.clear()
        for e in self.store.list_exams():
            if e.approved:
                self.exam.addItem(f"{e.name} — {e.subject} ({e.grade_name} / {e.section_name})", e.id)
        index = self.exam.findData(current)
        self.exam.setCurrentIndex(max(index, 0))
        self.exam.blockSignals(False)
        self._load()

    def select_exam(self, exam_id: int) -> None:
        self.refresh()
        index = self.exam.findData(exam_id)
        if index >= 0:
            self.exam.setCurrentIndex(index)

    def _exam_id(self) -> int | None:
        return self.exam.currentData()

    def _selected(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.selectedIndexes():
            return None
        return self.scans.get(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))

    def _load(self) -> None:
        exam_id = self._exam_id()
        self.table.setRowCount(0)
        if exam_id is None:
            self.summary.setText("لا توجد امتحانات معتمدة. اعتمد امتحاناً أولاً من صفحة «الامتحانات».")
            self.missing.setText("")
            self._update_buttons()
            return
        names = {s.student_id: s.full_name for s in self.store.exam_students(exam_id)}
        pages = self.scans.pages(exam_id)
        review = [p for p in pages if p.status != MATCHED or not p.aligned]
        self.table.setRowCount(len(review))
        for r, p in enumerate(review):
            status = STATUS_TEXT[p.status] + ("" if p.aligned or p.status == UNKNOWN else " (غير مقوَّمة)")
            cells = (status, names.get(p.student_id, "—"), str(p.page or "—"), p.source, p.note)
            for c, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, p.id)
                self.table.setItem(r, c, item)
        s = self.scans.summary(exam_id)
        confirmed = "  ✓ تم تأكيد الاكتمال" if self.scans.is_confirmed(exam_id) else ""
        self.summary.setText(
            f"الأوراق المستوردة: {s.total}   ·   مطابقة: {s.matched}   ·   مكررة: {s.duplicate}   ·   "
            f"غير معروفة: {s.unknown}   ·   غير مقوَّمة: {s.misaligned}\n"
            f"الطلاب: {s.students}   ·   مكتملة أوراقهم: {s.complete}   ·   بلا أي ورقة: {s.absent}{confirmed}"
        )
        incomplete = [f"{r.full_name} (ناقص: {'، '.join(map(str, r.missing))})"
                      for r in self.scans.student_report(exam_id) if r.missing and r.present]
        absent = [r.full_name for r in self.scans.student_report(exam_id) if not r.present]
        parts = []
        if incomplete:
            parts.append("أوراق ناقصة: " + "؛ ".join(incomplete))
        if absent:
            parts.append("لم تُستورد لهم أوراق: " + "، ".join(absent))
        self.missing.setText("\n".join(parts))
        self._update_buttons()

    def _update_buttons(self) -> None:
        has_exam = self._exam_id() is not None
        scan = self._selected()
        self.import_button.setEnabled(has_exam)
        self.view_button.setEnabled(scan is not None)
        self.assign_button.setEnabled(scan is not None)
        self.promote_button.setEnabled(scan is not None and scan.status == DUPLICATE)
        self.delete_button.setEnabled(scan is not None)
        self.confirm_button.setEnabled(has_exam and self.scans.summary(self._exam_id()).total > 0)

    def _try(self, action) -> bool:
        try:
            action()
            return True
        except AppError as exc:
            dialogs.error(self, str(exc))
            return False

    def _import(self) -> None:
        exam_id = self._exam_id()
        files, _ = QFileDialog.getOpenFileNames(
            self, "اختيار ملفات المسح", "", "ملفات المسح (*.pdf *.jpg *.jpeg *.png *.tif *.tiff *.bmp)")
        if not files:
            return
        progress = QProgressDialog("جارٍ استيراد الأوراق…", "إيقاف", 0, 100, self)
        progress.setWindowTitle("استيراد الأوراق")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        def report(done: int, total: int) -> bool:
            progress.setMaximum(max(total, 1))
            progress.setValue(done)
            QApplication.processEvents()
            return not progress.wasCanceled()

        result: list = []
        ok = self._try(lambda: result.append(importer.import_files(self.scans, exam_id, files, report)))
        progress.close()
        self._load()
        if not ok:
            return
        r = result[0]
        lines = [f"استُوردت {r.pages} صفحة: {r.matched} مطابقة، {r.duplicate} مكررة، {r.unknown} غير معروفة."]
        if r.misaligned:
            lines.append(f"{r.misaligned} ورقة لم تُقوَّم بالعلامات المرجعية؛ راجعها في الجدول.")
        if r.cancelled:
            lines.append("أُوقف الاستيراد قبل اكتماله، والأوراق التي دخلت محفوظة.")
        if r.failed_files:
            lines.append("تعذر قراءة: " + "، ".join(r.failed_files))
        dialogs.info(self, "\n".join(lines))

    def _view(self) -> None:
        scan = self._selected()
        if scan:
            ViewDialog(self, scan.path, scan.source).exec()

    def _assign(self) -> None:
        scan = self._selected()
        if not scan:
            return
        exam_id = self._exam_id()
        dialog = AssignDialog(self, self.store.exam_students(exam_id), self.store.page_count(exam_id))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self._try(lambda: importer.assign_manually(self.scans, scan.id, dialog.student.currentData(),
                                                         dialog.page.value())):
                self._load()

    def _promote(self) -> None:
        scan = self._selected()
        if scan and self._try(lambda: self.scans.promote(scan.id)):
            self._load()

    def _delete(self) -> None:
        scan = self._selected()
        if scan and dialogs.confirm(self, "هل تريد حذف هذه الورقة وصورتها؟", yes="حذف"):
            if self._try(lambda: self.scans.delete(scan.id)):
                self._load()

    def _confirm(self) -> None:
        exam_id = self._exam_id()
        s = self.scans.summary(exam_id)
        if s.complete < s.students and not dialogs.confirm(
            self, f"{s.students - s.complete} طالباً أوراقهم ناقصة أو غائبة. هل تؤكد اكتمال الاستيراد على ذلك؟",
            yes="تأكيد",
        ):
            return
        if self._try(lambda: self.scans.confirm(exam_id)):
            self._load()
            dialogs.info(self, "تم تأكيد اكتمال الاستيراد. يمكن البدء بالتصحيح في المرحلة القادمة.")
