import pytest

from musahhih.core.numwords import in_words


@pytest.mark.parametrize("value, words", [
    (0, "صفر"), (1, "واحد"), (2, "اثنان"), (10, "عشرة"), (11, "أحد عشر"), (12, "اثنا عشر"),
    (19, "تسعة عشر"), (20, "عشرون"), (21, "واحد وعشرون"), (37, "سبعة وثلاثون"), (50, "خمسون"),
    (91, "واحد وتسعون"), (99, "تسعة وتسعون"), (100, "مئة"), (150, "مئة وخمسون"), (200, "مئتان"),
    (72.5, "اثنان وسبعون ونصف"), (0.5, "نصف"), (40.25, "أربعون وربع"), (9.75, "تسعة وثلاثة أرباع"),
    (72.3, "اثنان وسبعون فاصل ثلاثة"), (17.35, "سبعة عشر فاصل ثلاثة خمسة"),
])
def test_in_words(value, words):
    assert in_words(value) == words


def test_rejects_out_of_range():
    with pytest.raises(ValueError):
        in_words(-1)
    with pytest.raises(ValueError):
        in_words(1000)
