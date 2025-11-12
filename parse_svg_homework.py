import asyncio
from src.studieplus_scraper.scraper import StudiePlusScraper
from bs4 import BeautifulSoup
import re


async def extract_homework():
    async with StudiePlusScraper() as scraper:
        print("[*] Logging in...")
        await scraper.login()
        await asyncio.sleep(2)

        print("\n[*] Getting schedule page HTML...")
        content = await scraper.page.content()

        # Parse with BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')

        # Find all lesson SVG groups (class="CAHE1CD-h-b")
        lesson_groups = soup.find_all('g', class_='CAHE1CD-h-b')

        print(f"[+] Found {len(lesson_groups)} lessons in schedule")

        homework_list = []

        for i, lesson in enumerate(lesson_groups, 1):
            # Get color from rect element
            rect = lesson.find('rect')
            if not rect:
                continue

            fill_color = rect.get('style', '')
            color_match = re.search(r'fill:\s*rgb\((\d+),\s*(\d+),\s*(\d+)\)', fill_color)

            if not color_match:
                continue

            r, g, b = map(int, color_match.groups())

            # Extract lesson info from text elements
            texts = lesson.find_all('text')

            time = ""
            subject = ""
            room = ""
            teacher = ""

            for text_elem in texts:
                text_content = text_elem.get_text(strip=True)

                # Time pattern: HH:MM-HH:MM
                if re.match(r'\d{2}:\d{2}-\d{2}:\d{2}', text_content):
                    time = text_content

                # Subject (bold text after time)
                if text_elem.get('style', '') and 'font-weight: bold' in text_elem.get('style'):
                    if ':' not in text_content:  # Not the time
                        subject = text_content

                # Room and teacher
                if len(text_content) > 2 and len(text_content) < 20:
                    if text_content.startswith('M') or text_content.startswith('N'):
                        room = text_content
                    elif text_content.islower() and len(text_content) < 10:
                        teacher = text_content

            # Check for homework or notes in title
            homework_text = ""
            note_text = ""

            for text_elem in texts:
                title_elem = text_elem.find('title')
                if title_elem:
                    title_content = title_elem.get_text(strip=True)

                    # Check if it's homework (both Danish and English)
                    if '*** Lektier ***' in title_content:
                        homework_text = title_content.replace('*** Lektier ***', '').strip()
                    elif '*** Homework ***' in title_content:
                        homework_text = title_content.replace('*** Homework ***', '').strip()

                    # Check if it's notes (both Danish and English)
                    if '*** Noter ***' in title_content:
                        note_text = title_content.replace('*** Noter ***', '').strip()
                    elif '*** Notes ***' in title_content:
                        note_text = title_content.replace('*** Notes ***', '').strip()

            # Determine lesson type by color
            lesson_type = "normal"
            if r < 150 and g > 200 and b > 200:  # Blue-ish
                lesson_type = "homework"
            elif r < 200 and g > 200 and b < 200:  # Green-ish
                lesson_type = "note"

            # Only save if there's homework or notes
            if homework_text or note_text:
                homework_list.append({
                    'time': time,
                    'subject': subject,
                    'teacher': teacher,
                    'room': room,
                    'color': f'rgb({r}, {g}, {b})',
                    'type': lesson_type,
                    'homework': homework_text,
                    'note': note_text
                })

                print(f"\n[{len(homework_list)}] {subject} ({time})")
                if homework_text:
                    print(f"    Homework: {homework_text[:80]}...")
                if note_text:
                    print(f"    Note: {note_text[:80]}...")

        print(f"\n\n{'='*60}")
        print(f"FOUND {len(homework_list)} LESSONS WITH HOMEWORK/NOTES")
        print(f"{'='*60}\n")

        for i, item in enumerate(homework_list, 1):
            print(f"{i}. {item['subject']} - {item['time']}")
            print(f"   Teacher: {item['teacher']} | Room: {item['room']} | Type: {item['type']}")
            if item['homework']:
                print(f"   Homework: {item['homework'][:100]}...")
            if item['note']:
                print(f"   Note: {item['note'][:100]}...")
            print()

        # Save to JSON
        import json
        with open("schedule_homework.json", "w", encoding="utf-8") as f:
            json.dump(homework_list, f, indent=2, ensure_ascii=False)
        print("[+] Saved to schedule_homework.json")

        print("\n[*] Done! Browser will close in 5 seconds...")
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(extract_homework())
