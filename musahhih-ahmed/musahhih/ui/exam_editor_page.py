"""محرّر الامتحان: الأسئلة والفروع والدرجات، ثم المعاينة والاعتماد وإنشاء الأوراق."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QHeaderView, QLabel, QProgressDialog, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..core.errors import AppError
from ..core.exams import ExamStore, format_marks, part_letter, question_title
from ..core.roster import Roster
from ..core.settings import Settings
from ..sheet import workflow
from ..sheet.text import isolate_formulas
from . import dialogs
from .exam_dialogs import AlignmentDialog, ExamDialog, IntroDialog, PartDialog
from .exams_page import ui_date

ROLE_KIND = Qt.ItemDataRole.UserRole          # "question" أو "part"
ROLE_ID = Qt.ItemDataRole.UserRole + 1


def _snippet(text: str, limit: int = 70) -> str:
    text = " ".join(text.split())
    text = text if len(text) <= limit else text[: limit - 1] + "…"
    return isolate_formulas(text)  # حتى لا ينعكس ترتيب المعادلات داخل الجملة العربية


def _button(text: str, slot, name: str = "") -> QPushButton:
    button = QPushButton(text)
    if name:
        button.setObjectName(name)
    button.clicked.connect(slot)
    return button


class ExamEditorPage(QWidget):
    back = Signal()
    import_requested = Signal()

    def __init__(self, store: ExamStore, roster: Roster, settings: Settings):
        super().__init__()
        self.setObjectName("page")
        self.store, self.roster, self.settings = store, roster, settings
        self.exam_id: int | None = None
        self._approved = False
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        top = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        top.addWidget(self.title, 1)
        self.edit_info = _button("تعديل بيانات الامتحان", self._edit_info)
        top.addWidget(self.edit_info)
        top.addWidget(_button("رجوع إلى الامتحانات", self.back.emit))
        root.addLayout(top)
        self.info = QLabel()
        self.info.setObjectName("pageHint")
        root.addWidget(self.info)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["السؤال / الفرع", "الدرجة", "أسطر الإجابة", "صورة"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(False)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        self.tree.currentItemChanged.connect(lambda *_: self._update_buttons())
        self.tree.itemDoubleClicked.connect(lambda *_: self._edit())
        root.addWidget(self.tree, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.add_question = _button("إضافة سؤال", self._add_question, "primary")
        self.add_part = _button("إضافة فرع", self._add_part, "primary")
        self.edit = _button("تعديل", self._edit)
        self.up = _button("▲", lambda: self._move(-1), "icon")
        self.down = _button("▼", lambda: self._move(1), "icon")
        self.delete = _button("حذف", self._delete, "danger")
        for b in (self.add_question, self.add_part, self.edit, self.up, self.down, self.delete):
            row.addWidget(b)
        row.addStretch()
        self.sum_label = QLabel()
        row.addWidget(self.sum_label)
        root.addLayout(row)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.preview = _button("معاينة الورقة", self._preview)
        self.approve = _button("اعتماد الامتحان وإنشاء أوراق الطلاب", self._approve, "primary")
        self.open_sheets = _button("فتح أوراق الطلاب للطباعة", self._open_sheets, "primary")
        self.alignment = _button("اختبار محاذاة الطباعة", self._alignment)
        self.import_scans = _button("استيراد الأوراق الممسوحة", self.import_requested.emit)
        self.unapprove = _button("إلغاء الاعتماد", self._unapprove, "danger")
        for b in (self.preview, self.approve, self.open_sheets, self.alignment, self.import_scans):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(self.unapprove)
        root.addLayout(row)

    # ---------- تحميل ----------
    def load(self, exam_id: int) -> None:
        self.exam_id = exam_id
        self.refresh()

    def refresh(self, select: tuple[str, int] | None = None) -> None:
        if self.exam_id is None:
            return
        exam = self.store.get_exam(self.exam_id)
        questions = self.store.questions(self.exam_id)
        self.title.setText(f"{exam.name} — {exam.subject}")
        duration = f"   ·   المدة: {exam.duration_minutes} دقيقة" if exam.duration_minutes else ""
        status = "معتمد — الأسئلة مقفلة" if exam.approved else "مسودة"
        self.info.setText(
            f"{exam.grade_name} / شعبة {exam.section_name}   ·   التاريخ: {ui_date(exam.exam_date)}{duration}"
            f"   ·   الحالة: {status}"
        )
        select = select or self._current()
        self.tree.blockSignals(True)
        self.tree.clear()
        chosen = None
        for qi, q in enumerate(questions):
            label = question_title(qi) + (f" — {_snippet(q.intro, 50)}" if q.intro else "")
            q_item = QTreeWidgetItem([label, format_marks(q.total), "", ""])
            q_item.setData(0, ROLE_KIND, "question")
            q_item.setData(0, ROLE_ID, q.id)
            font = q_item.font(0)
            font.setBold(True)
            q_item.setFont(0, font)
            q_item.setFont(1, font)
            self.tree.addTopLevelItem(q_item)
            if select == ("question", q.id):
                chosen = q_item
            for pi, p in enumerate(q.parts):
                text = _snippet(p.text) or "(بلا نص)"
                item = QTreeWidgetItem([f"      {part_letter(pi, exam.label_style)})  {text}", format_marks(p.max_marks),
                                        str(p.answer_lines), "نعم" if p.image else ""])
                item.setData(0, ROLE_KIND, "part")
                item.setData(0, ROLE_ID, p.id)
                q_item.addChild(item)
                if select == ("part", p.id):
                    chosen = item
            for column in (1, 2, 3):
                q_item.setTextAlignment(column, Qt.AlignmentFlag.AlignCenter)
                for i in range(q_item.childCount()):
                    q_item.child(i).setTextAlignment(column, Qt.AlignmentFlag.AlignCenter)
        self.tree.expandAll()
        if chosen is None and self.tree.topLevelItemCount():
            chosen = self.tree.topLevelItem(0)
        if chosen is not None:
            self.tree.setCurrentItem(chosen)
        self.tree.blockSignals(False)

        total = sum(q.total for q in questions)
        counted = self.store.counted_total(self.exam_id)
        match = abs(counted - exam.total_marks) < 1e-9
        if exam.answer_count and exam.answer_count < len(questions):
            summary = (f"مجموع الأسئلة: {format_marks(total)}   ·   المحتسب (أفضل {exam.answer_count}): "
                       f"{format_marks(counted)} من {format_marks(exam.total_marks)}")
        else:
            summary = f"مجموع الدرجات: {format_marks(total)} من {format_marks(exam.total_marks)}"
        self.sum_label.setText(summary + ("  ✓" if match else "  — غير مطابق"))
        self.sum_label.setStyleSheet(f"font-weight: bold; color: {'#2f8f83' if match else '#b3392f'};")
        self._approved = exam.approved
        self._update_buttons()

    def _current(self) -> tuple[str, int] | None:
        item = self.tree.currentItem()
        return (item.data(0, ROLE_KIND), item.data(0, ROLE_ID)) if item else None

    def _update_buttons(self) -> None:
        draft = not self._approved
        current = self._current()
        self.edit_info.setEnabled(draft)
        self.add_question.setEnabled(draft)
        self.add_part.setEnabled(draft and current is not None)
        for b in (self.edit, self.up, self.down, self.delete):
            b.setEnabled(draft and current is not None)
        self.preview.setVisible(draft)
        self.approve.setVisible(draft)
        self.open_sheets.setVisible(not draft)
        self.alignment.setVisible(not draft)
        self.import_scans.setVisible(not draft)
        self.unapprove.setVisible(not draft)

    def _question_id(self) -> int | None:
        """السؤال المحدد، أو سؤال الفرع المحدد."""
        item = self.tree.currentItem()
        if item is None:
            return None
        if item.data(0, ROLE_KIND) == "part":
            item = item.parent()
        return item.data(0, ROLE_ID)

    def _try(self, action) -> bool:
        try:
            action()
            return True
        except AppError as exc:
            dialogs.error(self, str(exc))
            return False

    # ---------- التحرير ----------
    def _edit_info(self) -> None:
        dialog = ExamDialog(self, self.roster, self.store.get_exam(self.exam_id))
        while dialog.exec() == QDialog.DialogCode.Accepted:
            if self._try(lambda: self.store.update_exam(self.exam_id, **dialog.values())):
                self.refresh()
                return

    def _add_question(self) -> None:
        """سؤال جديد بنصه ودرجته في خطوة واحدة؛ يُضاف له فرع ثانٍ (ب، ج…) لاحقاً عند الحاجة."""
        dialog = PartDialog(self, "إضافة سؤال", label="نص السؤال:")
        while dialog.exec() == QDialog.DialogCode.Accepted:
            new: list[tuple[int, int]] = []
            if self._try(lambda: new.append(self.store.add_question_with_part(self.exam_id, **dialog.values()))):
                self.refresh(("part", new[0][1]))
                return

    def _complete_question(self, question) -> None:
        """سؤال بلا درجة (أُضيف نصه فقط): يُدخل له الآن درجته وأسطر إجابته فيصير سؤالاً كاملاً."""
        dialog = PartDialog(self, "درجة السؤال", label="نص السؤال:")
        dialog.text.setPlainText(question.intro)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            def convert() -> None:
                part_id = self.store.add_part(question.id, **dialog.values())
                self.store.update_question(question.id, "")  # النص صار نص الفرع الوحيد
                self._converted = part_id

            if self._try(convert):
                self.refresh(("part", self._converted))
                return

    def _add_part(self) -> None:
        question_id = self._question_id()
        if question_id is None:
            return
        dialog = PartDialog(self, "إضافة فرع")
        while dialog.exec() == QDialog.DialogCode.Accepted:
            new: list[int] = []
            if self._try(lambda: new.append(self.store.add_part(question_id, **dialog.values()))):
                self.refresh(("part", new[0]))
                return

    def _edit(self) -> None:
        current = self._current()
        if current is None or self._approved:
            return
        kind, item_id = current
        if kind == "question":
            question = next(q for q in self.store.questions(self.exam_id) if q.id == item_id)
            if not question.parts:
                self._complete_question(question)
                return
            if len(question.parts) == 1 and not question.intro.strip():
                # سؤال بلا فروع في نظر المستخدم: التعديل عليه هو تعديل نصه ودرجته
                self._edit_part(question.parts[0], "تعديل السؤال", "نص السؤال:")
                return
            dialog = IntroDialog(self, "تعديل السؤال", question.intro)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                if self._try(lambda: self.store.update_question(item_id, dialog.edit.toPlainText())):
                    self.refresh()
            return
        part = next(p for q in self.store.questions(self.exam_id) for p in q.parts if p.id == item_id)
        self._edit_part(part, "تعديل الفرع", "نص الفرع:")

    def _edit_part(self, part, title: str, label: str) -> None:
        dialog = PartDialog(self, title, part, label=label)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            if self._try(lambda: self.store.update_part(part.id, **dialog.values())):
                self.refresh(("part", part.id))
                return

    def _move(self, step: int) -> None:
        current = self._current()
        if current is None:
            return
        kind, item_id = current
        move = self.store.move_question if kind == "question" else self.store.move_part
        if self._try(lambda: move(item_id, step)):
            self.refresh(current)

    def _delete(self) -> None:
        current = self._current()
        if current is None:
            return
        kind, item_id = current
        text = self.tree.currentItem().text(0).strip()
        what = "السؤال مع كل فروعه" if kind == "question" else "الفرع"
        if not dialogs.confirm(self, f"هل تريد حذف {what}؟\n{text}", yes="حذف"):
            return
        delete = self.store.delete_question if kind == "question" else self.store.delete_part
        if self._try(lambda: delete(item_id)):
            self.refresh()

    # ---------- الورقة ----------
    @staticmethod
    def _open_file(path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _preview(self) -> None:
        result: list[Path] = []
        if self._try(lambda: result.append(workflow.preview(self.store, self.exam_id))):
            self._open_file(result[0])

    def _approve(self) -> None:
        if not self._try(lambda: self.store.check_ready(self.exam_id)):
            return
        exam = self.store.get_exam(self.exam_id)
        count = len(self.roster.list_students(exam.section_id))
        pages: list[int] = []
        if not self._try(lambda: pages.append(workflow.sheet_pages(self.store, self.exam_id))):
            return
        wanted = f" (المطلوب {exam.target_pages})" if exam.target_pages else ""
        if exam.target_pages and pages[0] != exam.target_pages:
            wanted += " — تنبيه: يختلف عن المطلوب"
        if not dialogs.confirm(
            self,
            f"سيُعتمد الامتحان وتُنشأ أوراق {count} طالباً في {exam.grade_name} / شعبة {exam.section_name}.\n"
            f"عدد صفحات ورقة الطالب الواحد: {pages[0]}{wanted}، فالمجموع {pages[0] * count} ورقة للطباعة.\n\n"
            "بعد الاعتماد تُقفل الأسئلة والدرجات لأن مواضع الخانات تثبت على الورق المطبوع.\n"
            "تأكد من المعاينة أولاً. هل تريد المتابعة؟",
            yes="اعتماد",
        ):
            return
        progress = QProgressDialog("جارٍ إنشاء أوراق الطلاب…", "", 0, max(count, 1), self)
        progress.setWindowTitle("إنشاء الأوراق")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        def report(done: int, total: int) -> None:
            progress.setMaximum(total)
            progress.setValue(done)
            QApplication.processEvents()

        result: list[Path] = []
        ok = self._try(lambda: result.append(workflow.approve(self.store, self.roster, self.exam_id, report)))
        progress.close()
        self.refresh()
        if ok:
            dialogs.info(
                self,
                "تم اعتماد الامتحان وإنشاء أوراق الطلاب.\n\n"
                "عند الطباعة اختر الحجم 100% (Actual size) وليس «ملاءمة الصفحة»، "
                "ثم جرّب «اختبار محاذاة الطباعة» على ورقة واحدة قبل طباعة الجميع.",
            )
            self._open_file(result[0])

    def _open_sheets(self) -> None:
        result: list[Path] = []
        if self._try(lambda: result.append(workflow.sheets_path(self.store, self.exam_id))):
            self._open_file(result[0])

    def _alignment(self) -> None:
        dialog = AlignmentDialog(self, self.settings.get_float(workflow.OFFSET_X_KEY),
                                 self.settings.get_float(workflow.OFFSET_Y_KEY))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.settings.set(workflow.OFFSET_X_KEY, dialog.dx.value())
        self.settings.set(workflow.OFFSET_Y_KEY, dialog.dy.value())
        result: list[Path] = []
        if self._try(lambda: result.append(workflow.alignment_test(self.store, self.settings, self.exam_id))):
            self._open_file(result[0])

    def _unapprove(self) -> None:
        if not dialogs.confirm(
            self,
            "إلغاء الاعتماد يعيد الامتحان مسودة قابلة للتعديل.\n\n"
            "تحذير: الأوراق التي طُبعت من قبل تصبح غير صالحة، لأن مواضع الخانات قد تتغير "
            "عند إعادة الاعتماد. افعل ذلك فقط إذا لم توزَّع الأوراق على الطلاب.\n\nهل تريد المتابعة؟",
            yes="إلغاء الاعتماد", no="تراجع",
        ):
            return
        if self._try(lambda: self.store.unapprove(self.exam_id)):
            self.refresh()
