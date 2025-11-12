import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test():
    async with StudiePlusScraper() as scraper:
        print("[*] Logging in...")
        await scraper.login()

        print("\n[*] Looking for Schedule/Skema link...")

        # Try to find schedule link with common Danish terms
        try:
            # Wait a bit to see the page
            await asyncio.sleep(2)

            # Look for schedule link
            schedule_link = await scraper.page.wait_for_selector(
                "a:has-text('Skema'), a:has-text('Schedule'), a:has-text('Timetable')",
                timeout=10000
            )

            if schedule_link:
                print("[+] Found schedule link, clicking...")
                await schedule_link.click()
                await scraper.page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)

                await scraper.page.screenshot(path="schedule_page.png")
                print("[+] Screenshot saved to schedule_page.png")

                # Save HTML for analysis
                content = await scraper.page.content()
                with open("schedule_page.html", "w", encoding="utf-8") as f:
                    f.write(content)
                print("[+] Saved schedule HTML to schedule_page.html")

                print("\n[*] Waiting 30 seconds so you can see the page...")
                print("[*] Press Ctrl+C to exit early")
                await asyncio.sleep(30)

        except Exception as e:
            print(f"[-] Error: {e}")

            # Take screenshot of current page
            await scraper.page.screenshot(path="error_schedule.png")
            print("[*] Screenshot saved to error_schedule.png")

            # Save visible text
            visible_text = await scraper.page.evaluate("() => document.body.innerText")
            with open("visible_menu.txt", "w", encoding="utf-8") as f:
                f.write(visible_text)
            print("[+] Saved visible text to visible_menu.txt")

            print("\n[*] Waiting 30 seconds so you can navigate manually...")
            print("[*] Press Ctrl+C to exit early")
            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(test())
