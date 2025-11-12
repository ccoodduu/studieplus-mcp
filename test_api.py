import asyncio
import json
from src.studieplus_scraper.api import get_full_schedule, get_homework_and_notes


async def test_api():
    print("[*] Testing API Layer...")
    print("=" * 60)

    # Test 1: Get full schedule
    print("\n[TEST 1] get_full_schedule()")
    print("-" * 60)

    schedule = await get_full_schedule(week_offset=0)

    print(f"Week: {schedule['week']}, Year: {schedule['year']}")
    print(f"Dates: {schedule['dates']}")
    print(f"Total lessons: {len(schedule['lessons'])}")

    print("\nFirst 3 lessons:")
    for i, lesson in enumerate(schedule['lessons'][:3], 1):
        print(f"\n{i}. {lesson['subject']} ({lesson['time']})")
        print(f"   Date: {lesson['date']} ({lesson['weekday']})")
        print(f"   Teacher: {lesson['teacher']} | Room: {lesson['room']}")
        print(f"   Homework: {lesson['has_homework']} | Notes: {lesson['has_note']}")

    # Test 2: Get homework and notes (without details)
    print("\n" + "=" * 60)
    print("[TEST 2] get_homework_and_notes(include_details=False)")
    print("-" * 60)

    homework = await get_homework_and_notes(
        week_offset=0,
        days_ahead=7,
        include_details=False  # Don't fetch details yet
    )

    print(f"\nFound {homework['count']} lessons with homework/notes in the next 7 days:")

    for i, lesson in enumerate(homework['lessons'], 1):
        print(f"\n{i}. {lesson['subject']} - {lesson['date']} {lesson['time']}")
        print(f"   Homework: {lesson['has_homework']} | Notes: {lesson['has_note']} | Files: {lesson['has_files']}")

    # Save results
    output = {
        "full_schedule": schedule,
        "homework_overview": homework
    }

    with open("api_test_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("[+] API test complete! Results saved to api_test_results.json")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_api())
