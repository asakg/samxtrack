# file: test_download_excel.py
from playwright.sync_api import sync_playwright
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import re
import hashlib
import os, json, base64
import boto3

# ---- Selectors ----
SEL_USERNAME_INPUT   = "#UserName"                       # Username input
SEL_PASSWORD_INPUT   = "#Password"                       # Password input
SEL_LOGIN_BUTTON     = "button[type='submit']"           # Login button
SEL_LOANS_LINK       = "a[href='/Loans/Loans/Index']"    # Loans menu link
SEL_EXPORT_TO_EXCEL  = "button[data-role='excel']"       # Export to Excel button

# ---- Paths & naming helpers ----
PROJECT_ROOT = Path(__file__).resolve().parent  # sam_xtrack/
DATA_DIR = PROJECT_ROOT / "data"
LATEST_XLSX = DATA_DIR / "latest_loans.xlsx"
WEEKLY_DIR = DATA_DIR / "weekly_backups"        # snapshots live here
TMP_XLSX = DATA_DIR / "_tmp_download.xlsx"


def _monday_str(today: datetime) -> str:
    """Return YYYY-MM-DD string for Monday of this ISO week."""
    monday = today - timedelta(days=today.weekday())  # Monday = 0
    return monday.strftime("%Y-%m-%d")


def _extract_max_week_tag(xlsx_path: Path) -> str | None:
    """
    From the downloaded Excel, read the 'Last W Collected' column and return the
    largest week tag like 'W34'. If column missing or unparsable, return None.
    """
    try:
        df = pd.read_excel(xlsx_path)
        col = None
        for candidate in [
            "Last W Collected",
            "Last W collected",
            "LastWCollected",
            "Last_W_Collected",
        ]:
            if candidate in df.columns:
                col = candidate
                break
        if not col:
            return None

        week_nums = []
        for val in df[col].dropna().astype(str):
            m = re.search(r"[Ww]\s*-?\s*(\d+)", val)
            if m:
                week_nums.append(int(m.group(1)))
        if not week_nums:
            return None
        max_week = max(week_nums)
        return f"W{max_week}"
    except Exception:
        return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- Bryt credentials helper ----
def get_bryt_creds():
    """
    Fetch Bryt credentials from AWS Secrets Manager.

    Expected secret payload (JSON):
      {
        "BRYT_USER": "user@example.com",
        "BRYT_PASS": "supersecret"
      }

    Fallback to environment variables BRYT_USER / BRYT_PASS if needed.
    """
    secret_name = os.getenv("BRYT_SECRET_NAME", "samxtrack/bryt-login")
    region_name = os.getenv("AWS_REGION", "us-east-1")  # adjust if different

    # 1) Try AWS Secrets Manager
    try:
        client = boto3.client("secretsmanager", region_name=region_name)
        resp = client.get_secret_value(SecretId=secret_name)
        secret_str = resp.get("SecretString") or base64.b64decode(resp["SecretBinary"]).decode()
        data = json.loads(secret_str)
        user = data.get("BRYT_USER")
        pw = data.get("BRYT_PASS")
        if user and pw:
            return user, pw
    except Exception:
        # swallow and try env next
        pass

    # 2) Fallback: environment variables
    u = os.getenv("BRYT_USER")
    p = os.getenv("BRYT_PASS")
    if u and p:
        return u, p

    raise RuntimeError(
        "Bryt credentials not found. Ensure AWS secret has keys BRYT_USER/BRYT_PASS "
        f"under '{secret_name}', or set env vars BRYT_USER / BRYT_PASS."
    )


# ---- Test run ----
def test_download(username: str, password: str, headless: bool = False):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            slow_mo=200,
            args=["--disable-dev-shm-usage", "--use-mock-keychain"],
        )
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # Go to Loans index (will redirect to login if needed)
        page.goto("https://v3.brytsoftware.com/Loans/Loans/Index")

        # Login
        page.fill(SEL_USERNAME_INPUT, username)
        page.fill(SEL_PASSWORD_INPUT, password)
        page.click(SEL_LOGIN_BUTTON)

        # Navigate to Loans
        page.wait_for_selector(SEL_LOANS_LINK)
        page.click(SEL_LOANS_LINK)

        # Ensure grid/data fully loaded before exporting
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(SEL_EXPORT_TO_EXCEL, state="visible")

        # Trigger export and capture fresh download
        with page.expect_download() as download_info:
            page.click(SEL_EXPORT_TO_EXCEL)
        download = download_info.value

        # Always save first to a temp file, then compare+promote to latest
        download.save_as(TMP_XLSX.as_posix())
        new_hash = _sha256(TMP_XLSX)
        old_hash = _sha256(LATEST_XLSX) if LATEST_XLSX.exists() else "(none)"
        print(f"ℹ️  Old latest_loans.xlsx hash: {old_hash}")
        print(f"ℹ️  New download hash      : {new_hash}")

        # Promote temp to latest (always overwrite to keep it current)
        LATEST_XLSX.write_bytes(TMP_XLSX.read_bytes())
        print("✅ latest_loans.xlsx updated:", LATEST_XLSX)

        # If Friday, also save a weekly snapshot using week tag from the file
        today = datetime.now()
        if today.weekday() == 4:  # Friday
            week_tag = _extract_max_week_tag(TMP_XLSX) or f"week{today.isocalendar().week:02d}"
            monday_str = _monday_str(today)
            weekly_name = f"{monday_str}-{week_tag}.xlsx"
            weekly_path = WEEKLY_DIR / weekly_name
            weekly_path.write_bytes(TMP_XLSX.read_bytes())
            print("📦 Weekly snapshot saved to:", weekly_path)

        browser.close()


if __name__ == "__main__":
    user, pw = get_bryt_creds()
    # For EC2/scheduler runs you likely want headless=True; locally you can flip to False.
    test_download(user, pw, headless=True)