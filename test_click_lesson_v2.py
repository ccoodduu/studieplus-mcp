import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test():
    async with StudiePlusScraper() as scraper:
        print("[*] Logging in...")
        await scraper.login()

        print(f"\n[*] Current URL: {scraper.page.url}")
        await asyncio.sleep(2)

        print("\n[*] Looking for lesson boxes...")
        lesson_boxes = await scraper.page.query_selector_all('.well.well-small')

        print(f"[+] Found {len(lesson_boxes)} lesson boxes")

        if len(lesson_boxes) > 0:
            print("\n[*] Clicking on first lesson box...")
            await lesson_boxes[0].click()

            print("[*] Waiting for response...")
            await asyncio.sleep(2)

            # Don't take screenshot yet, just try to get content
            print("\n[*] Getting page content...")

            try:
                # Get visible text
                visible_text = await scraper.page.evaluate("() => document.body.innerText")

                print("\n[*] Visible text (first 1000 chars):")
                print(visible_text[:1000])

                # Save to file
                with open("lesson_popup_text.txt", "w", encoding="utf-8") as f:
                    f.write(visible_text)
                print("\n[+] Saved full text to lesson_popup_text.txt")

                # Try to get HTML
                content = await scraper.page.content()
                with open("lesson_popup.html", "w", encoding="utf-8") as f:
                    f.write(content)
                print("[+] HTML saved to lesson_popup.html")

            except Exception as e:
                print(f"[-] Error getting content: {e}")

            print("\n[*] Keeping browser open for 60 seconds...")
            print("[*] Please look at the browser and tell me what you see!")
            await asyncio.sleep(60)

        else:
            print("[-] No lesson boxes found!")


if __name__ == "__main__":
    asyncio.run(test())
