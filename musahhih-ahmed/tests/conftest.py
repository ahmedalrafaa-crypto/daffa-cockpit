import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from musahhih.core.db import open_db
from musahhih.core.roster import Roster


@pytest.fixture
def conn():
    connection = open_db(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def roster(conn):
    return Roster(conn)


@pytest.fixture
def section(roster):
    grade_id = roster.add_grade("الرابع العلمي")
    return roster.add_section(grade_id, "أ")
