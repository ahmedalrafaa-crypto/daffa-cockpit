"""تحليل صورة ورقة ممسوحة: قراءة QR، تصحيح الاتجاه، وتقويمها على مقاس A4 بالعلامات المرجعية.

الصورة الناتجة «قانونية»: 200 نقطة/إنش، أصلها الزاوية العليا اليسرى للورقة، فكل موضع
بالمليمتر في تخطيط الامتحان يقابله مباشرة بكسل = مليمتر × PX_PER_MM.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..core import qr_payload
from ..core.qr_payload import SheetCode
from ..sheet import geometry as g

SCAN_DPI = 200
PX_PER_MM = SCAN_DPI / 25.4
OUT_W = round(g.PAGE_W * PX_PER_MM)
OUT_H = round(g.PAGE_H * PX_PER_MM)
WHITE = (255, 255, 255)

_QR_MM = np.float32([
    [g.QR_X, g.QR_Y], [g.QR_X + g.QR_SIZE, g.QR_Y],
    [g.QR_X + g.QR_SIZE, g.QR_Y + g.QR_SIZE], [g.QR_X, g.QR_Y + g.QR_SIZE],
])
_MARK_CENTERS_MM = np.float32([[x + g.CORNER_SIZE / 2, y + g.CORNER_SIZE / 2] for x, y in g.corner_marks()])


@dataclass
class Analysis:
    code: SheetCode | None
    image: np.ndarray     # مقوَّمة إن نجحت المحاذاة، وإلا الصورة بعد تصحيح الاتجاه فقط
    aligned: bool


def _detect(gray: np.ndarray):
    try:
        text, points, _ = cv2.QRCodeDetector().detectAndDecode(gray)
    except cv2.error:
        return None
    if text and points is not None and qr_payload.decode(text):
        return text, points.reshape(4, 2).astype(np.float32)
    return None


def _find_qr(gray: np.ndarray):
    """يبحث في الصفحة كلها ثم في كل ركن مكبَّراً (للمسح الضعيف أو منخفض الدقة)."""
    found = _detect(gray)
    if found:
        return found
    h, w = gray.shape
    cw, ch = int(w * 0.45), int(h * 0.3)
    for x0, y0 in ((0, 0), (w - cw, h - ch), (w - cw, 0), (0, h - ch)):
        crop = cv2.resize(gray[y0:y0 + ch, x0:x0 + cw], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        for candidate in (crop, cv2.GaussianBlur(crop, (5, 5), 0)):
            found = _detect(candidate)
            if found:
                return found[0], found[1] / 2 + np.float32([x0, y0])
    return None


def _order(points: np.ndarray) -> np.ndarray:
    """يرتب أربع نقاط: أعلى يسار، أعلى يمين، أسفل يمين، أسفل يسار."""
    s, d = points.sum(axis=1), points[:, 0] - points[:, 1]
    return np.float32([points[s.argmin()], points[d.argmax()], points[s.argmax()], points[d.argmin()]])


def _find_mark(gray: np.ndarray, predicted: np.ndarray, scale: float, reach_mm: float):
    """مركز المربع الأسود الأقرب للموضع المتوقع، أو None."""
    h, w = gray.shape
    reach = int(reach_mm * scale)
    x0, y0 = max(0, int(predicted[0]) - reach), max(0, int(predicted[1]) - reach)
    x1, y1 = min(w, int(predicted[0]) + reach), min(h, int(predicted[1]) + reach)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    window = cv2.GaussianBlur(gray[y0:y1, x0:x1], (3, 3), 0)
    level, _ = cv2.threshold(window, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _, binary = cv2.threshold(window, min(level, 140), 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    expected = (g.CORNER_SIZE * scale) ** 2
    best, best_distance = None, None
    for contour in contours:
        area = cv2.contourArea(contour)
        if not 0.45 * expected <= area <= 1.9 * expected:
            continue
        (_, _), (bw, bh), _ = cv2.minAreaRect(contour)
        if min(bw, bh) <= 0 or max(bw, bh) / min(bw, bh) > 1.4 or area / (bw * bh) < 0.78:
            continue
        m = cv2.moments(contour)
        center = np.float32([m["m10"] / m["m00"] + x0, m["m01"] / m["m00"] + y0])
        distance = float(np.linalg.norm(center - predicted))
        if best_distance is None or distance < best_distance:
            best, best_distance = center, distance
    return best


def _warp(image: np.ndarray, found_mm: list, found_px: list, fallback: np.ndarray | None):
    """يقوّم الصورة. يعيد (الصورة، نجحت المحاذاة؟)."""
    size = (OUT_W, OUT_H)
    target = np.float32(found_mm) * PX_PER_MM if found_mm else None
    if len(found_px) == 4:
        matrix = cv2.getPerspectiveTransform(np.float32(found_px), target)
        return cv2.warpPerspective(image, matrix, size, flags=cv2.INTER_LINEAR, borderValue=WHITE), True
    if len(found_px) == 3:
        matrix = cv2.getAffineTransform(np.float32(found_px), target)
        return cv2.warpAffine(image, matrix, size, flags=cv2.INTER_LINEAR, borderValue=WHITE), True
    if fallback is not None:  # تقريب من QR وحده: يصلح للعرض ويُعلَّم للمراجعة
        inverse = cv2.invertAffineTransform(fallback) * PX_PER_MM
        return cv2.warpAffine(image, inverse, size, flags=cv2.INTER_LINEAR, borderValue=WHITE), False
    return image, False


def fit_page(image: np.ndarray) -> np.ndarray:
    """يصغّر صورة غير مقوَّمة لتقارب المقاس القانوني (للحفظ والعرض فقط)."""
    h, w = image.shape[:2]
    scale = min(OUT_W / w, OUT_H / h, 1.0) if w <= h else min(OUT_H / w, OUT_W / h, 1.0)
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return image


def rectify_by_corners(image: np.ndarray) -> Analysis:
    """تقويم ورقة بلا QR مقروء بالاعتماد على مربعات الزوايا، مع افتراض أن الصورة قائمة."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    scale = (w / g.PAGE_W + h / g.PAGE_H) / 2
    found_mm, found_px = [], []
    for center in _MARK_CENTERS_MM:
        hit = _find_mark(gray, center * np.float32([w / g.PAGE_W, h / g.PAGE_H]), scale, 16)
        if hit is not None:
            found_mm.append(center)
            found_px.append(hit)
    if len(found_px) < 3:
        return Analysis(None, fit_page(image), False)
    warped, ok = _warp(image, found_mm, found_px, None)
    return Analysis(None, warped, ok)


def analyze(image: np.ndarray) -> Analysis:
    """image بصيغة BGR. يقرأ الرمز ويصحح الاتجاه (أي دوران بمضاعفات 90°) ويقوّم الصفحة."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    found = _find_qr(gray)
    if not found:
        return Analysis(None, fit_page(image), False)
    text, points = found
    code = qr_payload.decode(text)

    # الرمز مطبوع أعلى يسار الورقة: موضعه في الصورة يحدد اتجاهها
    h, w = gray.shape
    cx, cy = points.mean(axis=0)
    left, top = cx < w / 2, cy < h / 2
    turns = 0 if (left and top) else 2 if (not left and not top) else 1 if (not left and top) else 3
    for _ in range(turns):  # تدوير 90° عكس عقارب الساعة: (x, y) ← (y, w-1-x)
        points = np.stack([points[:, 1], w - 1 - points[:, 0]], axis=1).astype(np.float32)
        w, h = h, w
    if turns:
        image = np.ascontiguousarray(np.rot90(image, turns))
        gray = np.ascontiguousarray(np.rot90(gray, turns))

    similarity, _ = cv2.estimateAffinePartial2D(_QR_MM, _order(points))
    if similarity is None:
        return Analysis(code, fit_page(image), False)
    scale = float(np.sqrt(abs(np.linalg.det(similarity[:, :2]))))
    found_mm, found_px = [], []
    for center in _MARK_CENTERS_MM:
        predicted = similarity @ np.float32([center[0], center[1], 1.0])
        hit = _find_mark(gray, predicted, scale, 12)
        if hit is not None:
            found_mm.append(center)
            found_px.append(hit)
    warped, ok = _warp(image, found_mm, found_px, similarity)
    return Analysis(code, warped, ok)
