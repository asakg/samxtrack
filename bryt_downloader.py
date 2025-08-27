"""
app/bryt_downloader.py

Headless Bryt export → puts fresh Excel in:
- data/_tmp_download.xlsx
- data/latest_loans.xlsx   (always updated)
- data/weekly_backups/<YYYY-MM-DD>-Wxx.xlsx  (Fridays, America/Chicago)

Credentials:
- Primary: AWS Secrets Manager (secret name in env BRYT_SECRET_NAME; default: samxtrack/bryt-login)
  Secret JSON must contain keys: BRYT_USER, BRYT_PASS
- Fallback: env vars BRYT_USERNAME / BRYT_PASSWORD

This module can be:
- Imported and called from scheduler.py → run_download()
- Run directly: `python -m app.bryt_downloader` (or `python app/bryt_downloader.py`)
"""

from __future__ import annotations

import os
import re
import json
import base64
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

import boto3
import pandas as pd
from playwright.sync_api import sync_playwright

# ---------------------------
# Selectors (stable, low risk)
# ---------------------------
SEL_USERNAME_INPUT   = "#UserName"
SEL_PASSWORD_INPUT   = "#Password"
SEL_LOGIN_BUTTON     = "button[type='submit']"
SEL_LOANS_LINK       = "a[href='/Loans/Loans/Index']"
SEL_EXPORT_TO_EXCEL  = "button[data-role='excel']"

# ---------------------------
# Paths
# ---------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # -> sam_xtrack/
DATA_DIR     = PROJECT_ROOT / "data"
LATEST_XLSX  = DATA_DIR / "latest_loans.xlsx"
WEEKLY_DIR   = DATA_DIR / "weekly_backups"
TMP_XLSX     = DATA_DIR / "_tmp_download.xlsx"

# ---------------------------
# Helpers
# ---------------------------
def _monday_str(dt: datetime) -> str:
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def _extract_max_week_tag(xlsx_path: Path) -> str | None:
    """Read 'Last W Collected' column and return the largest tag like 'W34'."""
    try:
        df = pd.read_excel(xlsx_path)
        col = None
        for candidate in ("Last W Collected", "Last W collected", "LastWCollected", "Last_W_Collected"):
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
        return f"W{max(week_nums)}"
    except Exception:
        return None

# ---------------------------
# Secrets
# ---------------------------
def _get_bryt_creds() -> tuple[str, str]:
    """
    Secrets Manager first (expects keys BRYT_USER / BRYT_PASS), then env fallback.
    Secret name default: samxtrack/bryt-login
    Region default: us-east-1
    """
    secret_name = os.getenv("BRYT_SECRET_NAME", "samxtrack/bryt-login")
    region_name = os.getenv("AWS_REGION", "us-east-1")

    try:
        client = boto3.client("secretsmanager", region_name=region_name)
        resp = client.get_secret_value(SecretId=secret_name)
        secret_str = resp.get("SecretString") or base64.b64decode(resp["SecretBinary"]).decode()
        payload = json.loads(secret_str)
        username = payload.get("BRYT_USER")
        password = payload.get("BRYT_PASS")
        if not (username and password):
            raise RuntimeError("Secret missing BRYT_USER / BRYT_PASS keys")
        return username, password
    except Exception:
        # Local/dev fallback
        u = os.getenv("BRYT_USERNAME")
        p = os.getenv("BRYT_PASSWORD")
        if u and p:
            return u, p
        raise

# ---------------------------
# Core downloader
# ---------------------------
def run_download(headless: bool = True, echo: bool = True, also_run_reports_on_friday: bool = False) -> dict:
    """
    Returns a dict with info about files written.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)

    username, password = _get_bryt_creds()

    out = {
        "tmp": None,
        "latest": None,
        "weekly": None,
        "friday": False,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-dev-shm-usage"]
        )
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # 1) Navigate (login page redirects if not authenticated)
        page.goto("https://v3.brytsoftware.com/Loans/Loans/Index")

        # 2) Login
        page.fill(SEL_USERNAME_INPUT, username)
        page.fill(SEL_PASSWORD_INPUT, password)
        page.click(SEL_LOGIN_BUTTON)

        # 3) Navigate to Loans & wait for grid
        page.wait_for_selector(SEL_LOANS_LINK)
        page.click(SEL_LOANS_LINK)
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(SEL_EXPORT_TO_EXCEL, state="visible")

        # 4) Export & capture download
        with page.expect_download() as dl_info:
            page.click(SEL_EXPORT_TO_EXCEL)
        download = dl_info.value

        download.save_as(TMP_XLSX.as_posix())
        out["tmp"] = TMP_XLSX.as_posix()

        # 5) Promote to latest (always overwrite)
        LATEST_XLSX.write_bytes(TMP_XLSX.read_bytes())
        out["latest"] = LATEST_XLSX.as_posix()

        if echo:
            old_hash = _sha256(LATEST_XLSX) if LATEST_XLSX.exists() else "(none)"
            new_hash = _sha256(TMP_XLSX)
            print(f"ℹ️  latest_loans.xlsx: {LATEST_XLSX}")
            print(f"ℹ️  New tmp hash     : {new_hash}")

        # 6) Friday snapshot (America/Chicago)
        # We detect Friday by *local time* unless the scheduler enforces CRON_TZ.
        # If you always set CRON_TZ=America/Chicago in crontab, this simple check is enough.
        if datetime.now().weekday() == 4:  # 0=Mon ... 4=Fri
            out["friday"] = True
            week_tag = _extract_max_week_tag(TMP_XLSX) or f"W{datetime.now().isocalendar().week:02d}"
            weekly_name = f"{_monday_str(datetime.now())}-{week_tag}.xlsx"
            weekly_path = WEEKLY_DIR / weekly_name
            weekly_path.write_bytes(TMP_XLSX.read_bytes())
            out["weekly"] = weekly_path.as_posix()
            if echo:
                print(f"📦 Weekly snapshot: {weekly_path}")

            if also_run_reports_on_friday:
                try:
                    # Import lazily to avoid circular imports / extra deps in normal run
                    from app.reports.generate_report import (
                        generate_take_action_report,
                        generate_ceo_must_contact_report,
                    )
                    print("[Weekly] Generating PDFs…")
                    generate_take_action_report()
                    generate_ceo_must_contact_report(send_notifications=False)
                except Exception as e:
                    print("[Weekly] Report generation failed:", e)

        browser.close()

    return out

# ---------------------------
# CLI usage
# ---------------------------
if __name__ == "__main__":
    # Default: headless=True for EC2; set HEADLESS=0 locally to watch
    headless = os.getenv("HEADLESS", "1") not in ("0", "false", "False")
    also_reports = os.getenv("RUN_WEEKLY_REPORTS", "0") in ("1", "true", "True")
    info = run_download(headless=headless, echo=True, also_run_reports_on_friday=also_reports)
    print("Result:", json.dumps(info, indent=2))