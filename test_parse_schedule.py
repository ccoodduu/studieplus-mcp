import asyncio
import json
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test():
    print("[*] Testing parse_schedule()...")

    async with StudiePlusScraper() as scraper:
        print("\n[TEST 1] Current week (week_offset=0)")
        print("=" * 60)

        lessons, week, year, dates = await scraper.parse_schedule(week_offset=0)

        print(f"\nWeek: {week}, Year: {year}")
        print(f"Dates: {dates}")
        print(f"\nFound {len(lessons)} lessons:")

        for i, lesson in enumerate(lessons[:5], 1):
            print(f"\n{i}. {lesson['subject']} ({lesson['time']})")
            print(f"   ID: {lesson['id']}")
            print(f"   Date: {lesson['date']} ({lesson['weekday']})")
            print(f"   Teacher: {lesson['teacher']} | Room: {lesson['room']}")
            print(f"   Homework: {lesson['has_homework']} | Notes: {lesson['has_note']} | Files: {lesson['has_files']}")

        if len(lessons) > 5:
            print(f"\n... and {len(lessons) - 5} more lessons")

        # Save to JSON for inspection
        output = {
            "week": week,
            "year": year,
            "dates": dates,
            "lessons": lessons
        }

        with open("schedule_parsed.json", "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print("\n[+] Full schedule saved to schedule_parsed.json")

        # Test filtering
        print("\n[TEST 2] Filter lessons with homework or notes")
        print("=" * 60)

        with_content = [l for l in lessons if l['has_homework'] or l['has_note']]
        print(f"\nFound {len(with_content)} lessons with homework/notes:")

        for i, lesson in enumerate(with_content, 1):
            print(f"\n{i}. {lesson['subject']} - {lesson['date']} {lesson['time']}")
            print(f"   Homework: {lesson['has_homework']} | Notes: {lesson['has_note']}")


if __name__ == "__main__":
    asyncio.run(test())
