"""
Live contract tests against the real StudiePlus API.

Goal: detect when StudiePlus changes their GWT structure. We assert on
SHAPE (types, regex, sanity) — not values — because the data changes all
the time.

Tests also print the current schedule, assignments, and notes/files for
one lesson, so you can quickly compare against the browser.

Run with:
    pytest tests/test_live.py

Skips automatically if credentials are missing in .env.
"""
from collections import defaultdict

from conftest import (
    SUB,
    assert_assignment_shape,
    assert_file_shape,
    assert_lesson_shape,
    banner,
    fmt_flags,
)


async def test_schedule_this_week(scraper):
    lessons, week_number, year, dates = await scraper.parse_schedule(week_offset=0)

    assert week_number.isdigit() and 1 <= int(week_number) <= 53
    assert year.isdigit() and len(year) == 4
    assert isinstance(lessons, list)
    assert lessons, "Got 0 lessons — is it a holiday, or is something broken?"

    for lesson in lessons:
        assert_lesson_shape(lesson)

    banner(f"SCHEDULE — Week {week_number}/{year}")
    by_date = defaultdict(list)
    for l in lessons:
        by_date[l["date"]].append(l)

    for date in sorted(by_date):
        day_lessons = sorted(by_date[date], key=lambda x: x["time"])
        weekday = day_lessons[0]["weekday"]
        print(f"\n{weekday} {date}")
        for l in day_lessons:
            print(
                f"  {l['time']:13} "
                f"{l['subject']:25} "
                f"{l['teacher']:25} "
                f"{l['room']:10} "
                f"{fmt_flags(l)}"
            )
    print(f"\nTotal: {len(lessons)} lessons")


async def test_assignments(scraper):
    open_assignments = await scraper.get_homework(only_open=True)
    all_assignments = await scraper.get_homework(only_open=False)

    assert isinstance(open_assignments, list)
    assert isinstance(all_assignments, list)
    assert len(all_assignments) >= len(open_assignments)

    for a in all_assignments:
        assert_assignment_shape(a)

    banner(f"ASSIGNMENTS — {len(open_assignments)} open, "
           f"{len(all_assignments)} total")
    for i, a in enumerate(open_assignments, 1):
        status = "submitted" if a["submitted"] else "not submitted"
        print(f"\n[{i}] {a['subject']} — {a['title']}")
        print(f"    Deadline: {a['deadline'] or '(none)'}")
        print(f"    Class:    {a['class']}")
        print(f"    Week:     {a['week']}")
        print(f"    Status:   {status}")
        print(f"    Time:     {a['hours_spent']}/{a['subject_budget_hours']} hours")


async def test_lesson_note_and_files(scraper):
    """Find a lesson where the file-fetching chain actually returns files,
    and print the note + files for it.

    Note: the schedule's `has_files` flag is set heuristically and produces
    false positives (lessons with `has_files=True` but no real files). We
    iterate until we find a lesson where `get_lesson_files_with_urls`
    actually returns something, so the test verifies the full chain.
    """
    target = None
    files = []
    for offset in (0, -1, 1, -2, 2):
        candidates, *_ = await scraper.parse_schedule(week_offset=offset)
        for lesson in candidates:
            if not lesson["has_files"]:
                continue
            fetched = scraper.get_lesson_files_with_urls(lesson["lesson_id"])
            if fetched:
                target = lesson
                files = fetched
                break
        if target:
            break

    if target is None:
        import pytest
        pytest.skip(
            "No lesson with actual fetchable files found within ±2 weeks "
            "(has_files=True is heuristic and may not match real attachments)"
        )

    assert_lesson_shape(target)
    for f in files:
        assert_file_shape(f)

    banner(
        f"LESSON — {target['subject']} "
        f"({target['weekday']} {target['date']} {target['time']})"
    )
    print(f"Teacher: {target['teacher']}")
    print(f"Room:    {target['room']}")
    print(f"ID:      {target['lesson_id']}")

    if target["homework"]:
        print(f"\n{SUB}\nHomework ({len(target['homework'])} chars):\n{SUB}")
        print(target["homework"])

    if target["note"]:
        print(f"\n{SUB}\nNote ({len(target['note'])} chars):\n{SUB}")
        print(target["note"])

    print(f"\n{SUB}\nFiles ({len(files)}):\n{SUB}")
    for f in files:
        print(f"  - {f['name']}")
        if f.get("url"):
            print(f"    {f['url']}")
        else:
            print(f"    (no URL — id={f['id']})")
