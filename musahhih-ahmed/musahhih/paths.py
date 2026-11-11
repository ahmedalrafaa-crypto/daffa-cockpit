"""مواقع ملفات البيانات.

البيانات تُحفظ خارج مجلد البرنامج عمداً، حتى لا يمسّها تحديث البرنامج
أو حذف مجلده. يمكن تغيير المكان بمتغير البيئة MUSAHHIH_DATA.
"""
from __future__ import annotations

import os
from pathlib import Path

DATA_ENV = "MUSAHHIH_DATA"
DATA_FOLDER_NAME = "MusahhihAhmed"


def data_dir() -> Path:
    override = os.environ.get(DATA_ENV)
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
