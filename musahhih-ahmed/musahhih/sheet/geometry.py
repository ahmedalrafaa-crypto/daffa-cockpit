"""ثوابت تخطيط ورقة A4 بالمليمتر (الأصل: الزاوية العليا اليسرى للصفحة).

هذه القيم جزء من «عقد» الورقة المطبوعة: تغييرها يغيّر مواضع الخانات في
الامتحانات الجديدة فقط، لأن مواضع كل امتحان معتمد محفوظة معه في القاعدة.
"""
PAGE_W = 210.0
PAGE_H = 297.0
DPI = 600
PX_PER_MM = DPI / 25.4

# العلامات المرجعية: مربعات سوداء في الزوايا الأربع
CORNER_SIZE = 5.0
CORNER_INSET = 8.0

# الرمز QR: أعلى يسار كل صفحة
QR_X = 16.0
QR_Y = 16.0
QR_SIZE = 20.0

# عمود الدرجات (يسار الصفحة) محجوز للدرجات فقط، ومنطقة المحتوى يمينه
GUTTER_X = 16.0
GUTTER_W = 18.0
MARK_BOX_W = 14.0
MARK_BOX_H = 9.0
CONTENT_X = 39.0
CONTENT_R = 194.0
CONTENT_W = CONTENT_R - CONTENT_X

FIRST_PAGE_TOP = 52.0   # بداية الأسئلة بعد الترويسة الكاملة
NEXT_PAGE_TOP = 40.0    # بداية الأسئلة في الصفحات التالية
CONTENT_BOTTOM = 279.0
FOOTER_Y = 283.0

FINAL_BOX = (40.0, 21.0, 24.0, 12.0)  # x, y, w, h لخانة الدرجة النهائية

LINE_STEP = 8.0         # المسافة بين أسطر الإجابة
QUESTION_BAND_H = 8.0
FIRST_PART_SHARE = 0.25   # نمط «أسئلة في كل صفحة»: حصة الأول (سؤالاً أو فرعاً) من الارتفاع المتاح


def corner_marks() -> list[tuple[float, float]]:
    """الزوايا العليا اليسرى لمربعات العلامات الأربعة."""
    lo, hi_x, hi_y = CORNER_INSET, PAGE_W - CORNER_INSET - CORNER_SIZE, PAGE_H - CORNER_INSET - CORNER_SIZE
    return [(lo, lo), (hi_x, lo), (lo, hi_y), (hi_x, hi_y)]
