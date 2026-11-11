"""مواقع ملفات البيانات.

البيانات تُحفظ خارج مجلد البرنامج عمداً، حتى لا يمسّها تحديث البرنامج
أو حذف مجلده. يمكن تغيير المكان بمتغير البيئة MUSAHHIH_DATA.
"""
from __future__ import annotations

import os
from pathlib import Path

DATA_ENV = "MUSAHHIH_DATA"
DATA_FOLDER_NAME = "MusahhihAhmed"


CONFIG_FILE = "data_location.txt"


def app_root() -> Path:
    return Path(__file__).resolve().parent.parent


def configured_location() -> str:
    """مكان البيانات من ملف data_location.txt بجانب البرنامج (سطر واحد، مثل D:\\MusahhihData)."""
    try:
        for line in (app_root() / CONFIG_FILE).read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                return line.strip().strip('"')
    except OSError:
        pass
    return ""


def data_dir() -> Path:
    override = os.environ.get(DATA_ENV) or configured_location()
    base = Path(override) if override else Path.home() / DATA_FOLDER_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "musahhih.db"


def backups_dir() -> Path:
    d = data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def exam_dir(exam_id: int) -> Path:
    d = data_dir() / "exams" / f"{exam_id:05d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def assets_dir() -> Path:
    return Path(__file__).resolve().parent / "assets"
