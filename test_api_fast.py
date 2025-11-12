import asyncio
import time
from src.studieplus_scraper import api


async def test_api_speed():
    print("[*] Testing API speed with optimized delays...")
    print("=" * 60)

    # Test 1: get_homework_and_notes()
    print("\n[TEST 1] get_homework_and_notes()")
    start = time.time()

    result = await api.get_homework_and_notes(
        week_offset=0,
        days_ahead=7,
        include_details=True
    )

    elapsed = time.time() - start
    print(f"Found {result['count']} lessons with homework/notes")
    print(f"Time: {elapsed:.2f}s")

    if result['lessons']:
        lesson = result['lessons'][0]
        print(f"\nFirst lesson:")
        print(f"  Subject: {lesson['subject']}")
        print(f"  Date: {lesson['date']} ({lesson['weekday']})")
        print(f"  Time: {lesson['time']}")
        print(f"  Has homework: {lesson['has_homework']}")
        print(f"  Has note: {lesson['has_note']}")
        if lesson.get('homework'):
            print(f"  Homework preview: {lesson['homework'][:100]}...")
        if lesson.get('note'):
            print(f"  Note preview: {lesson['note'][:100]}...")

    print("\n" + "=" * 60)
    print(f"[+] Test complete! Total time: {elapsed:.2f}s")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_api_speed())
