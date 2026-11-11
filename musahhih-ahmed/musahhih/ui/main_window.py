"""النافذة الرئيسية: شريط جانبي للتنقل وصفحات المحتوى."""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import APP_NAME, APP_SUBTITLE, __version__
from ..core.roster import Roster
from .classes_page import ClassesPage
from .home_page import HomePage
from .students_page import StudentsPage

# أقسام لم تُنفَّذ بعد: تظهر معطّلة مع رقم مرحلتها، حتى لا يوجد زر شكلي.
UPCOMING = [
    ("إنشاء امتحان جديد", 2),
    ("الامتحانات السابقة", 2),
    ("تصحيح الامتحانات", 4),
    ("سجل الدرجات", 5),
    ("إعدادات الطباعة", 6),
    ("النسخ الاحتياطي", 7),
]


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — {APP_SUBTITLE}")
        self.resize(1180, 740)
        self.setMinimumSize(1100, 640)
        self.roster = Roster(conn)

        self.home = HomePage(self.roster)
        self.classes = ClassesPage(self.roster)
        self.students = StudentsPage(self.roster)
        self.pages = [self.home, self.classes, self.students]

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(central)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(250)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 12)
        side.setSpacing(0)
        name = QLabel(APP_NAME)
        name.setObjectName("appTitle")
        subtitle = QLabel(APP_SUBTITLE)
        subtitle.setObjectName("appSubtitle")
        side.addWidget(name)
        side.addWidget(subtitle)

        self.nav = QButtonGroup(self)
        for index, text in enumerate(("الرئيسية", "الصفوف والشعب", "إدارة الطلاب")):
            button = QPushButton(text)
            button.setCheckable(True)
            self.nav.addButton(button, index)
            side.addWidget(button)
        self.nav.idClicked.connect(self.show_page)

        note = QLabel("أقسام قيد الإنجاز")
        note.setObjectName("sidebarNote")
        side.addWidget(note)
        for text, phase in UPCOMING:
            button = QPushButton(f"{text}  (المرحلة {phase})")
            button.setEnabled(False)
            side.addWidget(button)
        side.addStretch()
        version = QLabel(f"الإصدار {__version__}")
        version.setObjectName("sidebarNote")
        side.addWidget(version)

        self.stack = QStackedWidget()
        for page in self.pages:
            self.stack.addWidget(page)
        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)

        self.home.open_classes.connect(lambda: self.show_page(1))
        self.home.open_students.connect(lambda: self.show_page(2))
        self.classes.open_section.connect(self._open_section)
        self.show_page(0)

    def show_page(self, index: int) -> None:
        self.nav.button(index).setChecked(True)
        self.pages[index].refresh()
        self.stack.setCurrentIndex(index)

    def _open_section(self, section_id: int) -> None:
        self.show_page(2)
        self.students.show_section(section_id)
