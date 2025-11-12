import asyncio
import json
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test_lesson_details():
    print("[*] Testing get_lesson_details()...")
    print("=" * 60)

    async with StudiePlusScraper() as scraper:
        # Test 1: Fysik A lesson with homework
        print("\n[TEST 1] Fysik A (2025-11-10 12:00-13:00) - has homework")
        print("-" * 60)

        try:
            details = await scraper.get_lesson_details(
                date="2025-11-10",
                time="12:00-13:00"
            )

            print(f"\nLesson Details:")
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
                print(f"\nHomework text:")
                print(f"{details['homework'][:200]}...")

            if details['note']:
                print(f"\nNote text:")
                print(f"{details['note'][:200]}...")

            # Save to JSON
            with open("lesson_details_test.json", "w", encoding="utf-8") as f:
                json.dump(details, f, indent=2, ensure_ascii=False)

            print("\n[+] Test 1 passed! Details saved to lesson_details_test.json")

        except Exception as e:
            print(f"\n[!] Test 1 failed: {e}")

        # Test 2: Studievalg lesson with note
        print("\n" + "=" * 60)
        print("[TEST 2] Studievalg (2025-11-10 10:30-11:30) - has note")
        print("-" * 60)

        try:
            details = await scraper.get_lesson_details(
                date="2025-11-10",
                time="10:30-11:30"
            )

            print(f"\nLesson Details:")
            print(f"Subject: {details['subject']}")
            print(f"Has homework: {details['has_homework']}")
            print(f"Has note: {details['has_note']}")

            if details['note']:
                print(f"\nNote text:")
                print(f"{details['note'][:200]}...")

            print("\n[+] Test 2 passed!")

        except Exception as e:
            print(f"\n[!] Test 2 failed: {e}")

    print("\n" + "=" * 60)
    print("[+] All tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_lesson_details())
