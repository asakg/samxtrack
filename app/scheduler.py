# file: app/scheduler.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import json
import pandas as pd
from utils import load_latest_loans

try:
    from zoneinfo import ZoneInfo  # py39+
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

# ---- your app imports (these should already exist) ----
# Bryt downloader: must expose `download_latest(headless: bool = True) -> Path | None`
from bryt_downloader import download_latest

# Report generators (already added earlier)
from app.reports.generate_report import (
    generate_take_action_report,
    generate_ceo_must_contact_report,
)

# -----------------------------
# Logging
# -----------------------------
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "scheduler.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),  # also print to console
    ],
)
log = logging.getLogger("samxtrack.scheduler")


TZ_CHICAGO = ZoneInfo("America/Chicago")

# -----------------------------
# Weekly JSON builder (for Take Action)
# -----------------------------
def _current_friday_tag(now: datetime | None = None) -> str:
    """Return YYYY-MM-DD for the Friday of the current week (matching UI convention)."""
    now = now or datetime.now(tz=TZ_CHICAGO)
    # Friday is weekday() == 4; move forward 0..6 days to the next/current Friday
    delta = (4 - now.weekday()) % 7
    friday = now + timedelta(days=delta)
    return friday.strftime("%Y-%m-%d")

def _weekly_actions_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "weekly_actions"

def ensure_weekly_json_from_latest() -> Path | None:
    """
    If the weekly_actions JSON for this week is missing, create it from latest_loans.xlsx.
    We pre-populate entries with contacted=False and empty notes, keeping the order:
    High Risk first, then Critical (so existing report splitter works by halving the list).
    """
    try:
        week_tag = _current_friday_tag()
        out_dir = _weekly_actions_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{week_tag}.json"

        if out_path.exists():
            log.info("Weekly JSON already exists; leaving as-is: %s", out_path)
            return out_path

        # Load latest loans
        df = load_latest_loans()
        if df.empty:
            log.warning("Cannot build weekly JSON: latest_loans.xlsx is empty.")
            return None

        # Normalize booleans if needed
        df["Has Title"] = df.get("Has Title", pd.Series([False]*len(df))).astype(bool)
        df["Has Guarantor"] = df.get("Has Guarantor", pd.Series([False]*len(df))).astype(bool)
        df["Days Late"] = pd.to_numeric(df.get("Days Late", 0), errors="coerce").fillna(0).astype(int)

        # Classification consistent with dashboard/utils:
        is_critical = (df["Days Late"] > 21) & (~df["Has Title"]) & (~df["Has Guarantor"])
        is_high_risk = (df["Days Late"] > 21) & ~is_critical

        high_df = df[is_high_risk].copy()
        crit_df = df[is_critical].copy()

        def to_entries(frame: pd.DataFrame) -> list[dict]:
            rows = []
            for _, r in frame.iterrows():
                rows.append({
                    "borrower": str(r.get("Borrower", "")).strip(),
                    "balance": float(r.get("Principal Balance", 0) or 0.0),
                    "days_late": int(r.get("Days Late", 0) or 0),
                    "contacted": False,
                    "note": ""
                })
            return rows

        entries = to_entries(high_df) + to_entries(crit_df)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
        log.info("Weekly JSON created: %s (entries=%d)", out_path, len(entries))
        return out_path
    except Exception as e:
        log.exception("Failed to create weekly JSON: %s", e)
        return None


# -----------------------------
# Jobs
# -----------------------------
def daily_download_job():
    """Run every day @ 5:00 AM America/Chicago."""
    log.info("Daily download job started")
    try:
        xlsx_path = download_latest(headless=True)  # downloader handles AWS secrets internally
        if xlsx_path:
            log.info("Daily download complete: %s", xlsx_path)
        else:
            log.warning("Daily download returned no path (check downloader logs).")
    except Exception as e:
        log.exception("Daily download failed: %s", e)


def friday_reports_job():
    """
    Run Fridays shortly after the daily pull.
    - Generate Take Action report (if weekly JSON exists)
    - Generate CEO Must-Contact report (safe; skips if no matches)
    """
    log.info("Friday reports job started")
    try:
        built = ensure_weekly_json_from_latest()
        if built:
            log.info("Weekly JSON ensured: %s", built)
    except Exception as e:
        log.exception("Weekly JSON ensure step failed: %s", e)
    try:
        take = generate_take_action_report()
        if take:
            log.info("TakeAction report generated: %s", take)
        else:
            log.info("TakeAction not generated (likely no weekly JSON).")

        ceo = generate_ceo_must_contact_report(send_notifications=False)
        if ceo:
            log.info("CEO report generated: %s", ceo)
        else:
            log.info("CEO report skipped or no matches.")
    except Exception as e:
        log.exception("Friday reports failed: %s", e)


# -----------------------------
# Main scheduler
# -----------------------------
def main():
    log.info("Starting scheduler… (logs -> %s)", LOG_FILE)

    sched = BlockingScheduler(timezone=TZ_CHICAGO)

    # 1) Daily Bryt download: 5:00 AM Central, everyday
    sched.add_job(
        daily_download_job,
        trigger=CronTrigger(hour=5, minute=0),  # 05:00 America/Chicago
        id="daily_download",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=60 * 30,  # 30 minutes
    )

    # 2) Friday weekly PDFs: 5:05 AM Central, Fridays only
    sched.add_job(
        friday_reports_job,
        trigger=CronTrigger(day_of_week="fri", hour=5, minute=5),
        id="friday_reports",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=60 * 30,
    )

    # Optional: let you kick off immediately for a dry run by uncommenting:
    # daily_download_job()
    # friday_reports_job()

    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()