"""ملف الامتحان الجاهز (.mexam): الأسئلة والفروع والدرجات والتعليمات، لنقلها بين الحواسيب أو استيرادها دفعة واحدة."""
from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path

from .errors import AppError
from .exams import MAX_ANSWER_LINES, ExamStore

FORMAT = "musahhih-exam"
VERSION = 1


def from_store(store: ExamStore, exam_id: int) -> dict:
    exam = store.get_exam(exam_id)
    return {
        "format": FORMAT, "version": VERSION,
        "name": exam.name, "subject": exam.subject, "total_marks": exam.total_marks,
        "duration_minutes": exam.duration_minutes, "answer_count": exam.answer_count,
        "instructions": exam.instructions,
        "questions": [
            {"intro": q.intro, "parts": [
                {"text": p.text, "max_marks": p.max_marks, "answer_lines": p.answer_lines,
                 "image": base64.b64encode(p.image).decode("ascii") if p.image else None}
                for p in q.parts]}
            for q in store.questions(exam_id)
        ],
    }


def write(path: Path | str, data: dict) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def read(path: Path | str) -> dict:
    """يقرأ الملف ويتحقق من سلامته؛ كل خلل يرفع AppError برسالة عربية."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise AppError("الملف غير موجود.") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise AppError("تعذر قراءة الملف. تأكد أنه ملف امتحان جاهز (.mexam) سليم.") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise AppError("هذا الملف ليس ملف امتحان من «مصحّح أحمد».")
    if not isinstance(data.get("version"), int) or data["version"] > VERSION:
        raise AppError("ملف الامتحان أحدث من هذا البرنامج. حدّث البرنامج ثم أعد المحاولة.")
    try:
        questions = data["questions"]
        if not questions:
            raise ValueError
        for q in questions:
            if not q["parts"]:
                raise ValueError
            for p in q["parts"]:
                if float(p["max_marks"]) <= 0 or not 0 <= int(p["answer_lines"]) <= MAX_ANSWER_LINES:
                    raise ValueError
                if p.get("image"):
                    base64.b64decode(p["image"], validate=True)
        str(data["name"]), str(data["subject"]), float(data["total_marks"])
    except (KeyError, TypeError, ValueError, binascii.Error):
        raise AppError("ملف الامتحان تالف أو ناقص.") from None
    return data


def import_exam(store: ExamStore, data: dict, section_id: int, exam_date: str, school_name: str = "",
                name: str | None = None, subject: str | None = None, total_marks: float | None = None,
                duration_minutes: int | None = None, answer_count: int | None = None,
                instructions: str | None = None) -> int:
    """ينشئ امتحاناً مسودة من الملف. القيم الممررة تتقدم على ما في الملف (عدّلها المستخدم في النافذة)."""
    exam_id = store.create_exam(
        name if name is not None else data["name"],
        subject if subject is not None else data["subject"],
        section_id, exam_date,
        total_marks if total_marks is not None else float(data["total_marks"]),
        duration_minutes if duration_minutes is not None else int(data.get("duration_minutes", 0)),
        school_name,
        answer_count=answer_count if answer_count is not None else int(data.get("answer_count", 0)),
        instructions=instructions if instructions is not None else data.get("instructions", ""),
    )
    try:
        for q in data["questions"]:
            question_id = store.add_question(exam_id, q.get("intro", ""))
            for p in q["parts"]:
                image = base64.b64decode(p["image"]) if p.get("image") else None
                store.add_part(question_id, p["text"], float(p["max_marks"]), int(p["answer_lines"]), image)
    except Exception:
        store.delete_exam(exam_id)
        raise
    return exam_id
