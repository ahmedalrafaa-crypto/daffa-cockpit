"""صفحة سجل الدرجات: جدول النتائج، البحث والترتيب، التصدير إلى Excel والطباعة."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import paths
from ..core import results
from ..core.errors import AppError
from ..core.exams import ExamStore, format_marks, part_letter, question_title
from ..core.results_export import export_excel, status_text
from ..core.roster import Roster, format_student_code, name_key
from ..sheet.register_pdf import write_register_pdf
from . import dialogs

SORTS = [("أبجدياً", "name"), ("الدرجة: الأعلى أولاً", "high"), ("الدرجة: الأدنى أولاً", "low"),
         ("الرقم التعريفي", "code")]


class NumberItem(QTableWidgetItem):
    """خلية رقمية تُرتب بالقيمة لا بالنص، والفارغة («—») في الآخر."""

    def __init__(self, value: float | None):
        super().__init__("—" if value is None else format_marks(value))
        self.value = value
        self.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def __lt__(self, other):
        a = -1e9 if self.value is None else self.value
        b = -1e9 if getattr(other, "value", None) is None else other.value
        return a < b


class ResultsPage(QWidget):
    def __init__(self, conn, store: ExamStore, roster: Roster):
        super().__init__()
        self.setObjectName("page")
        self.conn, self.store, self.roster = conn, store, roster
        self.register: results.Register | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel("سجل الدرجات")
        title.setObjectName("pageTitle")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(QLabel("السنة الدراسية:"))
        self.year_box = QComboBox()
        self.year_box.currentIndexChanged.connect(lambda *_: self._load_exams())
        top.addWidget(self.year_box)
        top.addWidget(QLabel("الامتحان:"))
        self.exam_box = QComboBox()
        self.exam_box.setMinimumWidth(320)
        self.exam_box.currentIndexChanged.connect(lambda *_: self._load())
        top.addWidget(self.exam_box)
        root.addLayout(top)

        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("بحث بالاسم أو الرقم")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self._fill())
        tools.addWidget(self.search)
        tools.addWidget(QLabel("الترتيب:"))
        self.sort_box = QComboBox()
        for text, key in SORTS:
            self.sort_box.addItem(text, key)
        self.sort_box.currentIndexChanged.connect(lambda *_: self._fill())
        tools.addWidget(self.sort_box)
        self.parts_box = QCheckBox("عرض درجات الفروع")
        self.parts_box.setChecked(True)
        self.parts_box.toggled.connect(lambda *_: self._fill())
        tools.addWidget(self.parts_box)
        tools.addStretch()
        self.excel_button = QPushButton("تصدير إلى Excel")
        self.excel_button.clicked.connect(self._export)
        self.print_button = QPushButton("طباعة السجل")
        self.print_button.setObjectName("primary")
        self.print_button.clicked.connect(self._print)
        tools.addWidget(self.excel_button)
        tools.addWidget(self.print_button)
        root.addLayout(tools)

        self.table = QTableWidget()
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        root.addWidget(self.table, 1)
        self.summary = QLabel()
        self.summary.setObjectName("pageHint")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

    # ---------- تحميل ----------
    def refresh(self) -> None:
        current_year = self.year_box.currentData()
        years = sorted({results.academic_year(e.exam_date) for e in self.store.list_exams() if e.approved}, reverse=True)
        self.year_box.blockSignals(True)
        self.year_box.clear()
        self.year_box.addItem("كل السنوات", "")
        for y in years:
            if y:
                self.year_box.addItem(y, y)
        self.year_box.setCurrentIndex(max(self.year_box.findData(current_year), 0))
        self.year_box.blockSignals(False)
        self._load_exams()

    def select_exam(self, exam_id: int) -> None:
        self.refresh()
        index = self.exam_box.findData(exam_id)
        if index >= 0:
            self.exam_box.setCurrentIndex(index)

    def _load_exams(self) -> None:
        current = self.exam_box.currentData()
        year = self.year_box.currentData()
        self.exam_box.blockSignals(True)
        self.exam_box.clear()
        for e in self.store.list_exams():
            if e.approved and (not year or results.academic_year(e.exam_date) == year):
                self.exam_box.addItem(f"{e.name} — {e.subject} ({e.grade_name} / {e.section_name})", e.id)
        self.exam_box.setCurrentIndex(max(self.exam_box.findData(current), 0))
        self.exam_box.blockSignals(False)
        self._load()

    def _load(self) -> None:
        exam_id = self.exam_box.currentData()
        self.register = results.build(self.conn, exam_id) if exam_id is not None else None
        self._fill()

    def _names(self) -> tuple[str, str]:
        e = self.register.exam
        return e.grade_name, e.section_name

    # ---------- الجدول ----------
    def _rows(self):
        rows = list(self.register.results)
        needle = name_key(self.search.text())
        if needle:
            rows = [r for r in rows if needle in name_key(r.full_name) or needle in format_student_code(r.student_id)]
        key = self.sort_box.currentData()
        if key == "name":
            rows.sort(key=lambda r: name_key(r.full_name))
        elif key == "code":
            rows.sort(key=lambda r: r.student_id)
        else:
            def score(r):
                return r.final if r.final is not None else -1
            rows.sort(key=score, reverse=(key == "high"))
        return rows

    def _fill(self) -> None:
        enabled = self.register is not None
        for w in (self.excel_button, self.print_button, self.search, self.sort_box, self.parts_box):
            w.setEnabled(enabled)
        if not enabled:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.summary.setText("لا توجد امتحانات معتمدة بعد.")
            return
        exam, questions = self.register.exam, self.register.questions
        with_parts = self.parts_box.isChecked()
        heads = ["ت", "الرقم", "اسم الطالب"]
        for qi, q in enumerate(questions):
            if with_parts and len(q.parts) > 1:
                heads += [f"{question_title(qi)}\n{part_letter(pi, exam.label_style)} (من {format_marks(p.max_marks)})"
                          for pi, p in enumerate(q.parts)]
            heads.append(f"{question_title(qi)}\n(من {format_marks(q.total)})")
        heads += [f"الدرجة النهائية\n(من {format_marks(exam.total_marks)})", "الحالة"]
        rows = self._rows()
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(heads))
        self.table.setHorizontalHeaderLabels(heads)
        self.table.setRowCount(len(rows))
        bold = QFont()
        bold.setBold(True)
        grey = QBrush(QColor("#888888"))
        for i, r in enumerate(rows):
            cells: list[QTableWidgetItem] = [NumberItem(i + 1), QTableWidgetItem(format_student_code(r.student_id)),
                                             QTableWidgetItem(r.full_name)]
            for qi, q in enumerate(questions):
                if with_parts and len(q.parts) > 1:
                    cells += [NumberItem(r.parts.get(p.id)) for p in q.parts]
                item = NumberItem(r.questions[qi])
                if r.complete and not r.counted[qi]:
                    item.setForeground(grey)
                    item.setToolTip("لا يدخل في الدرجة النهائية (يُحتسب أفضل الأسئلة)")
                cells.append(item)
            final = NumberItem(r.final)
            final.setFont(bold)
            if not r.complete and not r.absent:
                final.setToolTip(f"ما صُحح حتى الآن: {format_marks(r.partial)}")
            cells += [final, QTableWidgetItem(status_text(r))]
            for c, item in enumerate(cells):
                if c == 1 or c == len(cells) - 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, c, item)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        s = self.register.stats()
        avg = "—" if s["average"] is None else format_marks(round(s["average"], 2))
        note = f"   ·   يُحتسب أفضل {exam.answer_count} أسئلة (غير المحتسب باللون الرمادي)" if exam.answer_count else ""
        self.summary.setText(
            f"الطلاب: {s['students']}   ·   الغائبون: {s['absent']}   ·   تصحيحهم ناقص: {s['incomplete']}   ·   "
            f"المتوسط: {avg}   ·   الأعلى: {format_marks(s['highest']) if s['highest'] is not None else '—'}   ·   "
            f"الأدنى: {format_marks(s['lowest']) if s['lowest'] is not None else '—'}   ·   "
            f"الناجحون: {s['passed']}{note}"
        )

    # ---------- التصدير والطباعة ----------
    def _warn_incomplete(self) -> bool:
        s = self.register.stats()
        if s["incomplete"]:
            return dialogs.confirm(self, f"تصحيح {s['incomplete']} طالباً لم يكتمل، وستظهر درجاتهم النهائية «—».\n"
                                         "هل تريد المتابعة؟", yes="متابعة")
        return True

    def _export(self) -> None:
        if not self.register or not self._warn_incomplete():
            return
        e = self.register.exam
        path, _ = QFileDialog.getSaveFileName(self, "حفظ سجل الدرجات", f"درجات {e.name} - {e.grade_name} {e.section_name}.xlsx",
                                              "ملفات Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            export_excel(self.register, path, *self._names(), with_parts=self.parts_box.isChecked())
        except AppError as exc:
            dialogs.error(self, str(exc))
            return
        dialogs.info(self, f"تم تصدير سجل الدرجات إلى:\n{path}")

    def _print(self) -> None:
        if not self.register or not self._warn_incomplete():
            return
        path = paths.exam_dir(self.register.exam.id) / "results.pdf"
        try:
            write_register_pdf(self.register, path, *self._names(), with_parts=self.parts_box.isChecked())
        except AppError as exc:
            dialogs.error(self, str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
