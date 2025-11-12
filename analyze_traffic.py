import asyncio
from playwright.async_api import async_playwright
import json
import os
from dotenv import load_dotenv

load_dotenv()

network_log = []

async def analyze_traffic():
    username = os.getenv("STUDIEPLUS_USERNAME")
    password = os.getenv("STUDIEPLUS_PASSWORD")
    school = os.getenv("STUDIEPLUS_SCHOOL")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        def log_request(request):
            network_log.append({
                'type': 'request',
                'method': request.method,
                'url': request.url,
                'headers': dict(request.headers),
                'post_data': request.post_data if request.method == 'POST' else None
            })
            print(f"\n>>> REQUEST: {request.method} {request.url}")
            if request.method == 'POST' and request.post_data:
                print(f"    POST DATA: {request.post_data}")

        def log_response(response):
            print(f"<<< RESPONSE: {response.status} {response.url}")

        page.on("request", log_request)
        page.on("response", log_response)

        print("[*] Navigating to Studie+...")
        await page.goto("https://all.studieplus.dk/")
        await page.wait_for_load_state("networkidle")

        print("\n[*] Selecting school...")
        await page.wait_for_selector(".select2-container")
        await page.click(".select2-container")
        await asyncio.sleep(0.3)

        search_input = await page.wait_for_selector(".select2-search input, .select2-input")
        await search_input.type(school)
        await asyncio.sleep(0.3)

        result = await page.wait_for_selector(f".select2-results .select2-result:has-text('{school}')")
        await result.click()
        await asyncio.sleep(0.3)

        print("\n[*] Clicking Direkte login...")
        direkte_button = await page.wait_for_selector("button#direkte")
        await direkte_button.click()

        print("\n[*] Filling credentials...")
        username_field = await page.wait_for_selector("input[name='user']")
        await username_field.fill(username)

        password_field = await page.wait_for_selector("input[type='password']")
        await password_field.fill(password)

        print("\n[*] Submitting login...")
        submit_button = await page.wait_for_selector("button[type='submit']")
        await submit_button.click()

        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

        print("\n[*] Navigating to assignments...")
        assignments_link = await page.wait_for_selector("a:has-text('Assignments')")
        await assignments_link.click()

        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        print("\n[*] Saving network log...")
        with open("network_log.json", "w", encoding="utf-8") as f:
            json.dump(network_log, f, indent=2, ensure_ascii=False)

        print(f"\n[+] Saved {len(network_log)} network requests to network_log.json")

        print("\n[*] Key requests summary:")
        for entry in network_log:
            if entry['type'] == 'request':
                url = entry['url']
                if 'login' in url or 'opgave' in url or 'skema' in url:
                    print(f"\n{entry['method']} {url}")
                    if entry['post_data']:
                        print(f"  POST: {entry['post_data']}")
                    print(f"  Cookies: {entry['headers'].get('cookie', 'None')[:100]}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(analyze_traffic())
