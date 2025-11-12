import asyncio
import json
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test_current_week():
    print("[*] Testing get_lesson_details() with current week...")
    print("=" * 60)

    async with StudiePlusScraper() as scraper:
        # First, get the current week's schedule to find lessons with homework/notes
        print("\n[STEP 1] Getting current week schedule...")
        lessons, week, year, dates = await scraper.parse_schedule(week_offset=0)

        print(f"Week: {week}, Year: {year}")
        print(f"Found {len(lessons)} total lessons")

        # Find lessons with homework or notes
        with_content = [l for l in lessons if l['has_homework'] or l['has_note']]
        print(f"Found {len(with_content)} lessons with homework/notes")

        if not with_content:
            print("[!] No lessons with homework/notes found in current week")
            return

        # Test with the first lesson that has content
        test_lesson = with_content[0]
        print(f"\n[STEP 2] Testing with: {test_lesson['subject']} ({test_lesson['date']} {test_lesson['time']})")
        print(f"Has homework: {test_lesson['has_homework']}, Has note: {test_lesson['has_note']}")

        try:
            details = await scraper.get_lesson_details(
                date=test_lesson['date'],
                time=test_lesson['time']
            )

            print(f"\n[SUCCESS] Lesson details retrieved:")
            print(f"ID: {details['id']}")
            print(f"Subject: {details['subject']}")
            print(f"Date: {details['date']} ({details['weekday']})")
            print(f"Time: {details['time']}")
            print(f"Teacher: {details['teacher']} | Room: {details['room']}")
            print(f"\nFlags:")
            print(f"- Has homework: {details['has_homework']}")
            print(f"- Has note: {details['has_note']}")
            print(f"- Has files: {details['has_files']}")

            if details['homework']:
                print(f"\nHomework text ({len(details['homework'])} chars):")
                print(f"{details['homework'][:300]}")
                if len(details['homework']) > 300:
                    print("...")

            if details['note']:
                print(f"\nNote text ({len(details['note'])} chars):")
                print(f"{details['note'][:300]}")
                if len(details['note']) > 300:
                    print("...")

            # Save to JSON
            with open("lesson_details_current.json", "w", encoding="utf-8") as f:
                json.dump(details, f, indent=2, ensure_ascii=False)

            print("\n[+] Test passed! Details saved to lesson_details_current.json")

        except Exception as e:
            print(f"\n[!] Test failed: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test_current_week())
