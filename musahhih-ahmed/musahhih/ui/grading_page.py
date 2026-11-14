"""شاشة التصحيح اليدوي: سؤال واحد لطالب واحد في كل مرة، والحفظ فوري عند كل اعتماد."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from ..core.errors import AppError
from ..core.exams import ExamStore, format_marks, part_letter, question_title
from ..core.grading import GRADED, GradingStore
from ..core.roster import format_student_code
from ..core.scans import ScanStore
from ..core.settings import Settings
from ..scan import crops, importer
from . import dialogs

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫،,", "0123456789...")
CACHE_SIZE = 10


def parse_mark(text: str) -> float | None:
    """«٤٫٥» أو «4,5» أو «4.5» ← 4.5؛ النص الفارغ أو غير الرقمي ← None."""
    text = text.strip().translate(_DIGITS)
    try:
        return float(text) if text else None
    except ValueError:
        return None


def to_pixmap(image: np.ndarray) -> QPixmap:
    h, w = image.shape[:2]
    qimage = QImage(image.data, w, h, image.strides[0], QImage.Format.Format_BGR888)
    return QPixmap.fromImage(qimage.copy())


class ZoomView(QGraphicsView):
    """عرض الصورة مع التكبير (Ctrl + العجلة أو الأزرار) والتحريك بالسحب."""

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(Qt.GlobalColor.lightGray)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

    def show_pixmaps(self, pixmaps: list[QPixmap]) -> None:
        scene = self.scene()
        scene.clear()
        y = 0
        for pixmap in pixmaps:
            item = QGraphicsPixmapItem(pixmap)
            item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            item.setPos(0, y)
            scene.addItem(item)
            y += pixmap.height() + 12
        scene.setSceneRect(scene.itemsBoundingRect())
        self.fit_width()

    def fit_width(self) -> None:
        rect = self.scene().sceneRect()
        if rect.width() <= 0:
            return
        self.resetTransform()
        scale = (self.viewport().width() - 4) / rect.width()
        self.scale(scale, scale)
        self.centerOn(rect.center().x(), rect.top())

    def zoom(self, factor: float) -> None:
        self.scale(factor, factor)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        else:
            super().wheelEvent(event)


class MarkEdit(QLineEdit):
    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)


class PendingDialog(QDialog):
    def __init__(self, parent, items):
        super().__init__(parent)
        self.setWindowTitle("الإجابات غير المصححة")
        self.setMinimumSize(460, 480)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("انقر نقرتين على إجابة للانتقال إليها:"))
        self.list = QListWidget()
        for p in items:
            text = f"{question_title(p.question_index)} — {p.student.full_name}" + ("  (متخطّاة)" if p.skipped else "")
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, (p.question_index, p.student.student_id))
            self.list.addItem(item)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        layout.addWidget(self.list)
        close = QPushButton("إغلاق")
        close.clicked.connect(self.reject)
        layout.addWidget(close)

    def choice(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None


class GradingPage(QWidget):
    def __init__(self, store: ExamStore, scans: ScanStore, grading: GradingStore, settings: Settings):
        super().__init__()
        self.setObjectName("page")
        self.store, self.scans, self.grading, self.settings = store, scans, grading, settings
        self.exam_id: int | None = None
        self.questions, self.students, self.boxes = [], [], []
        self.qi = self.si = 0
        self.full_page = False
        self._cache: dict[tuple[int, int, bool], tuple[list[QPixmap], bool]] = {}
        self.edits: list[tuple[int, MarkEdit, float]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel("تصحيح الامتحانات")
        title.setObjectName("pageTitle")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(QLabel("الامتحان:"))
        self.exam_box = QComboBox()
        self.exam_box.setMinimumWidth(320)
        self.exam_box.currentIndexChanged.connect(lambda *_: self._load_exam())
        top.addWidget(self.exam_box)
        root.addLayout(top)
        self.info = QLabel()
        self.info.setObjectName("pageHint")
        self.info.setWordWrap(True)
        root.addWidget(self.info)

        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        # --- لوحة التحكم ---
        panel = QFrame()
        panel.setObjectName("card")
        panel.setFixedWidth(340)
        side = QVBoxLayout(panel)
        side.setContentsMargins(16, 14, 16, 14)
        side.setSpacing(8)
        side.addWidget(QLabel("السؤال:"))
        self.question_box = QComboBox()
        self.question_box.currentIndexChanged.connect(self._question_changed)
        side.addWidget(self.question_box)
        self.question_bar = QProgressBar()
        side.addWidget(self.question_bar)
        self.student_name = QLabel()
        self.student_name.setObjectName("panelTitle")
        self.student_name.setWordWrap(True)
        side.addWidget(self.student_name)
        self.student_info = QLabel()
        self.student_info.setObjectName("pageHint")
        side.addWidget(self.student_info)
        self.status = QLabel()
        self.status.setWordWrap(True)
        side.addWidget(self.status)
        self.marks_grid = QGridLayout()
        self.marks_grid.setVerticalSpacing(8)
        side.addLayout(self.marks_grid)
        self.approve_button = QPushButton("اعتماد والانتقال للتالي")
        self.approve_button.setToolTip("أو اضغط Enter في خانة الدرجة الأخيرة")
        self.approve_button.setObjectName("primary")
        self.approve_button.clicked.connect(self.approve_next)
        side.addWidget(self.approve_button)
        row = QHBoxLayout()
        self.prev_button = QPushButton("الطالب السابق")
        self.prev_button.clicked.connect(self.previous)
        self.skip_button = QPushButton("تخطٍّ")
        self.skip_button.setToolTip("ترك هذه الإجابة للعودة إليها لاحقاً")
        self.skip_button.clicked.connect(self.skip)
        row.addWidget(self.prev_button)
        row.addWidget(self.skip_button)
        side.addLayout(row)
        self.pending_button = QPushButton("قائمة غير المصحح")
        self.pending_button.clicked.connect(self.show_pending)
        side.addWidget(self.pending_button)
        side.addStretch()
        side.addWidget(QLabel("الإنجاز الكلي:"))
        self.total_bar = QProgressBar()
        side.addWidget(self.total_bar)
        body.addWidget(panel)

        # --- الصورة ---
        viewer = QVBoxLayout()
        tools = QHBoxLayout()
        for text, slot in (("تكبير +", lambda: self.view.zoom(1.25)), ("تصغير −", lambda: self.view.zoom(0.8)),
                           ("ملاءمة العرض", lambda: self.view.fit_width())):
            b = QPushButton(text)
            b.clicked.connect(slot)
            tools.addWidget(b)
        self.page_button = QPushButton("الصفحة كاملة")
        self.page_button.setCheckable(True)
        self.page_button.toggled.connect(self._toggle_page)
        tools.addWidget(self.page_button)
        tools.addStretch()
        self.image_note = QLabel()
        self.image_note.setStyleSheet("color: #b3392f;")
        tools.addWidget(self.image_note)
        viewer.addLayout(tools)
        self.view = ZoomView()
        viewer.addWidget(self.view, 1)
        body.addLayout(viewer, 1)
        self._set_enabled(False)

    # ---------- تحميل ----------
    def refresh(self) -> None:
        current = self.exam_box.currentData()
        self.exam_box.blockSignals(True)
        self.exam_box.clear()
        for e in self.store.list_exams():
            if e.approved and self.scans.summary(e.id).matched:
                self.exam_box.addItem(f"{e.name} — {e.subject} ({e.grade_name} / {e.section_name})", e.id)
        index = self.exam_box.findData(current)
        self.exam_box.setCurrentIndex(max(index, 0))
        self.exam_box.blockSignals(False)
        self._load_exam()

    def select_exam(self, exam_id: int) -> None:
        self.refresh()
        index = self.exam_box.findData(exam_id)
        if index >= 0:
            self.exam_box.setCurrentIndex(index)

    def _set_enabled(self, on: bool) -> None:
        for w in (self.question_box, self.approve_button, self.prev_button, self.skip_button, self.pending_button,
                  self.page_button):
            w.setEnabled(on)

    def _load_exam(self) -> None:
        self.exam_id = self.exam_box.currentData()
        self._cache.clear()
        self._clear_marks()
        self.view.show_pixmaps([])
        if self.exam_id is None:
            self.info.setText("لا توجد امتحانات مستوردة أوراقها. استورد الأوراق الممسوحة أولاً من «استيراد الأوراق».")
            self._set_enabled(False)
            return
        try:
            self.grading.check_ready(self.exam_id)
        except AppError as exc:
            self.info.setText(str(exc))
            self._set_enabled(False)
            return
        exam = self.store.get_exam(self.exam_id)
        self.questions = self.store.questions(self.exam_id)
        self.students = self.grading.students(self.exam_id)
        self.boxes = self.store.layout(self.exam_id)
        absent = self.grading.absent(self.exam_id)
        self.info.setText(
            f"{exam.grade_name} / شعبة {exam.section_name}   ·   الطلاب: {len(self.students) + len(absent)}"
            f"   ·   الحاضرون: {len(self.students)}   ·   الأوراق المستوردة: {self.scans.summary(self.exam_id).matched}"
            + (f"\nبلا أوراق (لا يُصحح لهم): {'، '.join(s.full_name for s in absent)}" if absent else "")
        )
        if not self.students:
            self._set_enabled(False)
            return
        self._set_enabled(True)
        self.question_box.blockSignals(True)
        self.question_box.clear()
        for i, q in enumerate(self.questions):
            self.question_box.addItem(f"{question_title(i)} ({format_marks(q.total)} درجة)", i)
        self.question_box.blockSignals(False)
        qi, si = self._saved_position()
        self.qi, self.si = qi, si
        self.question_box.blockSignals(True)
        self.question_box.setCurrentIndex(qi)
        self.question_box.blockSignals(False)
        self._show()

    def _position_key(self) -> str:
        return f"grading_position_{self.exam_id}"

    def _saved_position(self) -> tuple[int, int]:
        try:
            qi, si = (int(x) for x in self.settings.get(self._position_key(), "0,0").split(","))
        except ValueError:
            qi, si = 0, 0
        qi = qi if 0 <= qi < len(self.questions) else 0
        si = si if 0 <= si < len(self.students) else 0
        return qi, si

    def _save_position(self) -> None:
        self.settings.set(self._position_key(), f"{self.qi},{self.si}")

    # ---------- العرض ----------
    def _clear_marks(self) -> None:
        while self.marks_grid.count():
            w = self.marks_grid.takeAt(0).widget()
            if w:
                w.hide()              # يُخفى فوراً؛ الحذف الفعلي يتم لاحقاً
                w.setParent(None)
                w.deleteLater()
        self.edits = []

    def _images(self, si: int, qi: int, full: bool) -> tuple[list[QPixmap], bool]:
        key = (si, qi, full)
        if key not in self._cache:
            student = self.students[si]
            question = self.questions[qi]
            pixmaps, exact = [], True
            if full:
                pages = sorted({r.page for r in crops.question_regions(self.boxes, question.id)})
                for page in pages:
                    scan = self.scans.matched_page(self.exam_id, student.student_id, page)
                    image = importer.read_image(scan.path) if scan else None
                    if image is not None:
                        pixmaps.append(to_pixmap(image))
                    exact = exact and scan is not None
            else:
                for region, image, ok in crops.question_images(self.scans, self.exam_id, student.student_id,
                                                               self.boxes, question.id):
                    if image is not None:
                        pixmaps.append(to_pixmap(image))
                    exact = exact and ok
            if len(self._cache) >= CACHE_SIZE:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (pixmaps, exact)
        return self._cache[key]

    def _show(self) -> None:
        if not self.students:
            return
        student = self.students[self.si]
        question = self.questions[self.qi]
        exam = self.store.get_exam(self.exam_id)
        self.student_name.setText(student.full_name)
        self.student_info.setText(
            f"الرقم: {format_student_code(student.student_id)}   ·   الطالب {self.si + 1} من {len(self.students)}")
        pixmaps, exact = self._images(self.si, self.qi, self.full_page)
        self.view.show_pixmaps(pixmaps)
        if not pixmaps:
            self.image_note.setText("لا توجد صفحة ممسوحة لهذا السؤال عند الطالب")
        elif not exact and not self.full_page:
            self.image_note.setText("الورقة لم تُقوَّم بدقة؛ تُعرض كاملة")
        else:
            self.image_note.setText("")

        self._clear_marks()
        saved = self.grading.student_marks(self.exam_id, student.student_id)
        single = len(question.parts) == 1
        for row, part in enumerate(question.parts):
            # علامة RLM في البداية تُبقي السطر من اليمين لليسار حتى لو بدأ بحرف لاتيني (A)
            label = QLabel("الدرجة المستحقة:" if single else
                           f"\u200fالفرع {part_letter(row, exam.label_style)}:")
            edit = MarkEdit()
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            edit.setFixedWidth(80)
            mark = saved.get(part.id)
            if mark and mark.status == GRADED:
                edit.setText(format_marks(mark.value))
            edit.returnPressed.connect(self._enter_pressed)
            edit.textChanged.connect(lambda _t, e=edit, m=part.max_marks: self._validate_edit(e, m))
            self.marks_grid.addWidget(label, row, 0)
            self.marks_grid.addWidget(edit, row, 1)
            self.marks_grid.addWidget(QLabel(f"من {format_marks(part.max_marks)}"), row, 2)
            self.edits.append((part.id, edit, part.max_marks))
        states = [saved.get(p.id) for p in question.parts]
        if all(m and m.status == GRADED for m in states):
            self.status.setText("✓ مصحَّح — يمكنك تعديل الدرجة ثم الاعتماد")
            self.status.setStyleSheet("color: #2f8f83;")
        elif any(m and m.status == "skipped" for m in states):
            self.status.setText("متخطّى سابقاً")
            self.status.setStyleSheet("color: #b3392f;")
        else:
            self.status.setText("")
        self._update_progress()
        self._save_position()
        if self.edits:
            self.edits[0][1].setFocus()
        QTimer.singleShot(30, self._prefetch)

    def _prefetch(self) -> None:
        if self.exam_id is not None and self.si + 1 < len(self.students):
            try:
                self._images(self.si + 1, self.qi, self.full_page)
            except Exception:
                pass

    def _update_progress(self) -> None:
        question = self.questions[self.qi]
        done, total = self.grading.question_progress(self.exam_id, question)
        self.question_bar.setMaximum(max(total, 1))
        self.question_bar.setValue(done)
        self.question_bar.setFormat(f"صُحّح لـ {done} من {total}")
        done, total = self.grading.overall_progress(self.exam_id)
        self.total_bar.setMaximum(max(total, 1))
        self.total_bar.setValue(done)
        self.total_bar.setFormat(f"%p%  ({done} من {total} درجة)")

    @staticmethod
    def _validate_edit(edit: QLineEdit, maximum: float) -> bool:
        value = parse_mark(edit.text())
        ok = edit.text().strip() == "" or (value is not None and 0 <= value <= maximum + 1e-9)
        edit.setStyleSheet("" if ok else "border: 2px solid #b3392f;")
        return ok

    # ---------- الأفعال ----------
    def _enter_pressed(self) -> None:
        """Enter في خانة غير الأخيرة ينقل للتالية، وفي الأخيرة يعتمد."""
        sender = self.sender()
        widgets = [e for _, e, _ in self.edits]
        if sender in widgets and widgets.index(sender) < len(widgets) - 1:
            widgets[widgets.index(sender) + 1].setFocus()
        else:
            self.approve_next()

    def approve_next(self) -> None:
        if self.exam_id is None or not self.students:
            return
        values = {}
        for part_id, edit, maximum in self.edits:
            value = parse_mark(edit.text())
            if value is None:
                edit.setFocus()
                dialogs.error(self, "أدخل درجة كل فرع رقماً، أو اضغط «تخطٍّ» لتأجيل هذه الإجابة.")
                return
            if value < 0 or value > maximum + 1e-9:
                edit.setFocus()
                dialogs.error(self, f"الدرجة يجب أن تكون بين 0 و {format_marks(maximum)}.")
                return
            values[part_id] = value
        try:
            self.grading.save(self.exam_id, self.students[self.si].student_id, values)
        except AppError as exc:
            dialogs.error(self, str(exc))
            return
        self._advance()

    def skip(self) -> None:
        if self.exam_id is None:
            return
        self.grading.skip(self.exam_id, self.students[self.si].student_id, [p for p, _, _ in self.edits])
        self._advance()

    def _advance(self) -> None:
        """ينتقل لأول طالب بعد الحالي لم يُصحح سؤاله؛ فإن رجعتَ لتعديل درجة سابقة تعود حيث كنت."""
        question = self.questions[self.qi]
        nxt = self.grading.next_pending(self.exam_id, question, self.si)
        if nxt is not None:
            if nxt <= self.si:
                dialogs.info(self, "وصلت إلى آخر طالب. ستنتقل إلى أول إجابة لم تُصحح في هذا السؤال.", title="تنبيه")
            self.si = nxt
            self._show()
            return
        self._show()
        title = question_title(self.qi)
        if self.qi + 1 < len(self.questions):
            if dialogs.confirm(self, f"اكتمل تصحيح {title} لجميع الطلاب.\nهل تنتقل إلى {question_title(self.qi + 1)}؟",
                               yes="الانتقال", no="البقاء"):
                self.question_box.setCurrentIndex(self.qi + 1)
        else:
            pending = self.grading.pending(self.exam_id)
            if pending:
                dialogs.info(self, f"اكتمل {title}، وبقيت {len(pending)} إجابة غير مصححة في أسئلة أخرى. "
                                   "افتح «قائمة غير المصحح».")
            else:
                dialogs.info(self, "اكتمل تصحيح جميع الأسئلة لجميع الطلاب. الدرجات محفوظة.")

    def previous(self) -> None:
        if self.si > 0:
            self.si -= 1
            self._show()

    def _question_changed(self, index: int) -> None:
        if index < 0 or self.exam_id is None:
            return
        self.qi = index
        nxt = self.grading.next_pending(self.exam_id, self.questions[index], len(self.students) - 1)
        self.si = nxt if nxt is not None else 0
        self._show()

    def _toggle_page(self, on: bool) -> None:
        self.full_page = on
        self._show()

    def go_to(self, question_index: int, student_id: int) -> None:
        self.qi = question_index
        self.si = next(i for i, s in enumerate(self.students) if s.student_id == student_id)
        self.question_box.blockSignals(True)
        self.question_box.setCurrentIndex(question_index)
        self.question_box.blockSignals(False)
        self._show()

    def show_pending(self) -> None:
        items = self.grading.pending(self.exam_id)
        if not items:
            dialogs.info(self, "لا توجد إجابات غير مصححة.")
            return
        dialog = PendingDialog(self, items)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.choice():
            self.go_to(*dialog.choice())
