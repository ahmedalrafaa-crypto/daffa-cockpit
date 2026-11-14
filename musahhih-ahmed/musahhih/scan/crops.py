"""قصّ منطقة سؤال من صورة الورقة الممسوحة المقوَّمة، اعتماداً على مواضع الخانات المحفوظة مع الامتحان."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.exams import LayoutBox
from ..sheet import geometry as g
from . import align, importer

MARGIN_MM = 2.0


@dataclass(frozen=True)
class Region:
    page: int
    x: float
    y: float
    w: float
    h: float


def question_regions(boxes: list[LayoutBox], question_id: int) -> list[Region]:
    """منطقة السؤال في كل صفحة يظهر فيها (عنوانه وفروعه ومساحات إجابته)، بالمليمتر."""
    by_page: dict[int, list[LayoutBox]] = {}
    for b in boxes:
        if b.question_id == question_id:
            by_page.setdefault(b.page, []).append(b)
    regions = []
    for page in sorted(by_page):
        top = min(b.y for b in by_page[page]) - MARGIN_MM
        bottom = max(b.y + b.h for b in by_page[page]) + MARGIN_MM
        x0, x1 = g.GUTTER_X - MARGIN_MM, g.CONTENT_R + MARGIN_MM
        regions.append(Region(page, x0, max(0.0, top), x1 - x0, min(g.PAGE_H, bottom) - max(0.0, top)))
    return regions


def crop(image: np.ndarray, region: Region) -> np.ndarray:
    k = align.PX_PER_MM
    h, w = image.shape[:2]
    y0, y1 = max(0, round(region.y * k)), min(h, round((region.y + region.h) * k))
    x0, x1 = max(0, round(region.x * k)), min(w, round((region.x + region.w) * k))
    return np.ascontiguousarray(image[y0:y1, x0:x1])


def question_images(scans, exam_id: int, student_id: int, boxes: list[LayoutBox],
                    question_id: int) -> list[tuple[Region, np.ndarray | None, bool]]:
    """لكل منطقة: (المنطقة، الصورة أو None إن غابت الصفحة، هل هي مقصوصة بدقة).

    الورقة غير المقوَّمة تُعرض كاملة لأن مواضع الخانات عليها غير مضمونة.
    """
    out = []
    for region in question_regions(boxes, question_id):
        scan = scans.matched_page(exam_id, student_id, region.page)
        image = importer.read_image(scan.path) if scan else None
        if image is None:
            out.append((region, None, False))
        elif scan.aligned:
            out.append((region, crop(image, region), True))
        else:
            out.append((region, image, False))
    return out
