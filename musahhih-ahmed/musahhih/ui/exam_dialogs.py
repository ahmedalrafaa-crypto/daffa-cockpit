"""نوافذ إدخال بيانات الامتحان والأسئلة والفروع واختبار المحاذاة."""
from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QDate, QIODevice, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QFrame, QHeaderView, QScrollArea, QTableWidget,
    QTableWidgetItem, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..core.exam_package import _per_page
from ..core.exams import (
    LABEL_STYLES, MAX_ANSWER_LINES, MAX_TARGET_PAGES, Exam, Part, format_marks, part_letter, question_title,
)
from ..core.roster import Roster
from . import dialogs

SYMBOLS = "² ³ ⁻¹ ½ ₀ ₁ ₂ × ÷ ± √ ≈ ≠ ≤ ≥ ∞ → ° Δ α β γ θ λ μ π ρ σ ε ω Ω".split()
MAX_IMAGE_SIDE = 1600


class _SelectAllMixin:
    """عند الدخول للحقل يُحدَّد كل ما فيه، فلا تُلحق الكتابة الجديدة بالقيمة القديمة (5 ثم 20 ← 520)."""

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.lineEdit().selectAll)


class MarksSpin(_SelectAllMixin, QDoubleSpinBox):
    pass


class CountSpin(_SelectAllMixin, QSpinBox):
    pass


def _buttons(dialog: QDialog, save_text: str = "حفظ") -> QDialogButtonBox:
    box = QDialogButtonBox()
    save = box.addButton(save_text, QDialogButtonBox.ButtonRole.AcceptRole)
    save.setObjectName("primary")
    box.addButton("إلغاء", QDialogButtonBox.ButtonRole.RejectRole)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


def _symbol_bar(target: QPlainTextEdit) -> QWidget:
    """لوحة رموز علمية تُدرج الرمز عند موضع الكتابة."""
    bar = QWidget()
    bar.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    grid = QGridLayout(bar)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(3)
    for i, symbol in enumerate(SYMBOLS):
        button = QPushButton(f"\u2066{symbol}\u2069")  # عزل حتى لا تنعكس رموز مثل ≤ في واجهة عربية
        button.setObjectName("symbol")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda _=False, s=symbol: target.insertPlainText(s))
        grid.addWidget(button, i // 15, i % 15)
    return bar


class ExamDialog(QDialog):
    """بيانات الامتحان الأساسية. عند الإنشاء يُسأل أيضاً عن عدد الأسئلة."""

    def __init__(self, parent: QWidget | None, roster: Roster, exam: Exam | None = None, school_name: str = "",
                 defaults: dict | None = None):
        """defaults: قيم أولية من ملف امتحان جاهز (اسم، مادة، درجة، مدة، أسئلة مطلوبة، تعليمات)."""
        super().__init__(parent)
        self.roster = roster
        defaults = defaults or {}
        self.setWindowTitle("تعديل بيانات الامتحان" if exam else
                            "استيراد امتحان جاهز" if defaults else "إنشاء امتحان جديد")
        self.setMinimumWidth(520)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.name = QLineEdit(exam.name if exam else defaults.get("name", ""))
        self.name.setPlaceholderText("مثال: امتحان الشهر الأول")
        self.subject = QLineEdit(exam.subject if exam else defaults.get("subject", ""))
        self.subject.setPlaceholderText("مثال: الفيزياء")
        self.school = QLineEdit(exam.school_name if exam else school_name)
        self.school.setPlaceholderText("يظهر في ترويسة الورقة")
        self.grade = QComboBox()
        self.section = QComboBox()
        self.date = QDateEdit(QDate.fromString(exam.exam_date, "yyyy-MM-dd") if exam else QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        self.date.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.total = MarksSpin()
        self.total.setRange(1, 1000)
        self.total.setDecimals(1)
        self.total.setValue(exam.total_marks if exam else defaults.get("total_marks", 100))
        self.duration = CountSpin()
        self.duration.setRange(0, 600)
        self.duration.setSuffix(" دقيقة")
        self.duration.setSpecialValueText("غير محددة")
        self.duration.setValue(exam.duration_minutes if exam else defaults.get("duration_minutes", 45))
        self.answer_count = CountSpin()
        self.answer_count.setRange(0, 50)
        self.answer_count.setSpecialValueText("جميع الأسئلة")
        self.answer_count.setToolTip("إن كان المطلوب الإجابة عن بعض الأسئلة فقط (مثل 4 من 5) فاكتب العدد المطلوب")
        self.answer_count.setValue(exam.answer_count if exam else defaults.get("answer_count", 0))
        self.label_style = QComboBox()
        for key, sample in LABEL_STYLES.items():
            self.label_style.addItem(f"{sample}", key)
        current = exam.label_style if exam else defaults.get("label_style", "ar")
        self.label_style.setCurrentIndex(max(self.label_style.findData(current), 0))
        self.target_pages = CountSpin()
        self.target_pages.setRange(0, MAX_TARGET_PAGES)
        self.target_pages.setSpecialValueText("حسب المحتوى")
        self.target_pages.setSuffix(" صفحات")
        self.target_pages.setToolTip("يضبط البرنامج أسطر الإجابة تلقائياً ليتسع الامتحان كله في هذا العدد من الصفحات")
        self.target_pages.setValue(exam.target_pages if exam else defaults.get("target_pages", 0))
        self.per_page = QComboBox()
        for value, text in ((0, "حسب المحتوى"), (1, "سؤال في كل صفحة"), (2, "سؤالان في كل صفحة"),
                            (3, "ثلاثة أسئلة في كل صفحة")):
            self.per_page.addItem(text, value)
        self.per_page.setToolTip("الأسئلة تملأ الصفحة: الأول ربعها والباقي لما بعده. "
                                 "في «سؤال في كل صفحة» يأخذ الفرع الأول الربع والفرع الثاني الباقي.")
        current = exam.questions_per_page if exam else _per_page(defaults)
        self.per_page.setCurrentIndex(max(self.per_page.findData(current), 0))
        self.instructions = QPlainTextEdit(exam.instructions if exam else defaults.get("instructions", ""))
        self.instructions.setPlaceholderText("تعليمات تُطبع أعلى الورقة (اختياري)")
        self.instructions.setFixedHeight(80)
        form.addRow("اسم الامتحان:", self.name)
        form.addRow("المادة:", self.subject)
        form.addRow("اسم المدرسة:", self.school)
        form.addRow("الصف:", self.grade)
        form.addRow("الشعبة:", self.section)
        form.addRow("التاريخ:", self.date)
        form.addRow("الدرجة الكلية:", self.total)
        form.addRow("مدة الامتحان:", self.duration)
        form.addRow("الأسئلة المطلوبة:", self.answer_count)
        form.addRow("ترقيم الفروع:", self.label_style)
        form.addRow("عدد صفحات الورقة:", self.target_pages)
        form.addRow("توزيع الأسئلة:", self.per_page)
        form.addRow("تعليمات الورقة:", self.instructions)
        self.count = None
        if exam is None and not defaults:
            self.count = CountSpin()
            self.count.setRange(1, 20)
            self.count.setValue(2)
            form.addRow("عدد الأسئلة:", self.count)

        for g in roster.list_grades():
            self.grade.addItem(g.name, g.id)
        self.grade.currentIndexChanged.connect(lambda *_: self._load_sections())
        if exam:
            grade_id = roster.get_section(exam.section_id)[0].grade_id
            self.grade.setCurrentIndex(self.grade.findData(grade_id))
        self._load_sections(exam.section_id if exam else None)

        layout = QVBoxLayout(self)
        # الحقول داخل منطقة تمرير والأزرار ثابتة أسفلها، حتى لا تختفي الأزرار على الشاشات الصغيرة
        holder = QWidget()
        holder.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)
        layout.addWidget(_buttons(self, "حفظ" if exam else "استيراد" if defaults else "إنشاء"))
        available = (self.screen() or QApplication.primaryScreen()).availableGeometry().height()
        self.resize(620, min(holder.sizeHint().height() + 90, int(available * 0.9)))

    def _load_sections(self, select: int | None = None) -> None:
        self.section.clear()
        if self.grade.currentData() is not None:
            for s in self.roster.list_sections(self.grade.currentData()):
                self.section.addItem(s.name, s.id)
        index = self.section.findData(select)
        if index >= 0:
            self.section.setCurrentIndex(index)

    def accept(self) -> None:
        if self.section.currentData() is None:
            dialogs.error(self, "اختر الصف والشعبة. إن لم توجد شعب فأضفها أولاً من صفحة «الصفوف والشعب».")
            return
        super().accept()

    def values(self) -> dict:
        return dict(
            name=self.name.text(), subject=self.subject.text(), section_id=self.section.currentData(),
            exam_date=self.date.date().toString("yyyy-MM-dd"), total_marks=self.total.value(),
            duration_minutes=self.duration.value(), school_name=self.school.text(),
            answer_count=self.answer_count.value(), instructions=self.instructions.toPlainText(),
            label_style=self.label_style.currentData(), target_pages=self.target_pages.value(),
            questions_per_page=self.per_page.currentData(),
        )


class IntroDialog(QDialog):
    """نص تمهيدي اختياري للسؤال يظهر قبل فروعه (مثل معطيات مسألة)."""

    def __init__(self, parent: QWidget | None, title: str, text: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("نص تمهيدي للسؤال (اختياري) — يظهر قبل الفروع:"))
        self.edit = QPlainTextEdit(text)
        self.edit.setMinimumHeight(110)
        layout.addWidget(self.edit)
        layout.addWidget(_symbol_bar(self.edit))
        layout.addWidget(_buttons(self))


class PartDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, part: Part | None = None, default_marks: float = 5,
                 label: str = "نص الفرع:"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(600)
        self.image: bytes | None = part.image if part else None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(label))
        self.text = QPlainTextEdit(part.text if part else "")
        self.text.setMinimumHeight(120)
        layout.addWidget(self.text)
        layout.addWidget(_symbol_bar(self.text))

        row = QHBoxLayout()
        row.addWidget(QLabel("الدرجة:"))
        self.marks = MarksSpin()
        self.marks.setRange(0.5, 1000)
        self.marks.setDecimals(1)
        self.marks.setSingleStep(0.5)
        self.marks.setValue(part.max_marks if part else default_marks)
        row.addWidget(self.marks)
        row.addSpacing(24)
        row.addWidget(QLabel("أسطر الإجابة:"))
        self.lines = CountSpin()
        self.lines.setRange(0, MAX_ANSWER_LINES)
        self.lines.setValue(part.answer_lines if part else 5)
        self.lines.setToolTip("مساحة الإجابة المحجوزة على الورقة، كل سطر 9 ملم")
        row.addWidget(self.lines)
        self.lines_fixed = QCheckBox("ثابت")
        self.lines_fixed.setToolTip("يُطبع هذا العدد من الأسطر كما هو حتى عند الضبط التلقائي للصفحات")
        self.lines_fixed.setChecked(part.lines_fixed if part else False)
        row.addWidget(self.lines_fixed)
        row.addStretch()
        layout.addLayout(row)

        row = QHBoxLayout()
        choose = QPushButton("إدراج صورة أو رسم")
        choose.clicked.connect(self._choose_image)
        self.remove = QPushButton("إزالة الصورة")
        self.remove.clicked.connect(self._remove_image)
        self.thumb = QLabel()
        row.addWidget(choose)
        row.addWidget(self.remove)
        row.addWidget(self.thumb)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(_buttons(self))
        self._show_image()

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "اختيار صورة", "", "الصور (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            dialogs.error(self, "تعذر قراءة الصورة. اختر ملف صورة سليماً بصيغة PNG أو JPG.")
            return
        if max(image.width(), image.height()) > MAX_IMAGE_SIDE:
            image = image.scaled(MAX_IMAGE_SIDE, MAX_IMAGE_SIDE, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        self.image = bytes(data)
        self._show_image()

    def _remove_image(self) -> None:
        self.image = None
        self._show_image()

    def _show_image(self) -> None:
        self.remove.setEnabled(self.image is not None)
        if self.image is None:
            self.thumb.setText("لا توجد صورة")
            self.thumb.setPixmap(QPixmap())
            self.thumb.setText("لا توجد صورة")
            return
        pixmap = QPixmap()
        pixmap.loadFromData(self.image)
        self.thumb.setPixmap(pixmap.scaled(160, 70, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))

    def values(self) -> dict:
        return dict(text=self.text.toPlainText(), max_marks=self.marks.value(),
                    answer_lines=self.lines.value(), image=self.image, lines_fixed=self.lines_fixed.isChecked())


class AlignmentDialog(QDialog):
    """شرح اختبار المحاذاة مع قيم إزاحة الطابعة."""

    def __init__(self, parent: QWidget | None, dx: float, dy: float):
        super().__init__(parent)
        self.setWindowTitle("اختبار محاذاة الطباعة")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        steps = QLabel(
            "هذا الاختبار يتأكد أن الدرجات ستُطبع داخل خاناتها على الورقة الأصلية:\n\n"
            "1. اطبع ورقة طالب واحدة من ملف الأوراق بحجم 100% (Actual size) وليس «ملاءمة الصفحة».\n"
            "2. أعد الورقة المطبوعة نفسها إلى درج الطابعة بالاتجاه نفسه.\n"
            "3. اطبع ملف الاختبار فوقها بحجم 100% أيضاً.\n"
            "4. يجب أن يقع كل رقم وإطاره الرفيع داخل خانته، وأن يحيط الإطار بمربعات الزوايا بالتساوي.\n\n"
            "إن ظهرت إزاحة ثابتة فأدخل مقدارها هنا ثم أعد الاختبار:"
        )
        steps.setWordWrap(True)
        layout.addWidget(steps)
        form = QFormLayout()
        self.dx = self._spin(dx)
        self.dy = self._spin(dy)
        form.addRow("إزاحة أفقية (موجب = نحو اليمين):", self.dx)
        form.addRow("إزاحة عمودية (موجب = نحو الأسفل):", self.dy)
        layout.addLayout(form)
        layout.addWidget(_buttons(self, "إنشاء ملف الاختبار وفتحه"))

    @staticmethod
    def _spin(value: float) -> QDoubleSpinBox:
        spin = MarksSpin()
        spin.setRange(-15, 15)
        spin.setDecimals(1)
        spin.setSingleStep(0.5)
        spin.setSuffix(" ملم")
        spin.setValue(value)
        return spin


class LinesDialog(QDialog):
    """تعديل أسطر الإجابة لكل الأسئلة والفروع في مكان واحد، مع عرض ما سيُطبع فعلاً."""

    def __init__(self, parent: QWidget | None, store, exam_id: int, layout_info):
        super().__init__(parent)
        self.store, self.exam_id, self.layout_info = store, exam_id, layout_info
        exam = store.get_exam(exam_id)
        self.auto = bool(exam.target_pages or exam.questions_per_page)
        self.setWindowTitle("أسطر الإجابة لكل سؤال")
        self.setMinimumSize(640, 460)
        layout = QVBoxLayout(self)
        self.fill = bool(exam.questions_per_page)
        if self.fill:
            note = ("«توزيع الأسئلة» مفعّل: الفروع غير الثابتة تملأ مساحة صفحتها تلقائياً. "
                    "لتحديد عدد أسطر فرع بعينه فعّل «ثابت» ثم اكتب العدد، فتتوزع المساحة الباقية على غيره.")
        elif self.auto:
            note = (f"«عدد صفحات الورقة = {exam.target_pages}» مفعّل: الرقم المكتوب لكل فرع حدّ أقصى، "
                    "والبرنامج يصغّره عند الحاجة ليتسع الامتحان. فعّل «ثابت» لفرض العدد كما هو.")
        else:
            note = "تُطبع الأسطر بالعدد المكتوب لكل فرع."
        hint = QLabel(note)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(0, 4 if self.auto else 3)
        heads = ["السؤال / الفرع", "الأسطر", "على الورقة"] + (["ثابت"] if self.auto else [])
        self.table.setHorizontalHeaderLabels(heads)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.rows: list[tuple[int, QSpinBox, QCheckBox | None]] = []
        for qi, q in enumerate(store.questions(exam_id)):
            for pi, p in enumerate(q.parts):
                label = question_title(qi) if len(q.parts) == 1 else f"{question_title(qi)} — {part_letter(pi, exam.label_style)}"
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(f"{label}  ({format_marks(p.max_marks)} درجة)"))
                spin = CountSpin()
                spin.setRange(0, MAX_ANSWER_LINES)
                spin.setValue(p.answer_lines)
                self.table.setCellWidget(r, 1, spin)
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, 2, item)
                box = None
                if self.auto:
                    box = QCheckBox()
                    box.setChecked(p.lines_fixed)
                    if self.fill:   # في هذا الوضع الرقم لا يُستعمل إلا للفرع الثابت
                        spin.setEnabled(p.lines_fixed)
                        box.toggled.connect(spin.setEnabled)
                    holder = QWidget()
                    h = QHBoxLayout(holder)
                    h.setContentsMargins(0, 0, 0, 0)
                    h.addWidget(box, alignment=Qt.AlignmentFlag.AlignCenter)
                    self.table.setCellWidget(r, 3, holder)
                self.rows.append((p.id, spin, box))
        layout.addWidget(self.table, 1)
        self.pages = QLabel()
        self.pages.setObjectName("panelTitle")
        layout.addWidget(self.pages)
        buttons = QDialogButtonBox()
        apply = buttons.addButton("تطبيق وإعادة الحساب", QDialogButtonBox.ButtonRole.ApplyRole)
        apply.clicked.connect(self.apply)
        save = buttons.addButton("حفظ وإغلاق", QDialogButtonBox.ButtonRole.AcceptRole)
        save.setObjectName("primary")
        buttons.addButton("إلغاء", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._show_actual()

    def changes(self) -> dict[int, tuple[int, bool]]:
        return {pid: (spin.value(), box.isChecked() if box else False) for pid, spin, box in self.rows}

    def apply(self) -> bool:
        from ..core.errors import AppError
        try:
            self.store.set_answer_lines(self.changes())
            self._show_actual()
        except AppError as exc:
            dialogs.error(self, str(exc))
            return False
        return True

    def accept(self) -> None:
        if self.apply():
            super().accept()

    def _show_actual(self) -> None:
        from ..core.errors import AppError
        try:
            pages, lines = self.layout_info(self.store, self.exam_id)
        except AppError as exc:
            self.pages.setText(str(exc))
            self.pages.setStyleSheet("color: #b3392f;")
            return
        self.pages.setStyleSheet("")
        self.pages.setText(f"عدد صفحات ورقة الطالب: {pages}")
        for r, (pid, spin, _) in enumerate(self.rows):
            actual = lines.get(pid)
            item = self.table.item(r, 2)
            item.setText("—" if actual is None else str(actual))
            item.setForeground(Qt.GlobalColor.darkRed if actual is not None and actual < spin.value() and
                               not self.auto else Qt.GlobalColor.black)
