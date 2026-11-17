"""صفحة طباعة الدرجات على أوراق الإجابة الأصلية: الإعدادات والمعايرة والمعاينة وإنشاء ملف الطباعة."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from .. import paths
from ..core import printing
from ..core.errors import AppError
from ..core.exams import ExamStore
from ..core.printing import ORDER_SCAN, ORDER_STUDENT, PrintSettings
from ..core.scans import ScanStore
from ..core.settings import Settings
from ..scan import align, importer
from ..sheet import workflow
from . import dialogs
from .grading_page import ZoomView, to_pixmap

COLOR_NAMES = {"red": "أحمر", "blue": "أزرق", "black": "أسود"}


def _spin(value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(-15, 15)
    spin.setDecimals(1)
    spin.setSingleStep(0.5)
    spin.setSuffix(" ملم")
    spin.setValue(value)
    return spin


def preview_pixmap(scan, page: printing.PrintPage, ink: str) -> tuple[QPixmap, bool]:
    """صورة الورقة الممسوحة وفوقها الدرجات في مواضعها كما ستُطبع. يعيد (الصورة، هل الورقة مقوَّمة)."""
    image = importer.read_image(scan.path) if scan else None
    if image is None:
        return QPixmap(), False
    pixmap = to_pixmap(image)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(ink))
    k = align.PX_PER_MM
    for box, text in page.items:
        f = QFont()
        f.setBold(True)
        f.setPixelSize(round(min(5.5, box.h * 0.62) * k))
        painter.setFont(f)
        painter.drawText(round(box.x * k), round(box.y * k), round(box.w * k), round(box.h * k),
                         int(Qt.AlignmentFlag.AlignCenter), text)
    painter.end()
    return pixmap, scan.aligned


class PreviewDialog(QDialog):
    """معاينة الدرجات فوق صور الأوراق الممسوحة، صفحةً صفحة، بترتيب ملف الطباعة نفسه."""

    def __init__(self, parent, conn, exam_id: int, order: str, ink: str):
        super().__init__(parent)
        self.setWindowTitle("معاينة الدرجات فوق الأوراق")
        self.resize(1100, 760)
        self.scans = ScanStore(conn)
        self.ink = ink
        self.pages = printing.build_pages(conn, exam_id, order)
        layout = QHBoxLayout(self)
        self.list = QListWidget()
        self.list.setFixedWidth(260)
        for i, p in enumerate(self.pages, start=1):
            item = QListWidgetItem(f"{i}. {p.full_name} — صفحة {p.page}" + ("" if p.items else "  (بلا درجات)"))
            self.list.addItem(item)
        self.list.currentRowChanged.connect(self._show)
        layout.addWidget(self.list)
        right = QVBoxLayout()
        self.note = QLabel()
        self.note.setStyleSheet("color: #b3392f;")
        right.addWidget(self.note)
        self.view = ZoomView()
        right.addWidget(self.view, 1)
        layout.addLayout(right, 1)
        if self.pages:
            self.list.setCurrentRow(0)

    def _show(self, row: int) -> None:
        if row < 0:
            return
        page = self.pages[row]
        pixmap, aligned = preview_pixmap(self.scans.get(page.scan_id), page, self.ink)
        self.view.show_pixmaps([pixmap] if not pixmap.isNull() else [])
        self.note.setText("" if aligned else "هذه الورقة لم تُقوَّم عند المسح؛ المعاينة تقريبية لكن الطباعة لا تتأثر.")


class OrientationDialog(QDialog):
    """مساعد اكتشاف طريقة سحب الطابعة للورق، بتجربة واحدة على ورقتين فارغتين."""

    QUESTIONS = [
        ("هل ظهرت الطباعة على الوجه نفسه الذي كتبتَ عليه علامتك X؟", printing.FACE, [("نعم", "up"), ("لا، على الوجه الآخر", "down")]),
        ("هل يشير السهم «أعلى الصفحة» نحو الحافة التي كتبتَ قربها علامتك X؟", printing.TOP,
         [("نعم", "first"), ("لا، نحو الحافة المقابلة", "last")]),
        ("على أي ورقة ظهر الرقم الكبير 1؟", printing.STACK, [("على الورقة X1 (العليا)", "top"),
                                                            ("على الورقة X2 (السفلى)", "bottom")]),
    ]

    def __init__(self, parent, settings: Settings, exam_id: int | None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("ضبط وضع الورق في الطابعة")
        self.setFixedWidth(660)
        layout = QVBoxLayout(self)
        head = QLabel("<b>تجربة واحدة تكفي لكل طابعة:</b>")
        layout.addWidget(head)
        # كل خطوة في سطر مستقل: القوائم المرقمة في Qt يُقدَّر ارتفاعها بأقل من الحقيقي فتُقصّ
        for number, text in enumerate((
                "خذ ورقتين فارغتين. اكتب بالقلم علامة كبيرة <b>X1</b> على الأولى و<b>X2</b> على الثانية، "
                "على <b>الوجه المتجه إلى الأعلى</b> وقرب <b>الحافة التي ستدخل الطابعة أولاً</b>.",
                "ضع الورقتين في الدرج كما ستضع أوراق الامتحان، والورقة <b>X1 فوق X2</b>.",
                "اضغط «طباعة صفحة الاختبار» واطبع الملف بحجم 100% (Actual size).",
                "انظر إلى الورقتين وأجب عن الأسئلة الثلاثة."), start=1):
            step = QLabel(f"{number}. {text}")
            step.setWordWrap(True)
            step.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(step)
        open_test = QPushButton("طباعة صفحة الاختبار")
        open_test.clicked.connect(lambda: self._open_test(exam_id))
        layout.addWidget(open_test, alignment=Qt.AlignmentFlag.AlignRight)
        self.boxes = []
        for number, (question, key, options) in enumerate(self.QUESTIONS, start=1):
            box = QComboBox()
            box.addItem("— اختر —", "")
            for text, value in options:
                box.addItem(text, value)
            box.setCurrentIndex(max(box.findData(settings.get(key)), 0))
            box.currentIndexChanged.connect(lambda *_: self._update())
            label = QLabel(f"<b>س{number}:</b> {question}")   # السؤال في سطر كامل فوق جوابه، فلا يُقصّ
            label.setWordWrap(True)
            layout.addWidget(label)
            layout.addWidget(box)
            self.boxes.append((key, box))
        self.result = QLabel()
        self.result.setWordWrap(True)
        self.result.setObjectName("panelTitle")
        layout.addWidget(self.result)
        buttons = QHBoxLayout()
        save = QPushButton("حفظ")
        save.setObjectName("primary")
        save.clicked.connect(self.accept)
        cancel = QPushButton("إلغاء")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        buttons.addStretch()
        layout.addLayout(buttons)
        self._update()

    def _fit(self) -> None:
        """ارتفاع النافذة من عرضها الفعلي: الأسطر الملتفة تأخذ حاجتها كاملة فلا يُقصّ شيء."""
        layout = self.layout()
        layout.activate()
        height = layout.totalHeightForWidth(self.width())
        if height > 0:
            self.setMinimumHeight(height)
            self.resize(self.width(), height)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit()

    def answers(self) -> dict[str, str]:
        return {key: box.currentData() for key, box in self.boxes}

    def _update(self) -> None:
        a = self.answers()
        text = printing.loading_instructions(a[printing.FACE], a[printing.TOP], a[printing.STACK])
        self.result.setText(text or "أجب عن الأسئلة الثلاثة لتظهر طريقة وضع الأوراق.")
        if self.isVisible():
            self._fit()

    def _open_test(self, exam_id) -> None:
        from ..sheet.orientation import write_orientation_test
        folder = paths.exam_dir(exam_id) if exam_id is not None else paths.data_dir()
        path = folder / "paper-orientation-test.pdf"
        try:
            write_orientation_test(path)
        except Exception:
            dialogs.error(self, "تعذر إنشاء صفحة الاختبار. أغلق الملف إن كان مفتوحاً ثم أعد المحاولة.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def accept(self) -> None:
        for key, value in self.answers().items():
            self.settings.set(key, value)
        super().accept()


class PrintPage(QWidget):
    def __init__(self, conn, store: ExamStore, settings: Settings):
        super().__init__()
        self.setObjectName("page")
        self.conn, self.store, self.settings = conn, store, settings
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        top = QHBoxLayout()
        title = QLabel("طباعة الدرجات على الأوراق")
        title.setObjectName("pageTitle")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(QLabel("الامتحان:"))
        self.exam_box = QComboBox()
        self.exam_box.setMinimumWidth(320)
        self.exam_box.currentIndexChanged.connect(lambda *_: self._load())
        top.addWidget(self.exam_box)
        root.addLayout(top)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self.info)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        # --- طريقة الطباعة ---
        how = QFrame()
        how.setObjectName("card")
        form = QFormLayout(how)
        form.setContentsMargins(16, 14, 16, 14)
        head = QLabel("طريقة الطباعة")
        head.setObjectName("panelTitle")
        form.addRow(head)
        self.order_box = QComboBox()
        self.order_box.addItem("بترتيب المسح (الرزمة كما خرجت من الماسح)", ORDER_SCAN)
        self.order_box.addItem("بترتيب الطلاب (أبجدياً، صفحةً صفحة)", ORDER_STUDENT)
        form.addRow("ترتيب الصفحات:", self.order_box)
        self.duplex = QCheckBox("الأوراق مطبوعة على الوجهين")
        form.addRow("", self.duplex)
        self.color_box = QComboBox()
        for key, name in COLOR_NAMES.items():
            self.color_box.addItem(name, key)
        form.addRow("لون الدرجات:", self.color_box)
        cards.addWidget(how, 1)
        # --- المعايرة ---
        cal = QFrame()
        cal.setObjectName("card")
        grid = QGridLayout(cal)
        grid.setContentsMargins(16, 14, 16, 14)
        head = QLabel("معايرة الطابعة")
        head.setObjectName("panelTitle")
        grid.addWidget(head, 0, 0, 1, 3)
        grid.addWidget(QLabel("أفقياً (موجب = يمين)"), 1, 1)
        grid.addWidget(QLabel("عمودياً (موجب = أسفل)"), 1, 2)
        ps = PrintSettings.load(settings)
        self.front_x, self.front_y = _spin(ps.front[0]), _spin(ps.front[1])
        self.back_x, self.back_y = _spin(ps.back[0]), _spin(ps.back[1])
        grid.addWidget(QLabel("الوجه الأمامي:"), 2, 0)
        grid.addWidget(self.front_x, 2, 1)
        grid.addWidget(self.front_y, 2, 2)
        self.back_label = QLabel("الوجه الخلفي:")
        grid.addWidget(self.back_label, 3, 0)
        grid.addWidget(self.back_x, 3, 1)
        grid.addWidget(self.back_y, 3, 2)
        cards.addWidget(cal, 1)
        root.addLayout(cards)

        self.duplex.setChecked(ps.duplex)
        self.color_box.setCurrentIndex(max(self.color_box.findData(ps.color), 0))
        for w in (self.front_x, self.front_y, self.back_x, self.back_y):
            w.valueChanged.connect(lambda *_: self._save_settings())
        self.duplex.toggled.connect(lambda *_: self._save_settings())
        self.color_box.currentIndexChanged.connect(lambda *_: self._save_settings())

        steps = QLabel(
            "<b>الخطوات:</b> (1) اطبع «ملف اختبار المحاذاة» فوق ورقة طالب مطبوعة وتأكد أن كل رقم داخل خانته، "
            "وإلا أدخل الإزاحة أعلاه وأعد الاختبار. (2) راجع «المعاينة». (3) أنشئ ملف طباعة الدرجات واطبعه "
            "<b>بحجم 100% (Actual size)</b> وضع الأوراق في الطابعة <b>بالترتيب المختار نفسه وبالاتجاه نفسه</b>"
            " الذي طُبعت به أول مرة. على الوجهين اختر «قلب على الحافة الطويلة».")
        steps.setWordWrap(True)
        steps.setObjectName("pageHint")
        root.addWidget(steps)
        loading = QHBoxLayout()
        self.loading = QLabel()
        self.loading.setWordWrap(True)
        self.loading.setTextFormat(Qt.TextFormat.RichText)
        loading.addWidget(self.loading, 1)
        self.orientation_button = QPushButton("ضبط وضع الورق في الطابعة")
        self.orientation_button.clicked.connect(self._orientation)
        loading.addWidget(self.orientation_button)
        root.addLayout(loading)

        row = QHBoxLayout()
        self.alignment_button = QPushButton("ملف اختبار المحاذاة")
        self.alignment_button.clicked.connect(self._alignment)
        self.preview_button = QPushButton("معاينة الدرجات فوق الأوراق")
        self.preview_button.clicked.connect(self._preview)
        self.print_button = QPushButton("إنشاء ملف طباعة الدرجات")
        self.print_button.setObjectName("primary")
        self.print_button.clicked.connect(self._print)
        for b in (self.alignment_button, self.preview_button, self.print_button):
            row.addWidget(b)
        row.addStretch()
        root.addLayout(row)
        root.addStretch()
        self._update_back()
        self._show_loading()

    # ---------- تحميل ----------
    def refresh(self) -> None:
        current = self.exam_box.currentData()
        self.exam_box.blockSignals(True)
        self.exam_box.clear()
        scans = ScanStore(self.conn)
        for e in self.store.list_exams():
            if e.approved and scans.summary(e.id).matched:
                self.exam_box.addItem(f"{e.name} — {e.subject} ({e.grade_name} / {e.section_name})", e.id)
        self.exam_box.setCurrentIndex(max(self.exam_box.findData(current), 0))
        self.exam_box.blockSignals(False)
        self._load()

    def select_exam(self, exam_id: int) -> None:
        self.refresh()
        index = self.exam_box.findData(exam_id)
        if index >= 0:
            self.exam_box.setCurrentIndex(index)

    def _load(self) -> None:
        exam_id = self.exam_box.currentData()
        for b in (self.alignment_button, self.preview_button, self.print_button):
            b.setEnabled(exam_id is not None)
        if exam_id is None:
            self.info.setText("لا توجد امتحانات مستوردة أوراقها بعد.")
            return
        r = printing.readiness(self.conn, exam_id)
        lines = [f"صفحات للطباعة: <b>{r['pages']}</b>   ·   اكتمل تصحيح <b>{r['complete']}</b> من {r['students']}"]
        if not r["confirmed"]:
            lines.append("<span style='color:#b3392f'>لم يُؤكَّد اكتمال استيراد الأوراق بعد.</span>")
        if r["incomplete"]:
            lines.append("<span style='color:#b3392f'>تصحيحهم ناقص (تبقى خاناتهم الناقصة فارغة): "
                         + "، ".join(r["incomplete"]) + "</span>")
        done = printing.jobs(self.conn, exam_id)
        if done:
            last = done[-1]
            changed = last.marks_hash != printing.marks_signature(self.conn, exam_id)
            lines.append(f"آخر ملف طباعة: {last.created_at} ({last.pages} صفحة)"
                         + ("   ·   <span style='color:#b3392f'>تغيّرت درجات بعده</span>" if changed else ""))
        self.info.setText("<br>".join(lines))

    def _update_back(self) -> None:
        for w in (self.back_label, self.back_x, self.back_y):
            w.setEnabled(self.duplex.isChecked())

    def _settings(self) -> PrintSettings:
        return PrintSettings((self.front_x.value(), self.front_y.value()), (self.back_x.value(), self.back_y.value()),
                             self.duplex.isChecked(), self.color_box.currentData())

    def _save_settings(self) -> None:
        self._settings().save(self.settings)
        self._update_back()

    def _show_loading(self) -> None:
        text = printing.saved_instructions(self.settings)
        if text:
            self.loading.setText(f"<b>وضع الأوراق في طابعتك:</b> {text}")
        else:
            self.loading.setText("<span style='color:#b3392f'><b>لم يُضبط بعد وضع الورق في الطابعة.</b> "
                                 "اضغط الزر وجرّب على ورقتين فارغتين قبل طباعة أوراق الطلاب.</span>")

    def _orientation(self) -> None:
        if OrientationDialog(self, self.settings, self.exam_box.currentData()).exec() == QDialog.DialogCode.Accepted:
            self._show_loading()

    # ---------- الأفعال ----------
    @staticmethod
    def _open(path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _alignment(self) -> None:
        try:
            path = workflow.alignment_test(self.store, self.settings, self.exam_box.currentData())
        except AppError as exc:
            dialogs.error(self, str(exc))
            return
        self._open(path)

    def _preview(self) -> None:
        try:
            dialog = PreviewDialog(self, self.conn, self.exam_box.currentData(), self.order_box.currentData(),
                                   self._settings().ink)
        except AppError as exc:
            dialogs.error(self, str(exc))
            return
        dialog.exec()

    def _print(self) -> None:
        exam_id = self.exam_box.currentData()
        r = printing.readiness(self.conn, exam_id)
        if not r["confirmed"]:
            dialogs.error(self, "أكّد اكتمال استيراد الأوراق أولاً من صفحة «استيراد الأوراق».")
            return
        if r["incomplete"] and not dialogs.confirm(
                self, f"تصحيح {len(r['incomplete'])} طالباً لم يكتمل، وستبقى خاناتهم الناقصة فارغة.\nهل تتابع؟",
                yes="متابعة"):
            return
        done = printing.jobs(self.conn, exam_id)
        if done:
            last = done[-1]
            changed = last.marks_hash != printing.marks_signature(self.conn, exam_id)
            note = "\nتغيّرت درجات منذ ذلك الحين." if changed else "\nالدرجات لم تتغير منذ ذلك الحين."
            if not dialogs.confirm(self, f"أُنشئ ملف طباعة لهذا الامتحان من قبل ({last.created_at}).{note}\n\n"
                                         "طباعة الدرجات مرتين على الأوراق نفسها تُفسدها. هل تريد إنشاء ملف جديد؟",
                                   yes="إنشاء ملف جديد", no="إلغاء"):
                return
        if not printing.saved_instructions(self.settings) and not dialogs.confirm(
                self, "لم تضبط بعد وضع الورق في الطابعة، فقد تُطبع الدرجات على الوجه الخطأ أو مقلوبة.\n"
                      "ننصح بتجربة «ضبط وضع الورق في الطابعة» على ورقتين فارغتين أولاً. هل تتابع؟",
                yes="متابعة", no="إلغاء"):
            return
        try:
            path, count = workflow.print_marks(self.conn, exam_id, self.order_box.currentData(), self._settings())
        except AppError as exc:
            dialogs.error(self, str(exc))
            return
        self._load()
        first = printing.build_pages(self.conn, exam_id, self.order_box.currentData())[:3]
        order = "\n".join(f"  {i}. {p.full_name} — صفحة {p.page}" for i, p in enumerate(first, start=1))
        how = printing.saved_instructions(self.settings)
        dialogs.info(self, f"أُنشئ ملف طباعة الدرجات ({count} صفحة):\n{path}\n\n"
                           + (f"{how}\n\n" if how else "")
                           + f"أول الأوراق التي يجب أن تدخل الطابعة بالترتيب:\n{order}\n\n"
                           "اطبع بحجم 100% (Actual size). جرّب أول ورقة وحدها قبل الرزمة كلها.")
        self._open(path)
