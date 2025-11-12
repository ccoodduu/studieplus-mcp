import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper
from bs4 import BeautifulSoup


async def analyze():
    async with StudiePlusScraper() as scraper:
        print("[*] Logging in...")
        await scraper.login()

        print("\n[*] Navigating to schedule...")
        schedule_link = await scraper.page.wait_for_selector("a:has-text('Skema')", timeout=10000)
        await schedule_link.click()
        await scraper.page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

        print("\n[*] Analyzing lesson structure...")

        # Get all lesson elements using JavaScript
        lessons_data = await scraper.page.evaluate("""() => {
            const lessons = [];

            // Find all lesson cells in the schedule
            const lessonCells = document.querySelectorAll('td[class*="lesson"], div[class*="lesson"], div[class*="skema"]');

            lessonCells.forEach((cell, index) => {
                const styles = window.getComputedStyle(cell);
                const bgColor = styles.backgroundColor;
                const text = cell.innerText.substring(0, 200);
                const classes = cell.className;

                if (text.trim().length > 5) {
                    lessons.push({
                        index: index,
                        backgroundColor: bgColor,
                        classes: classes,
                        text: text,
                        hasHomework: text.includes('Studieomr') || text.includes('lektie'),
                    });
                }
            });

            return lessons;
        }""")

        print(f"\n[+] Found {len(lessons_data)} lesson elements")

        for i, lesson in enumerate(lessons_data[:10]):  # Show first 10
            print(f"\n--- Lesson {i+1} ---")
            print(f"Background: {lesson['backgroundColor']}")
            print(f"Classes: {lesson['classes']}")
            print(f"Has homework indicator: {lesson['hasHomework']}")
            print(f"Text preview: {lesson['text'][:100]}...")

        # Save full data
        import json
        with open("lessons_analysis.json", "w", encoding="utf-8") as f:
            json.dump(lessons_data, f, indent=2, ensure_ascii=False)
        print("\n[+] Saved full analysis to lessons_analysis.json")

        print("\n[*] Keeping browser open for 30 seconds...")
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(analyze())
