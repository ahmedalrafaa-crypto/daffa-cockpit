"""علامات التصحيح المطبوعة: ✓ للدرجة الكاملة، ✗ للصفر، و«نصف صح» (✓ يقطعها خط) لما بينهما.

العلامة لا يقررها البرنامج: تُشتق من الدرجة التي وضعها المدرّس للفرع.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from ..core.printing import HALF, RIGHT, WRONG, kind_for  # noqa: F401  (القاعدة في المنطق، والرسم هنا)
from . import geometry as g

GUTTER, OVER_ANSWER, OFF = "gutter", "answer", "off"
POSITIONS = {GUTTER: "بجانب خانة الدرجة", OVER_ANSWER: "فوق الإجابة (كبيرة)", OFF: "بدون علامات"}

GUTTER_SIZE = 4.0     # ملم: علامة صغيرة في الشريط (5 ملم) بين حافة الصفحة وخانة الدرجة
ANSWER_SIZE = 14.0    # ملم: علامة كبيرة فوق الإجابة كما يضعها المدرّس بالقلم


def gutter_center(box) -> tuple[float, float]:
    """مركز العلامة الصغيرة: يسار خانة الدرجة، في الشريط الفارغ بين حافة الصفحة والخانة."""
    box_x = g.GUTTER_X + (g.GUTTER_W - g.MARK_BOX_W) / 2
    # أقرب إلى حافة الصفحة قليلاً حتى تبقى مسافة واضحة عن إطار الخانة (لا يلمسه حتى مع سُمك القلم)
    return (g.CORNER_INSET + g.CORNER_SIZE + box_x) / 2 - 0.3, box.y + box.h / 2


def answer_center(answer_box) -> tuple[float, float]:
    """مركز العلامة الكبيرة: أسفل يسار مساحة الإجابة، أي في أسطر الكتابة لا فوق نص السؤال المطبوع،
    وفي الطرف الأيسر حيث تنتهي الأسطر العربية غالباً."""
    return g.CONTENT_X + ANSWER_SIZE * 0.8, answer_box.y + answer_box.h - ANSWER_SIZE * 0.75


def draw_annotation(painter: QPainter, a, color: str, px_per_mm: float, dx_mm: float = 0.0,
                    dy_mm: float = 0.0) -> None:
    """دائرة حول الخطأ أو خط تحته، كما رسمها المدرّس، بخط بعرض قلم أحمر عادي (0.5 ملم)."""
    k = px_per_mm
    pen = QPen(QColor(color))
    pen.setWidthF(0.5 * k)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    x1, y1, x2, y2 = (a.x1 + dx_mm) * k, (a.y1 + dy_mm) * k, (a.x2 + dx_mm) * k, (a.y2 + dy_mm) * k
    if a.kind == "circle":
        painter.drawEllipse(QRectF(QPointF(x1, y1), QPointF(x2, y2)))
    else:
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def draw_tick(painter: QPainter, kind: str, cx_mm: float, cy_mm: float, size_mm: float, color: str,
              px_per_mm: float) -> None:
    """يرسم العلامة بخطوط (لا بخط حروف) لتبدو واحدة في كل جهاز وطابعة."""
    k = px_per_mm
    s = size_mm
    pen = QPen(QColor(color))
    pen.setWidthF(max(0.7, s * 0.11) * k)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    def pt(dx: float, dy: float) -> QPointF:
        return QPointF((cx_mm + dx * s) * k, (cy_mm + dy * s) * k)

    if kind == WRONG:
        painter.drawLine(pt(-0.4, -0.4), pt(0.4, 0.4))
        painter.drawLine(pt(0.4, -0.4), pt(-0.4, 0.4))
        return
    path = QPainterPath(pt(-0.45, 0.0))          # ✓
    path.lineTo(pt(-0.12, 0.38))
    path.lineTo(pt(0.48, -0.42))
    painter.drawPath(path)
    if kind == HALF:   # «نصف صح»: خط أفقي قصير يقطع الذراع الطويلة (لا مائل، حتى لا تشبه ✗)
        painter.drawLine(pt(0.02, -0.02), pt(0.42, -0.02))
