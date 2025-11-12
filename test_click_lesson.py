import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test():
    async with StudiePlusScraper() as scraper:
        print("[*] Logging in...")
        await scraper.login()

        print(f"\n[*] Current URL: {scraper.page.url}")
        print("[*] Already on schedule page after login")

        await asyncio.sleep(2)

        print("\n[*] Looking for lesson boxes...")

        # Try to find lesson boxes (the colored ones with subject names)
        # From parsing we know they have class "well well-small"
        lesson_boxes = await scraper.page.query_selector_all('.well.well-small')

        print(f"[+] Found {len(lesson_boxes)} lesson boxes")

        if len(lesson_boxes) > 0:
            # Click on the first lesson
            print("\n[*] Clicking on first lesson box...")
            await lesson_boxes[0].click()

            print("[*] Waiting to see what happens...")
            await asyncio.sleep(3)

            # Take screenshot after click
            await scraper.page.screenshot(path="after_lesson_click.png")
            print("[+] Screenshot saved to after_lesson_click.png")

            # Get page content
            content = await scraper.page.content()
            with open("after_lesson_click.html", "w", encoding="utf-8") as f:
                f.write(content)
            print("[+] HTML saved to after_lesson_click.html")

            # Look for any popups or modals
            print("\n[*] Checking for popups/modals...")

            # Common modal/popup selectors
            modals = await scraper.page.query_selector_all('.modal, .popup, .dialog, [role="dialog"]')
            print(f"[*] Found {len(modals)} modal elements")

            # Get visible text to see what's showing
            visible_text = await scraper.page.evaluate("() => document.body.innerText")

            # Look for homework-related text in visible content
            if 'lektie' in visible_text.lower() or 'opgave' in visible_text.lower():
                print("\n[+] Found homework-related text!")
                # Find the specific section
                lines = visible_text.split('\n')
                for i, line in enumerate(lines):
                    if 'lektie' in line.lower() or 'opgave' in line.lower():
                        print(f"\nLine {i}: {line}")
                        # Print context (2 lines before and after)
                        for j in range(max(0, i-2), min(len(lines), i+3)):
                            if j != i:
                                print(f"  {lines[j]}")

            print("\n[*] Keeping browser open for 30 seconds so you can see...")
            print("[*] Press Ctrl+C to exit early")
            await asyncio.sleep(30)

        else:
            print("[-] No lesson boxes found!")
            await scraper.page.screenshot(path="no_lessons_found.png")

            print("\n[*] Keeping browser open for 30 seconds...")
            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(test())
