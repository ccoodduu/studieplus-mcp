"""
Shared test fixtures and helpers for live contract tests.

Tests log in with credentials from .env and call the real StudiePlus API.
The point is to detect when StudiePlus changes their GWT structure — we assert
on shape (types, ranges, sane-looking values) rather than specific values.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import pytest
from studieplus_scraper.requests_scraper import StudiePlusRequestsScraper


@pytest.fixture(scope="session")
def scraper():
    s = StudiePlusRequestsScraper()
    if not (s.username and s.password and s.school):
        pytest.skip(
            "STUDIEPLUS_USERNAME / STUDIEPLUS_PASSWORD / STUDIEPLUS_SCHOOL "
            "not set in .env"
        )
    assert s.login(), "Login failed — check credentials in .env"
    return s


# ------- shape helpers -------

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}(-\d{2}:\d{2})?$")
DEADLINE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$")

LEAKED_GWT_PREFIXES = ("dk.uddata.", "java.", "dk.gwt.", "com.google.")
GWT_SIGNATURE_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*/\d+$")


def looks_like_gwt_leak(value):
    """Return True if a string looks like a leaked GWT internal — a strong
    signal that the deserializer is reading from the wrong stack offset."""
    if not isinstance(value, str):
        return False
    if any(value.startswith(p) for p in LEAKED_GWT_PREFIXES):
        return True
    if GWT_SIGNATURE_RE.match(value):
        return True
    return False


def assert_lesson_shape(lesson: dict):
    expected_keys = {
        "id", "lesson_id", "file_container_id", "date", "weekday", "time",
        "subject", "teacher", "room",
        "has_homework", "has_note", "has_files",
        "homework", "note",
    }
    missing = expected_keys - lesson.keys()
    assert not missing, f"Lesson missing fields: {missing}"

    assert isinstance(lesson["lesson_id"], int) and lesson["lesson_id"] >= 0
    assert DATE_RE.match(lesson["date"]), f"Bad date: {lesson['date']!r}"
    assert TIME_RE.match(lesson["time"]), f"Bad time: {lesson['time']!r}"

    for f in ("has_homework", "has_note", "has_files"):
        assert isinstance(lesson[f], bool), \
            f"{f} must be bool, got {type(lesson[f]).__name__}"

    for f in ("subject", "teacher", "room", "homework", "note", "weekday"):
        assert isinstance(lesson[f], str), \
            f"{f} must be str, got {type(lesson[f]).__name__}"
        assert not looks_like_gwt_leak(lesson[f]), \
            f"{f}={lesson[f]!r} looks like a GWT internal — parser misaligned?"


def assert_assignment_shape(a: dict):
    expected_keys = {
        "container_id", "opgave_id", "subject", "title", "description",
        "deadline", "subject_budget_hours", "hours_spent", "class", "week",
        "submitted", "submission_date",
    }
    missing = expected_keys - a.keys()
    assert not missing, f"Assignment missing fields: {missing}"

    assert isinstance(a["submitted"], bool)
    for f in ("subject", "title", "description", "class"):
        assert isinstance(a[f], str)
        assert not looks_like_gwt_leak(a[f]), \
            f"{f}={a[f]!r} looks like a GWT internal — parser misaligned?"

    if a["deadline"]:
        assert DEADLINE_RE.match(a["deadline"]), \
            f"deadline={a['deadline']!r} does not match 'dd.mm.yyyy hh:mm'"


def assert_file_shape(f: dict):
    assert "name" in f and isinstance(f["name"], str) and f["name"]
    assert "id" in f and isinstance(f["id"], int) and f["id"] > 0
    if f.get("url"):
        assert f["url"].startswith("https://"), f"Suspicious URL: {f['url']!r}"


# ------- pretty printing -------

BAR = "=" * 70
SUB = "-" * 70


def banner(title: str):
    print()
    print(BAR)
    print(title)
    print(BAR)


def fmt_flags(lesson: dict) -> str:
    flags = []
    if lesson.get("has_homework"): flags.append("homework")
    if lesson.get("has_note"): flags.append("note")
    if lesson.get("has_files"): flags.append("files")
    return f"[{', '.join(flags)}]" if flags else ""
