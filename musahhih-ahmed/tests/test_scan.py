"""استيراد مسح محاكى: ترتيب عشوائي، دوران، ميل، تكرار، ورقة مجهولة."""
import random

import cv2
import numpy as np
import pymupdf
import pytest

from musahhih.core.errors import AppError
from musahhih.core.roster import Roster
from musahhih.core.scans import DUPLICATE, MATCHED, UNKNOWN, ScanStore
from musahhih.scan import align, importer
from musahhih.sheet import geometry as g
from musahhih.sheet import workflow


def _rasterize(pdf, dpi=150):
    out = []
    for page in pymupdf.open(pdf):
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
        rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        out.append(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return out


def _degrade(image, angle=0.0, rotate=0, shift=(0, 0), seed=1):
    """يحاكي المسح: ميل صغير، إزاحة، ضجيج، وربما دوران 180°."""
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    matrix[:, 2] += shift
    out = cv2.warpAffine(image, matrix, (w, h), borderValue=(235, 235, 235))
    if rotate:
        out = np.ascontiguousarray(np.rot90(out, rotate))
    noise = np.random.default_rng(seed).normal(0, 6, out.shape)
    return np.clip(out.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def _write_pdf(images, path):
    doc = pymupdf.open()
    for image in images:
        ok, jpg = cv2.imencode(".jpg", image)
        h, w = image.shape[:2]
        page = doc.new_page(width=w * 72 / 150, height=h * 72 / 150)
        page.insert_image(page.rect, stream=jpg.tobytes())
    doc.save(path)


@pytest.fixture
def setup(qapp, data_dir, store, conn, exam):
    sheets = workflow.approve(store, Roster(conn), exam)
    return exam, _rasterize(sheets), ScanStore(conn), store


def test_analyze_reads_code_and_aligns_to_canonical_a4(setup):
    exam, pages, scans, store = setup
    original = pages[0]
    result = align.analyze(_degrade(original, angle=2.0, shift=(14, -9)))
    assert result.code is not None and result.code.exam_id == exam and result.code.page == 1
    assert result.aligned and result.image.shape[:2] == (align.OUT_H, align.OUT_W)
    # بعد التقويم تقع علامات الزوايا حيث يتوقعها التخطيط (خطأ أقل من 1 ملم)
    gray = cv2.cvtColor(result.image, cv2.COLOR_BGR2GRAY)
    for x, y in g.corner_marks():
        cx, cy = round((x + g.CORNER_SIZE / 2) * align.PX_PER_MM), round((y + g.CORNER_SIZE / 2) * align.PX_PER_MM)
        r = round(0.8 * align.PX_PER_MM)
        assert gray[cy - r:cy + r, cx - r:cx + r].max() < 90


@pytest.mark.parametrize("rotate", [1, 2, 3])
def test_analyze_fixes_page_orientation(setup, rotate):
    exam, pages, scans, store = setup
    result = align.analyze(_degrade(pages[0], angle=-1.5, rotate=rotate))
    assert result.code is not None and result.aligned
    assert result.image.shape[:2] == (align.OUT_H, align.OUT_W)


def test_blank_page_is_unreadable(setup):
    result = align.analyze(np.full((1754, 1240, 3), 255, np.uint8))
    assert result.code is None and not result.aligned


def test_shuffled_batch_pdf_groups_every_student(setup, tmp_path):
    exam, pages, scans, store = setup
    students = store.exam_students(exam)
    per = len(pages) // len(students)
    order = list(range(len(pages)))
    random.Random(7).shuffle(order)
    scan_pdf = tmp_path / "batch.pdf"
    _write_pdf([_degrade(pages[i], angle=random.Random(i).uniform(-2, 2), rotate=2 if i % 4 == 0 else 0, seed=i)
                for i in order], scan_pdf)

    calls = []
    result = importer.import_files(scans, exam, [scan_pdf], lambda d, t: calls.append((d, t)) or True)
    assert (result.pages, result.matched, result.duplicate, result.unknown) == (len(pages), len(pages), 0, 0)
    assert result.misaligned == 0 and calls[-1] == (len(pages), len(pages))

    summary = scans.summary(exam)
    assert summary.complete == len(students) and summary.absent == 0
    # كل صفحة محفوظة لطالبها وصفحتها الصحيحين رغم الترتيب العشوائي
    for position, index in enumerate(order):
        scan = scans.pages(exam)[position]
        assert (scan.student_id, scan.page) == (students[index // per].student_id, index % per + 1)
        assert scan.path.exists() and scan.aligned
    scans.confirm(exam)
    assert scans.is_confirmed(exam)


def test_missing_page_duplicate_and_unknown(setup, tmp_path):
    exam, pages, scans, store = setup
    students = store.exam_students(exam)
    per = len(pages) // len(students)
    files = []
    # الطالب الأول: الصفحة الثانية ناقصة؛ الطالب الثاني غائب كلياً؛ الباقون كاملون
    for i, image in enumerate(pages):
        s, p = divmod(i, per)
        if (s == 0 and p == 1) or s == 1:
            continue
        path = tmp_path / f"s{i:02d}.png"
        cv2.imwrite(str(path), _degrade(image, angle=1.0, seed=i))
        files.append(path)
    dup = tmp_path / "dup.png"
    cv2.imwrite(str(dup), _degrade(pages[0], seed=99))          # نسخة ثانية من ورقة موجودة
    blank = tmp_path / "blank.png"
    cv2.imwrite(str(blank), np.full((1754, 1240, 3), 250, np.uint8))
    bad = tmp_path / "bad.png"
    bad.write_text("not an image")
    result = importer.import_files(scans, exam, files + [dup, blank, bad])
    assert (result.duplicate, result.unknown) == (1, 1) and result.failed_files == ["bad.png"]

    report = {r.student_id: r for r in scans.student_report(exam)}
    assert report[students[0].student_id].missing == [2]
    assert report[students[1].student_id].present == [] and report[students[1].student_id].missing == list(range(1, per + 1))
    with pytest.raises(AppError, match="غير معروفة"):
        scans.confirm(exam)
    unknown = scans.pages(exam, UNKNOWN)[0]
    scans.assign(unknown.id, students[0].student_id, 2)          # تعيين يدوي لورقة بلا QR
    assert scans.matched_page(exam, students[0].student_id, 2).id == unknown.id
    with pytest.raises(AppError, match="مكررة"):
        scans.confirm(exam)
    scans.delete_duplicates(exam)
    scans.confirm(exam)
    # بعد الاستيراد لا يجوز إلغاء الاعتماد
    with pytest.raises(AppError):
        store.unapprove(exam)
    # أي تغيير لاحق يلغي «تأكيد الاكتمال»
    scans.delete(scans.pages(exam, MATCHED)[0].id)
    assert not scans.is_confirmed(exam)


def test_wrong_exam_and_unapproved(setup, tmp_path, store, section, conn):
    exam, pages, scans, _ = setup
    other = store.create_exam("آخر", "م", section, "2026-01-01", 10)
    with pytest.raises(AppError, match="اعتمد"):
        importer.import_files(scans, other, [])
    path = tmp_path / "p.png"
    cv2.imwrite(str(path), pages[0])
    # ورقة معتمدة لامتحان آخر مقروءة لكنها ليست لهذا الامتحان
    store.add_part(store.add_question(other), "س", 10)
    workflow.approve(store, Roster(conn), other)
    result = importer.import_files(scans, other, [path])
    assert result.unknown == 1 and "امتحان آخر" in scans.pages(other)[0].note


def test_promote_duplicate_and_delete_promotes_next(setup, tmp_path):
    exam, pages, scans, store = setup
    first, second = tmp_path / "a.png", tmp_path / "b.png"
    cv2.imwrite(str(first), pages[0])
    cv2.imwrite(str(second), pages[0])
    importer.import_files(scans, exam, [first, second])
    a, b = scans.pages(exam)
    assert (a.status, b.status) == (MATCHED, DUPLICATE)
    scans.promote(b.id)
    assert (scans.get(a.id).status, scans.get(b.id).status) == (DUPLICATE, MATCHED)
    scans.delete(b.id)
    assert scans.get(a.id).status == MATCHED and not b.path.exists()
