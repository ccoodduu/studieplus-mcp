import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test():
    async with StudiePlusScraper() as scraper:
        print("[*] Logging in...")
        await scraper.login()

        print(f"\n[*] Current URL: {scraper.page.url}")
        await asyncio.sleep(2)

        print("\n[*] Looking for lesson boxes...")

        # Find all lesson divs
        lesson_boxes = await scraper.page.query_selector_all('div.well.well-small')

        print(f"[+] Found {len(lesson_boxes)} lesson boxes")

        if len(lesson_boxes) > 0:
            print("\n[*] Clicking on first lesson...")
            await lesson_boxes[0].click()
            await asyncio.sleep(1)

            print("[*] Pressing Ctrl+Alt+N to open info panel...")
            await scraper.page.keyboard.press('Control+Alt+KeyN')

            print("[*] Waiting for info panel to open...")
            await asyncio.sleep(2)

            # Get content after opening panel
            visible_text = await scraper.page.evaluate("() => document.body.innerText")

            # Save full content first (before trying to print)
            with open("info_panel_text.txt", "w", encoding="utf-8") as f:
                f.write(visible_text)
            print("\n[+] Saved full text to info_panel_text.txt")

            # Print safely
            try:
                print("\n[*] Visible text (first 2000 chars):")
                print(visible_text[:2000])
            except UnicodeEncodeError:
                print("[*] Text contains unicode characters, check file instead")

            # Save HTML
            content = await scraper.page.content()
            with open("info_panel.html", "w", encoding="utf-8") as f:
                f.write(content)
            print("[+] HTML saved to info_panel.html")

            # Look for homework/notes sections
            if 'lektie' in visible_text.lower() or 'note' in visible_text.lower():
                print("\n[+] Found homework/notes content!")

            print("\n[*] Keeping browser open for 60 seconds...")
            print("[*] You should see the info panel now!")
            await asyncio.sleep(60)

        else:
            print("[-] No lesson boxes found")
            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(test())
