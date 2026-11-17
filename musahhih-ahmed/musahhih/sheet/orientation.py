"""صفحة تحديد اتجاه الورق في الطابعة: صفحتان بسهم «أعلى الصفحة» ورقمين كبيرين 1 و 2."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPolygonF

from . import geometry as g
from .render import open_pdf
from .text import CENTER, draw_text, font, px


def write_orientation_test(path: Path | str) -> None:
    writer, painter = open_pdf(path, "تحديد اتجاه الورق")
    try:
        for number in (1, 2):
            if number == 2:
                writer.newPage()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#000000"))
            cx = g.PAGE_W / 2
            # سهم كبير نحو أعلى الصفحة
            arrow = QPolygonF([QPointF(px(cx), px(20)), QPointF(px(cx - 22), px(52)), QPointF(px(cx - 8), px(52)),
                               QPointF(px(cx - 8), px(90)), QPointF(px(cx + 8), px(90)), QPointF(px(cx + 8), px(52)),
                               QPointF(px(cx + 22), px(52))])
            painter.drawPolygon(arrow)
            painter.setPen(QColor("#000000"))
            draw_text(painter, "أعلى الصفحة", font(9, True), 20, 95, g.PAGE_W - 40, 16, CENTER, wrap=False)
            draw_text(painter, str(number), font(70, True), 20, 115, g.PAGE_W - 40, 80, CENTER, wrap=False)
            draw_text(painter, f"الصفحة {number} من ملف الاختبار", font(7, True), 20, 200, g.PAGE_W - 40, 14,
                      CENTER, wrap=False)
            draw_text(painter, "الطابعة طبعت على هذا الوجه من الورقة", font(6), 20, 222, g.PAGE_W - 40, 12, CENTER,
                      wrap=False)
            draw_text(painter, "ارجع إلى البرنامج وأجب عن الأسئلة الثلاثة", font(5), 20, 240, g.PAGE_W - 40, 10, CENTER,
                      wrap=False)
    finally:
        painter.end()
