"""كتابة الدرجة بالحروف العربية (للدرجة النهائية «رقماً وكتابةً»): 91 ← «واحد وتسعون»."""
from __future__ import annotations

UNITS = ["صفر", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة", "عشرة",
         "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر",
         "تسعة عشر"]
TENS = {2: "عشرون", 3: "ثلاثون", 4: "أربعون", 5: "خمسون", 6: "ستون", 7: "سبعون", 8: "ثمانون", 9: "تسعون"}
HUNDREDS = {1: "مئة", 2: "مئتان", 3: "ثلاثمئة", 4: "أربعمئة", 5: "خمسمئة", 6: "ستمئة", 7: "سبعمئة",
            8: "ثمانمئة", 9: "تسعمئة"}
FRACTIONS = {25: "ربع", 50: "نصف", 75: "ثلاثة أرباع"}


def _integer(n: int) -> str:
    if n < 20:
        return UNITS[n]
    if n < 100:
        tens, unit = divmod(n, 10)
        return TENS[tens] if unit == 0 else f"{UNITS[unit]} و{TENS[tens]}"
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return HUNDREDS[hundreds] if rest == 0 else f"{HUNDREDS[hundreds]} و{_integer(rest)}"
    raise ValueError("الدرجة أكبر من 999")


def in_words(value: float) -> str:
    """72.5 ← «اثنان وسبعون ونصف»، 0.5 ← «نصف»، 72.3 ← «اثنان وسبعون فاصل ثلاثة»."""
    if value < 0:
        raise ValueError("الدرجة لا تكون سالبة")
    hundredths = round(value * 100)
    whole, part = divmod(hundredths, 100)
    if part == 0:
        return _integer(whole)
    if part in FRACTIONS:
        return FRACTIONS[part] if whole == 0 else f"{_integer(whole)} و{FRACTIONS[part]}"
    digits = f"{part:02d}".rstrip("0")
    return f"{_integer(whole)} فاصل " + " ".join(UNITS[int(d)] for d in digits)
