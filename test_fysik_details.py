import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test():
    async with StudiePlusScraper() as scraper:
        homework = await scraper.get_homework()

        if homework:
            for hw in homework:
                if 'Fysik' in hw.get('subject', ''):
                    print(f"\nTesting Fysik assignment (row {hw['row_index']})...")
                    details = await scraper.get_assignment_details(hw['row_index'])

                    print(f"\n{'='*60}")
                    print(f"ASSIGNMENT DETAILS - FYSIK")
                    print(f"{'='*60}")
                    print(f"Title: {details.get('assignment_title', 'N/A')}")
                    print(f"Subject: {details.get('subject', 'N/A')}")
                    print(f"Student time: {details.get('student_time', 'N/A')}")
                    print(f"Responsible: {details.get('responsible', 'N/A')}")
                    print(f"Course: {details.get('course', 'N/A')}")
                    print(f"Evaluation form: {details.get('evaluation_form', 'N/A')}")
                    print(f"Groups: {details.get('groups', 'N/A')}")
                    print(f"Status: {details.get('submission_status', 'N/A')}")
                    print(f"Deadline: {details.get('deadline', 'N/A')}")

                    desc = details.get('description', '')
                    if desc:
                        print(f"\nDescription:\n{desc}")
                    else:
                        print("\nDescription: None")

                    files = details.get('files', [])
                    print(f"\nFiles ({len(files)}):")
                    for file in files:
                        print(f"  - {file['name']}: {file['url']}")
                    print(f"{'='*60}")
                    break


if __name__ == "__main__":
    asyncio.run(test())
