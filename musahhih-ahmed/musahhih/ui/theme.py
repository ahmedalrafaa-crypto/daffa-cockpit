"""المظهر العام: ألوان هادئة وخط عربي مريح."""

FONT_FAMILIES = ["Segoe UI", "Tahoma", "Noto Sans Arabic", "DejaVu Sans"]
FONT_SIZE_PT = 12

STYLE = """
QWidget { color: #1f2d3a; }
QDialog, QMessageBox { background: #f4f6f8; }
QMessageBox QLabel, QDialog QLabel { color: #1f2d3a; }
QMainWindow, #page { background: #f4f6f8; }
#sidebar { background: #1f3a4d; }
#appTitle { color: white; font-size: 20pt; font-weight: bold; padding: 18px 16px 0 16px; }
#appSubtitle { color: #a9c1d1; font-size: 10pt; padding: 0 16px 14px 16px; }
#sidebar QPushButton {
    color: #dce8ef; background: transparent; border: none; border-radius: 8px;
    padding: 11px 14px; margin: 2px 10px; text-align: right; font-size: 12pt;
}
#sidebar QPushButton:hover { background: #2b4d64; }
#sidebar QPushButton:checked { background: #2f8f83; color: white; font-weight: bold; }
#sidebar QPushButton:disabled { color: #6f8a9b; }
#sidebarNote { color: #8fa9ba; font-size: 9pt; padding: 12px 16px 4px 16px; }

#pageTitle { font-size: 19pt; font-weight: bold; color: #1f3a4d; }
#pageHint { color: #5b6b78; font-size: 11pt; }
#panelTitle { font-size: 13pt; font-weight: bold; color: #1f3a4d; }
#card { background: white; border: 1px solid #dde3e8; border-radius: 12px; }
#statNumber { font-size: 26pt; font-weight: bold; color: #2f8f83; }
#statLabel { color: #5b6b78; }

QPushButton {
    background: white; border: 1px solid #c5ced6; border-radius: 8px;
    padding: 8px 16px; min-height: 22px;
}
QPushButton:hover { background: #eef3f6; }
QPushButton:disabled { color: #a3adb5; background: #f1f3f5; }
QPushButton#primary { background: #2f8f83; color: white; border: none; font-weight: bold; }
QPushButton#primary:hover { background: #277a70; }
QPushButton#primary:disabled { background: #a9cfc9; color: white; }
QPushButton#danger { color: #b3392f; border-color: #e0b4af; }
QPushButton#danger:hover { background: #fbeceb; }
QPushButton#danger:disabled { color: #a3adb5; border-color: #c5ced6; }

QLineEdit, QComboBox {
    background: white; border: 1px solid #c5ced6; border-radius: 8px; padding: 7px 10px; min-height: 22px;
}
QPushButton#icon { padding: 8px 10px; }
QSpinBox, QDoubleSpinBox, QDateEdit { min-height: 30px; min-width: 90px; }
QPushButton#symbol { padding: 3px 0; min-width: 30px; font-size: 13pt; }
QPlainTextEdit {
    background: white; border: 1px solid #c5ced6; border-radius: 8px; padding: 6px 8px;
}
QComboBox::drop-down { border: none; width: 26px; }
QLineEdit:focus, QComboBox:focus { border-color: #2f8f83; }
QListWidget, QTableWidget, QTreeWidget {
    background: white; border: 1px solid #dde3e8; border-radius: 10px;
    alternate-background-color: #f7f9fb; outline: none;
}
QListWidget::item { padding: 10px 12px; }
QTreeWidget::item { padding: 7px 4px; }
QListWidget::item:selected, QTableWidget::item:selected, QTreeWidget::item:selected { background: #d6ece9; color: #1f2d3a; }
QProgressBar { border: 1px solid #c5ced6; border-radius: 6px; text-align: center; background: white; min-height: 20px; }
QProgressBar::chunk { background: #8fd0c7; border-radius: 5px; }
QHeaderView::section {
    background: #eaf0f3; border: none; border-bottom: 1px solid #dde3e8; padding: 8px; font-weight: bold;
}
"""
