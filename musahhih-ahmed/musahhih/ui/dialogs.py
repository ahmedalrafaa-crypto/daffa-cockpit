"""نوافذ حوار عربية بسيطة (رسائل، تأكيد، إدخال نص)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLineEdit, QMessageBox, QVBoxLayout, QWidget,
)


def _box(parent: QWidget | None, icon: QMessageBox.Icon, title: str, text: str) -> QMessageBox:
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    return box


def info(parent: QWidget | None, text: str, title: str = "تم") -> None:
    box = _box(parent, QMessageBox.Icon.Information, title, text)
    box.addButton("حسناً", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def error(parent: QWidget | None, text: str, title: str = "تنبيه") -> None:
    box = _box(parent, QMessageBox.Icon.Warning, title, text)
    box.addButton("حسناً", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def confirm(parent: QWidget | None, text: str, yes: str = "نعم", no: str = "إلغاء", title: str = "تأكيد") -> bool:
    box = _box(parent, QMessageBox.Icon.Question, title, text)
    yes_button = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
    no_button = box.addButton(no, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(no_button)
    box.setEscapeButton(no_button)
    box.exec()
    return box.clickedButton() is yes_button


class TextDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, label: str, text: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(label))
        self.edit = QLineEdit(text)
        self.edit.selectAll()
        layout.addWidget(self.edit)
        buttons = QDialogButtonBox()
        save = buttons.addButton("حفظ", QDialogButtonBox.ButtonRole.AcceptRole)
        save.setObjectName("primary")
        buttons.addButton("إلغاء", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def ask_text(parent: QWidget | None, title: str, label: str, text: str = "") -> str | None:
    """يعيد النص المدخل، أو None إذا ألغى المستخدم."""
    dialog = TextDialog(parent, title, label, text)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.edit.text()
