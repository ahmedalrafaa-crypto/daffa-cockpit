"""نوافذ إدخال بيانات الامتحان والأسئلة والفروع واختبار المحاذاة."""
from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QDate, QIODevice, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..core.exams import MAX_ANSWER_LINES, Exam, Part
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
        layout.addLayout(form)
        layout.addWidget(_buttons(self, "حفظ" if exam else "إنشاء"))

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
                    answer_lines=self.lines.value(), image=self.image)


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
