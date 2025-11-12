import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test():
    async with StudiePlusScraper() as scraper:
        homework = await scraper.get_homework()

        if homework:
            print("\n[*] Homework with row indices:")
            for i, hw in enumerate(homework, 1):
                print(f"{i}. {hw.get('title')} - Row: {hw.get('row_index')}")

            if homework[0].get('row_index'):
                print(f"\n[*] Testing assignment details for first assignment (row {homework[0]['row_index']})...")
                details = await scraper.get_assignment_details(homework[0]['row_index'])

                print(f"\n{'='*60}")
                print(f"ASSIGNMENT DETAILS")
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
                    print(f"\nDescription:\n{desc[:500]}{'...' if len(desc) > 500 else ''}")

                files = details.get('files', [])
                print(f"\nFiles ({len(files)}):")
                for file in files:
                    print(f"  - {file['name']}: {file['url']}")
                print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(test())
