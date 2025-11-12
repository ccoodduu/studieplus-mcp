import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper


async def test():
    async with StudiePlusScraper() as scraper:
        print("[*] Logging in...")
        await scraper.login()

        print(f"\n[*] Current URL: {scraper.page.url}")
        await asyncio.sleep(2)

        print("\n[*] Finding all lesson elements with subject names...")

        # Use JavaScript to find ALL divs that look like lesson boxes
        lessons = await scraper.page.evaluate("""() => {
            const results = [];
            const allDivs = document.querySelectorAll('div');

            // Look for divs that contain subject names and time
            allDivs.forEach((div, idx) => {
                const text = div.innerText || '';
                const style = window.getComputedStyle(div);
                const bgColor = style.backgroundColor;

                // Check if text contains typical subject patterns and time
                const hasSubject = /Engelsk|Fysik|Matematik|Dansk|Studievalg|Kemi|Biologi|Historie/i.test(text);
                const hasTime = /\d{2}:\d{2}/.test(text);

                // Check if it's a colored lesson (not white/transparent)
                const isColored = bgColor !== 'rgba(0, 0, 0, 0)' &&
                                 bgColor !== 'rgb(255, 255, 255)' &&
                                 bgColor !== 'rgb(245, 245, 245)';  // Exclude very light gray

                if ((hasSubject || hasTime) && text.length > 10 && text.length < 500) {
                    results.push({
                        index: idx,
                        text: text.substring(0, 100),
                        backgroundColor: bgColor,
                        className: div.className,
                        hasSubject: hasSubject,
                        hasTime: hasTime,
                        isColored: isColored
                    });
                }
            });

            return results;
        }""")

        print(f"\n[+] Found {len(lessons)} potential lesson elements")

        # Show all candidates
        for i, lesson in enumerate(lessons[:15]):
            print(f"\n--- Lesson {i+1} ---")
            print(f"Background: {lesson['backgroundColor']}")
            print(f"Has subject: {lesson['hasSubject']} | Has time: {lesson['hasTime']} | Colored: {lesson['isColored']}")
            print(f"Text: {lesson['text']}")

        # Try to find elements with actual subjects
        colored_lessons = [l for l in lessons if l['isColored'] and l['hasSubject']]

        print(f"\n\n[*] Found {len(colored_lessons)} colored lessons with subjects")

        if len(colored_lessons) > 0:
            print(f"\n[*] Will click on first colored lesson: {colored_lessons[0]['text'][:50]}")

            # Find the element again by class name and click it
            lesson_selector = f"div.{colored_lessons[0]['className'].split()[0]}"
            print(f"[*] Using selector: {lesson_selector}")

            try:
                all_matches = await scraper.page.query_selector_all(lesson_selector)
                print(f"[*] Found {len(all_matches)} elements with that class")

                if len(all_matches) > 0:
                    print("[*] Clicking first match...")
                    await all_matches[0].click()
                    await asyncio.sleep(1)

                    print("[*] Pressing Ctrl+Alt+N...")
                    await scraper.page.keyboard.press('Control+Alt+KeyN')
                    await asyncio.sleep(2)

                    # Get content
                    visible_text = await scraper.page.evaluate("() => document.body.innerText")

                    with open("lesson_info_panel.txt", "w", encoding="utf-8") as f:
                        f.write(visible_text)
                    print("[+] Saved to lesson_info_panel.txt")

                    # Show if homework found
                    if 'lektie' in visible_text.lower() or 'opgave' in visible_text.lower():
                        print("[+] Found homework content!")
                    if 'note' in visible_text.lower():
                        print("[+] Found notes!")

            except Exception as e:
                print(f"[-] Error: {e}")

        print("\n[*] Keeping browser open for 60 seconds...")
        print("[*] Please manually click on a colored lesson and press Ctrl+Alt+N")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(test())
