"""النافذة الرئيسية: شريط جانبي للتنقل وصفحات المحتوى."""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import APP_NAME, APP_SUBTITLE, __version__
from ..core.exams import ExamStore
from ..core.roster import Roster
from ..core.settings import Settings
from .classes_page import ClassesPage
from .exam_editor_page import ExamEditorPage
from .exams_page import ExamsPage
from .home_page import HomePage
from .students_page import StudentsPage

# أقسام لم تُنفَّذ بعد: تظهر معطّلة مع رقم مرحلتها، حتى لا يوجد زر شكلي.
UPCOMING = [
    ("استيراد الأوراق", 3),
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
        self.store = ExamStore(conn)
        self.settings = Settings(conn)
        self.exams = ExamsPage(self.store, self.roster, self.settings)
        self.editor = ExamEditorPage(self.store, self.roster, self.settings)
        # محرّر الامتحان صفحة داخلية تُفتح من قائمة الامتحانات وليس لها زر في الشريط
        self.pages = [self.home, self.classes, self.students, self.exams, self.editor]

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
        for index, text in enumerate(("الرئيسية", "الصفوف والشعب", "إدارة الطلاب", "الامتحانات")):
            button = QPushButton(text)
            button.setCheckable(True)
            self.nav.addButton(button, index)
            side.addWidget(button)
        self.nav.idClicked.connect(self.show_page)
        new_exam = QPushButton("＋ إنشاء امتحان جديد")
        new_exam.clicked.connect(self._new_exam)
        side.addWidget(new_exam)

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
        self.exams.open_exam.connect(self._open_exam)
        self.editor.back.connect(lambda: self.show_page(3))
        self.show_page(0)

    def show_page(self, index: int) -> None:
        self.nav.button(min(index, 3)).setChecked(True)
        self.pages[index].refresh()
        self.stack.setCurrentIndex(index)

    def _open_section(self, section_id: int) -> None:
        self.show_page(2)
        self.students.show_section(section_id)

    def _new_exam(self) -> None:
        self.show_page(3)
        self.exams.new_exam()

    def _open_exam(self, exam_id: int) -> None:
        self.editor.load(exam_id)
        self.show_page(4)
