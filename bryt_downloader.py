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
    region_name = os.getenv("AWS_REGION", "us-east-2")

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
        page.set_default_timeout(120_000)

        # 1) Go directly to Loans page (bypasses navbar/hamburger in headless)
        LOANS_URL = "https://v3.brytsoftware.com/Loans/Loans/Index"
        page.goto(LOANS_URL, wait_until="domcontentloaded")

        # 2) If redirected to login, submit credentials
        if page.query_selector(SEL_USERNAME_INPUT):
            page.fill(SEL_USERNAME_INPUT, username)
            page.fill(SEL_PASSWORD_INPUT, password)
            with page.expect_navigation(wait_until="networkidle"):
                page.click(SEL_LOGIN_BUTTON)

        # 3) Ensure we land on Loans and the export button is ready
        page.goto(LOANS_URL, wait_until="domcontentloaded")
        page.wait_for_url(lambda url: "/Loans/Loans/Index" in url, timeout=90_000)
        page.wait_for_load_state("networkidle")

        # Some pages render a Kendo toolbar; wait for it if present
        try:
            page.wait_for_selector(".k-toolbar, .k-grid-toolbar", state="visible", timeout=20_000)
        except Exception:
            pass  # not fatal; continue

        # Bryt has used a few different selectors for the Excel export button over time.
        possible_export_selectors = [
            SEL_EXPORT_TO_EXCEL,           # button[data-role='excel']
            ".k-grid-excel",               # common Kendo class
            "button:has-text('Export to Excel')",
            "text=Export to Excel",        # text fallback
        ]

        excel_btn = None
        for sel in possible_export_selectors:
            try:
                excel_btn = page.wait_for_selector(sel, state="visible", timeout=20_000)
                if excel_btn:
                    break
            except Exception:
                continue

        if not excel_btn:
            # Write debug artifacts to help troubleshoot
            debug_dir = DATA_DIR / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / "loans_page_debug.html").write_text(page.content())
            try:
                page.screenshot(path=(debug_dir / "loans_page_debug.png").as_posix(), full_page=True)
            except Exception:
                pass
            raise RuntimeError("Could not locate the 'Export to Excel' button on Loans page. Debug saved to data/debug/")

        # 4) Export & capture download
        with page.expect_download() as dl_info:
            excel_btn.click()
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