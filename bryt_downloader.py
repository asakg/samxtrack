import asyncio
import os
from datetime import datetime
from playwright.async_api import async_playwright
import shutil

# Configuration
USERNAME = "rami@ajpartnersllc.com"
PASSWORD = "KGlinegroup2025"
LOGIN_URL = "https://v3.brytsoftware.com/Loans/Loans/Index"
CSV_FILENAME = "latest_loans.csv"
TEMP_FILENAME = "temp_loans.csv"

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
FINAL_PATH = os.path.join(DATA_DIR, CSV_FILENAME)
TEMP_PATH = os.path.join(DATA_DIR, TEMP_FILENAME)

async def download_csv():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()

            await page.goto(LOGIN_URL)

            # Fill login form - update selectors if needed
            await page.fill('input[name="username"]', USERNAME)
            await page.fill('input[name="password"]', PASSWORD)
            await page.click('button[type="submit"]')

            # Wait for dashboard to load
            await page.wait_for_selector('text="Dashboard"')

            # Navigate to Loans section - update selector if needed
            await page.click('a[href="/loans"]')
            await page.wait_for_selector('text="Loan List"')

            # Trigger CSV download
            with page.expect_download() as download_info:
                await page.click('button#downloadCsv')  # Update this selector
            download = await download_info.value
            await download.save_as(TEMP_PATH)
            await browser.close()

        # If temp file downloaded, replace the final file
        if os.path.exists(TEMP_PATH):
            shutil.move(TEMP_PATH, FINAL_PATH)
            print(f"[{datetime.now()}] ✅ CSV downloaded and saved to {FINAL_PATH}")
        else:
            print(f"[{datetime.now()}] ⚠️ Download failed, using previous CSV.")
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Exception occurred: {e}")
        if os.path.exists(TEMP_PATH):
            os.remove(TEMP_PATH)

# Entry point
if __name__ == "__main__":
    asyncio.run(download_csv())