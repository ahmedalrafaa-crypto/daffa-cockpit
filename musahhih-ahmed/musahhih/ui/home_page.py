"""الصفحة الرئيسية: ملخص البيانات والانتقال السريع."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import APP_NAME, APP_SUBTITLE, paths
from ..core.roster import Roster


class HomePage(QWidget):
    open_classes = Signal()
    open_students = Signal()

    def __init__(self, roster: Roster):
        super().__init__()
        self.setObjectName("page")
        self.roster = roster
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel(f"{APP_NAME} — {APP_SUBTITLE}")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        stats = QHBoxLayout()
        stats.setSpacing(16)
        self.numbers: list[QLabel] = []
        for label in ("الصفوف الدراسية", "الشعب", "الطلاب"):
            card = QFrame()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.setContentsMargins(20, 16, 20, 16)
            number = QLabel("0")
            number.setObjectName("statNumber")
            number.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption = QLabel(label)
            caption.setObjectName("statLabel")
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(number)
            box.addWidget(caption)
            self.numbers.append(number)
            stats.addWidget(card)
        root.addLayout(stats)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        classes = QPushButton("إدارة الصفوف والشعب")
        classes.setObjectName("primary")
        classes.clicked.connect(self.open_classes)
        students = QPushButton("إدارة الطلاب")
        students.setObjectName("primary")
        students.clicked.connect(self.open_students)
        folder = QPushButton("فتح مجلد البيانات")
        folder.clicked.connect(self._open_data_folder)
        actions.addWidget(classes)
        actions.addWidget(students)
        actions.addStretch()
        actions.addWidget(folder)
        root.addLayout(actions)

        self.hint = QLabel()
        self.hint.setObjectName("pageHint")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        location = QLabel(f"تُحفظ بياناتك في: {paths.data_dir()}")
        location.setObjectName("pageHint")
        location.setWordWrap(True)
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addStretch()
        root.addWidget(location)

    def refresh(self) -> None:
        grades, sections, students = self.roster.totals()
        for label, value in zip(self.numbers, (grades, sections, students)):
            label.setText(str(value))
        if grades == 0:
            self.hint.setText("ابدأ بإضافة صفوفك وشعبك من «الصفوف والشعب»، ثم أضف الطلاب أو استوردهم من Excel.")
        elif students == 0:
            self.hint.setText("الخطوة التالية: أضف طلاب كل شعبة يدوياً أو استوردهم من ملف Excel.")
        else:
            self.hint.setText("")

    def _open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data_dir())))
