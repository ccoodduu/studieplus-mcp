import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper
from bs4 import BeautifulSoup


async def extract_homework():
    async with StudiePlusScraper() as scraper:
        print("[*] Logging in...")
        await scraper.login()
        await asyncio.sleep(2)

        print("\n[*] Finding lesson elements in schedule...")

        # Find all lesson boxes using JavaScript
        lessons = await scraper.page.evaluate("""() => {
            const results = [];

            // Look for divs with actual subject names visible
            const allDivs = document.querySelectorAll('div');

            allDivs.forEach((div, idx) => {
                const text = div.innerText || '';
                const style = window.getComputedStyle(div);
                const bgColor = style.backgroundColor;

                // Check if text contains time patterns and subject names
                const hasSubjectPattern = /(Engelsk|Fysik|Matematik|Dansk|Kemi|Biologi|Historie|Studievalg)/i.test(text);
                const isShortText = text.length > 15 && text.length < 100;

                // Check for colored backgrounds (excluding white, transparent, and very light gray)
                const r = parseInt(bgColor.match(/\\d+/g)?.[0] || 255);
                const g = parseInt(bgColor.match(/\\d+/g)?.[1] || 255);
                const b = parseInt(bgColor.match(/\\d+/g)?.[2] || 255);
                const isColored = !(r > 240 && g > 240 && b > 240) && bgColor !== 'rgba(0, 0, 0, 0)';

                if (hasSubjectPattern && isShortText && isColored) {
                    results.push({
                        index: idx,
                        text: text.trim(),
                        bgColor: bgColor,
                        className: div.className
                    });
                }
            });

            return results;
        }""")

        print(f"[+] Found {len(lessons)} colored lesson boxes")

        homework_list = []

        for i, lesson in enumerate(lessons[:10]):  # Process first 10 lessons
            print(f"\n[{i+1}/{len(lessons[:10])}] Processing: {lesson['text'][:50]}")

            try:
                # Click on the lesson box
                # Find element by its index
                lesson_elem = await scraper.page.evaluate(f"""(index) => {{
                    const allDivs = document.querySelectorAll('div');
                    return allDivs[{lesson['index']}];
                }}""", lesson['index'])

                # Click using JavaScript since we have the index
                await scraper.page.evaluate(f"""() => {{
                    const allDivs = document.querySelectorAll('div');
                    allDivs[{lesson['index']}].click();
                }}""")

                await asyncio.sleep(0.5)

                # Press Ctrl+Alt+N to open info panel
                await scraper.page.keyboard.press('Control+Alt+KeyN')
                await asyncio.sleep(1)

                # Extract modal content
                modal_data = await scraper.page.evaluate("""() => {
                    // Look for the Note modal
                    const modal = document.querySelector('.modal-dialog, [role="dialog"], .gwt-DialogBox');

                    if (!modal) return null;

                    const text = modal.innerText || modal.textContent;

                    // Try to extract structured data
                    const result = {
                        owner: '',
                        class_subject: '',
                        date: '',
                        note: '',
                        homework: '',
                        files: []
                    };

                    // Look for "Homework" section
                    const hwMatch = text.match(/Homework[\\s\\S]*?(?=Filer|Files|$)/i);
                    if (hwMatch) {
                        const hwText = hwMatch[0].replace(/^Homework\\s*/i, '').trim();
                        result.homework = hwText;
                    }

                    // Look for "Note" section
                    const noteMatch = text.match(/Note\\s+([\\s\\S]*?)(?=Homework|Filer|Files|$)/i);
                    if (noteMatch && noteMatch[1]) {
                        result.note = noteMatch[1].trim();
                    }

                    // Extract owner, class, date
                    const ownerMatch = text.match(/Owner\\s+([^\\n]+)/i);
                    if (ownerMatch) result.owner = ownerMatch[1].trim();

                    const classMatch = text.match(/Class and subject\\s+([^\\n]+)/i);
                    if (classMatch) result.class_subject = classMatch[1].trim();

                    const dateMatch = text.match(/Date\\s+([^\\n]+)/i);
                    if (dateMatch) result.date = dateMatch[1].trim();

                    return result;
                }""")

                if modal_data and (modal_data['homework'] or modal_data['note']):
                    print(f"  [+] Found content!")
                    if modal_data['homework']:
                        print(f"      Homework: {modal_data['homework'][:80]}...")
                    if modal_data['note']:
                        print(f"      Note: {modal_data['note'][:80]}...")

                    homework_list.append({
                        'lesson': lesson['text'],
                        'background_color': lesson['bgColor'],
                        **modal_data
                    })
                else:
                    print(f"  [-] No homework or notes")

                # Close modal by pressing Escape
                await scraper.page.keyboard.press('Escape')
                await asyncio.sleep(0.3)

            except Exception as e:
                print(f"  [-] Error: {e}")
                # Try to close any open modal
                await scraper.page.keyboard.press('Escape')
                await asyncio.sleep(0.3)

        print(f"\n\n{'='*60}")
        print(f"SUMMARY: Found {len(homework_list)} lessons with homework/notes")
        print(f"{'='*60}\n")

        for i, hw in enumerate(homework_list, 1):
            print(f"{i}. {hw['class_subject']} ({hw['date']})")
            print(f"   Lesson: {hw['lesson']}")
            if hw['homework']:
                print(f"   Homework: {hw['homework'][:100]}...")
            if hw['note']:
                print(f"   Note: {hw['note'][:100]}...")
            print()

        # Save to file
        import json
        with open("schedule_homework.json", "w", encoding="utf-8") as f:
            json.dump(homework_list, f, indent=2, ensure_ascii=False)
        print("[+] Saved to schedule_homework.json")

        print("\n[*] Keeping browser open for 30 seconds...")
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(extract_homework())
