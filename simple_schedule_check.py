import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test():
    async with StudiePlusScraper() as scraper:
        print("[*] Logging in...")
        await scraper.login()

        print(f"\n[*] Current URL after login: {scraper.page.url}")

        # Take screenshot
        await scraper.page.screenshot(path="current_page.png")
        print("[*] Screenshot saved to current_page.png")

        # Get visible text
        visible_text = await scraper.page.evaluate("() => document.body.innerText")
        print(f"\n[*] Visible text (first 500 chars):")
        print(visible_text[:500])

        # Get all div text content
        divs_text = await scraper.page.evaluate("""() => {
            const divs = document.querySelectorAll('div');
            return Array.from(divs).slice(0, 20).map(div => ({
                className: div.className,
                text: div.innerText ? div.innerText.substring(0, 100) : ''
            })).filter(d => d.text.length > 10);
        }""")

        print(f"\n[*] Found {len(divs_text)} divs with content:")
        for i, div in enumerate(divs_text[:10]):
            print(f"\n{i+1}. Class: {div['className']}")
            print(f"   Text: {div['text'][:80]}...")

        print("\n[*] Keeping browser open for 60 seconds so you can check...")
        print("[*] Press Ctrl+C to exit early")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(test())
