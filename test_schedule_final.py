import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test():
    print("[*] Testing schedule homework extraction...")

    async with StudiePlusScraper() as scraper:
        # Test schedule homework
        schedule_hw = await scraper.get_schedule_homework()

        print(f"\n{'='*60}")
        print(f"SCHEDULE HOMEWORK ({len(schedule_hw)} found)")
        print(f"{'='*60}\n")

        for i, lesson in enumerate(schedule_hw, 1):
            print(f"{i}. {lesson['subject']} ({lesson['time']})")
            print(f"   Teacher: {lesson['teacher']} | Room: {lesson['room']}")
            print(f"   Type: {lesson['type']}")
            if lesson['homework']:
                print(f"   Homework: {lesson['homework'][:100]}...")
            if lesson['note']:
                print(f"   Note: {lesson['note'][:100]}...")
            print()


if __name__ == "__main__":
    asyncio.run(test())
