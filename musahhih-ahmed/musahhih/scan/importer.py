"""استيراد ملفات المسح (PDF متعدد الصفحات أو صور) وتصنيف كل صفحة."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np
import pymupdf

from ..core.errors import AppError
from ..core.scans import DUPLICATE, MATCHED, UNKNOWN, ScanStore
from . import align

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
JPEG_QUALITY = 88


@dataclass
class ImportResult:
    pages: int = 0
    matched: int = 0
    duplicate: int = 0
    unknown: int = 0
    misaligned: int = 0
    cancelled: bool = False
    failed_files: list[str] | None = None


def encode_jpeg(image: np.ndarray) -> bytes:
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise AppError("تعذر ترميز صورة الورقة.")
    return data.tobytes()


def read_image(path: Path) -> np.ndarray | None:
    """قراءة تدعم المسارات العربية على Windows (cv2.imread لا يدعمها)."""
    try:
        data = np.frombuffer(Path(path).read_bytes(), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def count_pages(path: Path) -> int:
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as doc:
            return doc.page_count
    return 1


def iter_pages(path: Path) -> Iterator[tuple[str, np.ndarray]]:
    """يعطي (وصف المصدر، الصورة BGR) لكل صفحة في الملف."""
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as doc:
            for index, page in enumerate(doc, start=1):
                pix = page.get_pixmap(dpi=align.SCAN_DPI, colorspace=pymupdf.csRGB, alpha=False)
                rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                yield f"{path.name} — صفحة {index}", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    else:
        image = read_image(path)
        if image is None:
            raise ValueError(path.name)
        yield path.name, image


def import_files(scans: ScanStore, exam_id: int, files: list[Path | str],
                 progress: Callable[[int, int], bool] | None = None) -> ImportResult:
    """يستورد الملفات صفحةً صفحة. progress(تم، الكل) تعيد False لإيقاف الاستيراد."""
    exam = scans.exams.get_exam(exam_id)
    if not exam.approved:
        raise AppError("اعتمد الامتحان أولاً قبل استيراد أوراقه.")
    students = {s.student_id for s in scans.exams.exam_students(exam_id)}
    page_count = scans.exams.page_count(exam_id)
    files = [Path(f) for f in files]
    result = ImportResult(failed_files=[])
    totals = {}
    for f in files:
        try:
            if f.suffix.lower() not in IMAGE_TYPES | {".pdf"}:
                raise ValueError
            totals[f] = count_pages(f)
        except Exception:
            result.failed_files.append(f.name)
    total = sum(totals.values())
    done = 0
    for f in totals:
        try:
            for source, image in iter_pages(f):
                analysis = align.analyze(image)
                code, note = analysis.code, ""
                student_id = page = None
                if code is None:
                    note = "لم يُقرأ رمز QR"
                elif code.exam_id != exam_id:
                    note = f"ورقة امتحان آخر (رقم {code.exam_id})"
                elif code.student_id not in students or not 1 <= code.page <= page_count:
                    note = "الرمز لا يطابق طلاب هذا الامتحان"
                else:
                    student_id, page = code.student_id, code.page
                scan = scans.add(exam_id, source, encode_jpeg(analysis.image), student_id, page,
                                 analysis.aligned and student_id is not None, note)
                result.pages += 1
                result.matched += scan.status == MATCHED
                result.duplicate += scan.status == DUPLICATE
                result.unknown += scan.status == UNKNOWN
                result.misaligned += scan.status != UNKNOWN and not scan.aligned
                done += 1
                if progress and not progress(done, total):
                    result.cancelled = True
                    return result
        except AppError:
            raise
        except Exception:
            result.failed_files.append(f.name)
            done = sum(totals[x] for x in list(totals)[: list(totals).index(f) + 1])
    return result


def assign_manually(scans: ScanStore, scan_id: int, student_id: int, page: int) -> None:
    """يعيّن ورقة مجهولة لطالبها، ويحاول تقويمها بمربعات الزوايا إن لم تكن مقوَّمة."""
    scan = scans.assign(scan_id, student_id, page)
    if scan.aligned:
        return
    image = read_image(scan.path)
    if image is None:
        return
    analysis = align.rectify_by_corners(image)
    if analysis.aligned:
        scans.replace_image(scan_id, encode_jpeg(analysis.image), True)


def rotate_half_turn(scans: ScanStore, scan_id: int) -> None:
    """يدوّر صورة ورقة غير مقوَّمة 180° (ورقة أُدخلت مقلوبة ولم يُقرأ رمزها)."""
    scan = scans.get(scan_id)
    image = read_image(scan.path)
    if image is None:
        raise AppError("تعذر قراءة صورة الورقة.")
    scans.replace_image(scan_id, encode_jpeg(np.ascontiguousarray(np.rot90(image, 2))), False)
