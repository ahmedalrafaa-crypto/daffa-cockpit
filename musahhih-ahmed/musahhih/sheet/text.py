"""أدوات النص والخط المشتركة بين ورقة الامتحان وطبقة الدرجات."""
from __future__ import annotations

import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QFontDatabase, QPainter

from .. import paths
from .geometry import PX_PER_MM

FONT_FAMILY = "Noto Naskh Arabic"
_fonts_loaded = False

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute
LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute
CENTER = Qt.AlignmentFlag.AlignHCenter


def px(mm: float) -> float:
    return mm * PX_PER_MM


def rect(x: float, y: float, w: float, h: float) -> QRectF:
    return QRectF(px(x), px(y), px(w), px(h))


def font(size_mm: float, bold: bool = False) -> QFont:
    """خط مضمَّن مع البرنامج بحجم محدد بالمليمتر (لا يعتمد على خطوط الحاسوب)."""
    global _fonts_loaded
    if not _fonts_loaded:
        for name in ("NotoNaskhArabic-Regular.ttf", "NotoNaskhArabic-Bold.ttf"):
            QFontDatabase.addApplicationFont(str(paths.assets_dir() / "fonts" / name))
        _fonts_loaded = True
    f = QFont(FONT_FAMILY)
    f.setPixelSize(round(px(size_mm)))
    f.setBold(bold)
    return f


# مقاطع لاتينية/رمزية (معادلات ووحدات) داخل نص عربي
_LTR = r"A-Za-z0-9Ͱ-Ͽ°-¾×÷⁰-₟←-⋿=+\-*/^_.,%<>()\[\]"
_RUN = re.compile(f"[{_LTR}](?:[{_LTR} ]*[{_LTR}])?")
_MEANINGFUL = re.compile(r"[A-Za-zͰ-Ͽ×÷←-⋿=+*/^<>]")
LRI, PDI = "⁦", "⁩"


_MARK_TAIL = re.compile(r"\s+\(\d+(?:\.\d+)?\)$")


def _trim(run: str) -> tuple[int, int]:
    """حدود المعادلة داخل المقطع: بلا ترقيم طرفي وبلا أقواس غير مغلقة.

    القوس غير المغلق يعود للجملة العربية المحيطة (مثل «(5 درجات)») فيُترك خارج العزل.
    """
    start, end = 0, len(run)
    while True:
        while end > start and run[end - 1] in " .,=":
            end -= 1
        while start < end and run[start] in " ,=":  # «=» الطرفية تتبع الطرف العربي من المعادلة
            start += 1
        mark = _MARK_TAIL.search(run, start, end)
        if mark:  # درجة البند «(4)» ليست من المعادلة؛ تبقى خارج العزل في نهاية السطر العربي
            end = mark.start()
            continue
        opened: list[int] = []
        stray_close = -1
        for i in range(start, end):
            if run[i] in "([":
                opened.append(i)
            elif run[i] in ")]":
                if opened:
                    opened.pop()
                elif stray_close < 0:
                    stray_close = i
        if opened:
            end = opened[0]
        elif stray_close >= 0:
            # يبقى الجزء الأطول من جانبي القوس الزائد
            if stray_close - start >= end - stray_close - 1:
                end = stray_close
            else:
                start = stray_close + 1
        else:
            return start, end


def isolate_formulas(text: str) -> str:
    """يعزل المعادلات كمقاطع من اليسار إلى اليمين حتى لا يقلب النص العربي ترتيبها.

    مثال: «احسب F = m × a» تبقى فيها المعادلة بترتيبها الصحيح.
    """
    def wrap(match: re.Match) -> str:
        run = match.group(0)
        start, end = _trim(run)
        core = run[start:end]
        if len(core) < 2 or not _MEANINGFUL.search(core):
            return run
        return f"{run[:start]}{LRI}{core}{PDI}{run[end:]}"

    return _RUN.sub(wrap, text)


def text_height(painter: QPainter, text: str, f: QFont, width_mm: float) -> float:
    """ارتفاع النص بالمليمتر عند لفّه ضمن العرض المعطى."""
    painter.setFont(f)
    flags = RIGHT | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap
    r = painter.boundingRect(QRectF(0, 0, px(width_mm), 1e7), int(flags), isolate_formulas(text))
    return r.height() / PX_PER_MM


def draw_text(painter: QPainter, text: str, f: QFont, x: float, y: float, w: float, h: float,
              align=RIGHT, valign=Qt.AlignmentFlag.AlignTop, wrap: bool = True) -> None:
    painter.setFont(f)
    flags = align | valign
    if wrap:
        flags |= Qt.TextFlag.TextWordWrap
    painter.drawText(rect(x, y, w, h), int(flags), isolate_formulas(text))
