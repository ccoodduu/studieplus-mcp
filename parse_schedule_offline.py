from bs4 import BeautifulSoup
import json

with open("schedule_page.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

print("[*] Analyzing schedule HTML structure...")

# Find all text containing "Studieomr" or homework keywords
all_text = soup.get_text()
lines = all_text.split('\n')

homework_lines = []
for i, line in enumerate(lines):
    line = line.strip()
    if len(line) > 20 and ('Studieomr' in line or 'lektie' in line.lower() or
                            'aflever' in line.lower() or 'opgave' in line.lower()):
        homework_lines.append({
            'line_num': i,
            'text': line[:200]
        })

print(f"\n[+] Found {len(homework_lines)} potential homework lines")
for hw in homework_lines[:10]:
    try:
        print(f"\n{hw['line_num']}: {hw['text']}")
    except UnicodeEncodeError:
        print(f"\n{hw['line_num']}: [Unicode text]")

# Try to find schedule table structure
print("\n\n[*] Looking for table/grid structure...")
tables = soup.find_all('table')
print(f"[*] Found {len(tables)} tables")

for idx, table in enumerate(tables[:3]):
    print(f"\n--- Table {idx+1} ---")
    rows = table.find_all('tr')
    print(f"Rows: {len(rows)}")
    if len(rows) > 0:
        first_row = rows[0]
        cells = first_row.find_all(['td', 'th'])
        print(f"Cells in first row: {len(cells)}")
        if len(cells) > 0:
            print(f"First cell text: {cells[0].get_text()[:50]}")

# Look for divs with specific classes that might be lessons
print("\n\n[*] Looking for lesson divs...")
divs_with_class = soup.find_all('div', class_=True)
print(f"[*] Found {len(divs_with_class)} divs with classes")

# Sample first 50
lesson_candidates = []
for div in divs_with_class[:100]:
    text = div.get_text(strip=True)
    if len(text) > 30 and len(text) < 500:
        classes = ' '.join(div.get('class', []))
        if 'time' in text.lower() or 'kl.' in text.lower() or ':' in text[:20]:
            lesson_candidates.append({
                'classes': classes,
                'text': text[:150]
            })

print(f"\n[+] Found {len(lesson_candidates)} potential lesson elements")
for i, lesson in enumerate(lesson_candidates[:5]):
    print(f"\n{i+1}. Classes: {lesson['classes']}")
    print(f"   Text: {lesson['text']}")

# Save results
with open("schedule_parse_results.json", "w", encoding="utf-8") as f:
    json.dump({
        'homework_lines': homework_lines,
        'lesson_candidates': lesson_candidates
    }, f, indent=2, ensure_ascii=False)

print("\n\n[+] Results saved to schedule_parse_results.json")
