import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test():
    async with StudiePlusScraper() as scraper:
        print("[*] Logging in...")
        await scraper.login()

        print(f"\n[*] Current URL: {scraper.page.url}")
        await asyncio.sleep(2)

        print("\n[*] Looking for ALL clickable elements in schedule...")

        # Try to find elements using JavaScript to get more info
        elements_info = await scraper.page.evaluate("""() => {
            const results = [];

            // Find all divs that might be lessons
            const allDivs = document.querySelectorAll('div');

            allDivs.forEach((div, index) => {
                const text = div.innerText || '';
                const style = window.getComputedStyle(div);
                const bgColor = style.backgroundColor;
                const classes = div.className;

                // Look for elements that might be lessons (have time info or subject names)
                if (text.includes(':') && text.length > 10 && text.length < 300) {
                    // Check if it's colored (not white/transparent)
                    if (bgColor !== 'rgba(0, 0, 0, 0)' && bgColor !== 'rgb(255, 255, 255)') {
                        results.push({
                            index: index,
                            text: text.substring(0, 150),
                            backgroundColor: bgColor,
                            classes: classes,
                            id: div.id || 'no-id'
                        });
                    }
                }
            });

            return results.slice(0, 20);  // First 20 candidates
        }""")

        print(f"\n[+] Found {len(elements_info)} potential lesson elements:")

        for i, elem in enumerate(elements_info):
            print(f"\n--- Element {i+1} ---")
            print(f"Background: {elem['backgroundColor']}")
            print(f"Classes: {elem['classes']}")
            print(f"ID: {elem['id']}")
            print(f"Text: {elem['text']}")

        # Save to file
        import json
        with open("lesson_elements_found.json", "w", encoding="utf-8") as f:
            json.dump(elements_info, f, indent=2, ensure_ascii=False)

        print("\n\n[*] Keeping browser open for 60 seconds...")
        print("[*] Please look at the colored lesson boxes in the schedule")
        print("[*] and tell me which element from the list above looks correct!")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(test())
