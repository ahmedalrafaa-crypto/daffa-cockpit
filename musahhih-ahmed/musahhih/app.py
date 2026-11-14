"""نقطة تشغيل البرنامج."""
from __future__ import annotations

import sys
import traceback
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from . import APP_NAME, paths
from .core.db import open_db
from .ui import dialogs
from .ui.main_window import MainWindow
from .ui.theme import FONT_FAMILIES, FONT_SIZE_PT, apply_light_theme, stylesheet


def _log_error(text: str) -> None:
    try:
        with open(paths.logs_dir() / "errors.log", "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}\n")
    except OSError:
        pass


def _excepthook(exc_type, exc, tb) -> None:
    _log_error("".join(traceback.format_exception(exc_type, exc, tb)))
    dialogs.error(
        None,
        "حدث خطأ غير متوقع. بياناتك المحفوظة سليمة.\n"
        f"سُجّلت تفاصيل الخطأ في:\n{paths.logs_dir() / 'errors.log'}",
        title="خطأ",
    )


def create_app(argv: list[str]) -> QApplication:
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    apply_light_theme(app)
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(FONT_SIZE_PT)
    app.setFont(font)
    app.setStyleSheet(stylesheet())
    return app


def main() -> int:
    app = create_app(sys.argv)
    try:
        conn = open_db(paths.db_path())
    except Exception as exc:  # فشل فتح القاعدة يمنع العمل كلياً
        _log_error(traceback.format_exc())
        dialogs.error(None, f"تعذر فتح قاعدة البيانات:\n{exc}\n\nالمكان: {paths.db_path()}", title="خطأ")
        return 1
    sys.excepthook = _excepthook
    window = MainWindow(conn)
    window.show()
    code = app.exec()
    conn.close()
    return code
