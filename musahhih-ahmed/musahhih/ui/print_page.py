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
        try:
            path, count = workflow.print_marks(self.conn, exam_id, self.order_box.currentData(), self._settings())
        except AppError as exc:
            dialogs.error(self, str(exc))
            return
        self._load()
        dialogs.info(self, f"أُنشئ ملف طباعة الدرجات ({count} صفحة):\n{path}\n\n"
                           "اطبعه بحجم 100% (Actual size)، والأوراق في الطابعة بالترتيب المختار وبالاتجاه نفسه.")
        self._open(path)
