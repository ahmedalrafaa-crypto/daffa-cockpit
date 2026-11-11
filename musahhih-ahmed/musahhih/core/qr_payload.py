"""محتوى رمز QR على ورقة الطالب: MA1|امتحان|طالب|صفحة|تحقق."""
from __future__ import annotations

import zlib
from dataclasses import dataclass

PREFIX = "MA1"


@dataclass(frozen=True)
class SheetCode:
    exam_id: int
    student_id: int
    page: int

    def human(self) -> str:
        """صيغة مقروءة تُطبع بجانب الرمز لإدخالها يدوياً عند تعذر القراءة."""
        return f"{self.exam_id}-{self.student_id:05d}-{self.page}"


def _check(body: str) -> str:
    return f"{zlib.crc32(body.encode('ascii')) % 97:02d}"


def encode(code: SheetCode) -> str:
    body = f"{PREFIX}|{code.exam_id}|{code.student_id}|{code.page}"
    return f"{body}|{_check(body)}"


def decode(text: str) -> SheetCode | None:
    """يعيد None إذا لم يكن النص رمزاً صحيحاً من هذا البرنامج."""
    parts = text.strip().split("|")
    if len(parts) != 5 or parts[0] != PREFIX:
        return None
    body = "|".join(parts[:4])
    if parts[4] != _check(body) or not all(p.isascii() and p.isdigit() for p in parts[1:4]):
        return None
    exam_id, student_id, page = (int(p) for p in parts[1:4])
    if page < 1:
        return None
    return SheetCode(exam_id, student_id, page)
