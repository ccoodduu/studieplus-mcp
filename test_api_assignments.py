import asyncio
from src.studieplus_scraper import api


async def test_assignments_via_api():
    print("[*] Testing assignment functions via API layer...")
    print("=" * 60)

    # Test 1: Get all assignments
    print("\n[TEST 1] get_all_assignments()")
    print("-" * 60)

    result = await api.get_all_assignments()

    print(f"Found {result['count']} assignments")

    if result['assignments']:
        print("\nFirst assignment:")
        assignment = result['assignments'][0]
        print(f"  Subject: {assignment['subject']}")
        print(f"  Title: {assignment['title']}")
        print(f"  Deadline: {assignment['deadline']}")
        print(f"  Row index: {assignment['row_index']}")

    # Test 2: Get upcoming assignments
    print("\n" + "=" * 60)
    print("[TEST 2] get_upcoming_assignments(days=14)")
    print("-" * 60)

    upcoming = await api.get_upcoming_assignments(days=14)

    print(f"Found {upcoming['count']} assignments due in next {upcoming['days']} days")

    # Test 3: Get assignments by subject
    if result['assignments']:
        test_subject = result['assignments'][0]['subject']

        print("\n" + "=" * 60)
        print(f"[TEST 3] get_assignments_by_subject('{test_subject}')")
        print("-" * 60)

        by_subject = await api.get_assignments_by_subject(test_subject)

        print(f"Found {by_subject['count']} assignments for {by_subject['subject']}")

    print("\n" + "=" * 60)
    print("[+] All tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_assignments_via_api())
