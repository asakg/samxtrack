import os
import re
import json
import pandas as pd
import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # kept for backward-compat
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML
import base64

# --- utils import (works whether you run as module or file) ---
try:
    # Running as a module: python -m app.reports.generate_report
    from app.utils import load_latest_loans
except ImportError:
    # Running the file directly: python app/reports/generate_report.py
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    from utils import load_latest_loans

# --- optional notifications ---
try:
    from app.notifications.notifications import (
        send_email_with_attachment,
        send_telegram_document,
    )
except Exception:
    def send_email_with_attachment(*args, **kwargs):  # no-op fallback
        pass
    def send_telegram_document(*args, **kwargs):      # no-op fallback
        pass


# ========== Template helpers ==========
def _project_root():
    # this file: sam_xtrack/app/reports/generate_report.py  -> ../../ = sam_xtrack/
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def _get_env():
    try:
        return Environment(
            loader=FileSystemLoader(os.path.join(_project_root(), "app", "templates")),
            autoescape=select_autoescape(["html", "xml"]),
        )
    except Exception as e:
        print("Template environment init failed:", e)
        return None

def _safe_get_template(env, template_path):
    if env is None:
        return None
    try:
        return env.get_template(template_path)
    except Exception as e:
        print(f"Template not found or failed to load: {template_path} ->", e)
        return None


# ========== Path helpers ==========
def _reports_dir():
    root = _project_root()
    path = os.path.join(root, "reports")  # => sam_xtrack/reports
    os.makedirs(path, exist_ok=True)
    return path

def _weekly_actions_dir():
    root = _project_root()
    return os.path.join(root, "data", "weekly_actions")

def _latest_week_json():
    """Return (json_path, week_tag) for the newest weekly_actions file, or (None, None) if none."""
    folder = _weekly_actions_dir()
    if not os.path.exists(folder):
        return None, None
    files = sorted(f for f in os.listdir(folder) if f.endswith(".json"))
    if not files:
        return None, None
    last = files[-1]
    return os.path.join(folder, last), last.replace(".json", "")


# ========== Take Action Report ==========
def render_split_table_data(borrowers):
    contacted = []
    not_contacted = []

    for row in borrowers:
        entry = {
            "borrower": row.get("borrower", ""),
            "balance": f"${row.get('balance', 0):,.2f}",
            "note": row.get("note", "Not Contacted") if row.get("contacted") else "Not Contacted",
            "contacted": row.get("contacted", False),
        }
        if entry["contacted"]:
            contacted.append(entry)
        else:
            not_contacted.append(entry)
    return {"contacted": contacted, "not_contacted": not_contacted}

def generate_take_action_report():
    """Generate the weekly Take Action PDF from the newest JSON. Never raise."""
    try:
        json_path, week = _latest_week_json()
        if not json_path:
            print("[TakeAction] No JSON files found. Skipping.")
            return None

        with open(json_path) as f:
            data = json.load(f)
        df = pd.DataFrame(data)

        if df.empty:
            print("[TakeAction] Data is empty. Skipping.")
            return None

        # Split into halves (your current convention)
        mid = len(df) // 2
        high_risk_df = df.iloc[:mid]
        critical_df = df.iloc[mid:]

        high_risk_data = render_split_table_data(high_risk_df.to_dict(orient="records"))
        critical_data = render_split_table_data(critical_df.to_dict(orient="records"))

        contacted_counts = df.get("contacted", pd.Series(dtype=int)).value_counts()
        total = int(len(df))
        contacted_n = int(contacted_counts.get(True, 0)) if not contacted_counts.empty else 0
        not_contacted_n = int(contacted_counts.get(False, 0)) if not contacted_counts.empty else 0

        # Percentages as strings with % for width attributes in the template
        contacted_pct = f"{round((contacted_n / total) * 100) if total else 0}%"
        not_contacted_pct = f"{100 - int(contacted_pct.rstrip('%')) if total else 0}%"

        env = _get_env()
        template = _safe_get_template(env, "dashboardsidebar/takeaction/take_action_report.html")
        if template is None:
            print("[TakeAction] Template missing. Skipping PDF render.")
            return None

        html_content = template.render(
            week=week,
            total=len(df),
            contacted=contacted_n,
            not_contacted=not_contacted_n,
            chart_data="",  # no pie image
            high_risk=high_risk_data,
            critical=critical_data,
            contacted_pct=contacted_pct,
            not_contacted_pct=not_contacted_pct,
        )

        report_dir = _reports_dir()
        pdf_path = os.path.join(report_dir, f"TakeAction_Report_{week}.pdf")
        try:
            HTML(string=html_content).write_pdf(pdf_path)
            print(f"[TakeAction] PDF generated at {pdf_path}")
            return pdf_path
        except Exception as e:
            print("[TakeAction] PDF render failed:", e)
            return None
    except Exception as e:
        print("[TakeAction] Unexpected error:", e)
        return None


## ========== CEO “Must Contact” Report ==========

# Exact dropdown phrase (this is what you’ll enforce on the Take Action page)
EXPECTED_NOTE = "move to BAD, needs to contacted by MIKE/SAIPI"

def _normalize_note(s: str) -> str:
    """Trim, collapse internal whitespace, and uppercase for stable comparison."""
    return " ".join(s.strip().split()).upper()

_EXPECTED_NOTE_NORM = _normalize_note(EXPECTED_NOTE)

def _note_matches(note: str) -> bool:
    """Match the dropdown phrase robustly (ignores case / extra spaces)."""
    return isinstance(note, str) and _normalize_note(note) == _EXPECTED_NOTE_NORM

def generate_ceo_must_contact_report(send_notifications: bool = False):
    """
    Create CEO report from the latest weekly_actions JSON.
    Criteria: note matches EXPECTED_NOTE.
    We classify into two buckets:
      - High Risk (21+ days late)
      - Critical (No Title & No Guarantor, and >21 days late)
    Saves to sam_xtrack/reports/CEO_MustContact_<week>.pdf
    Never raises; returns pdf path or None.
    """
    try:
        json_path, week = _latest_week_json()
        if not json_path:
            print("[CEO] No weekly_actions JSON found. Skipping CEO report.")
            return None

        with open(json_path, "r") as f:
            actions = json.load(f)

        # Filter by note
        filtered = [a for a in actions if _note_matches(a.get("note", ""))]
        if not filtered:
            # helpful debug of notes seen
            seen = sorted({repr(a.get("note", "")) for a in actions})
            print("[CEO] No matching CEO contact cases found. Notes seen:", seen)
            return None

        # Pull loans file to enrich with Days Late / Has Title / Has Guarantor
        try:
            loans_df = load_latest_loans()
        except Exception as e:
            print("[CEO] load_latest_loans failed:", e)
            loans_df = pd.DataFrame()

        have_loans = (not loans_df.empty and
                      all(col in loans_df.columns for col in ["Borrower", "Days Late", "Has Title", "Has Guarantor"]))

        high_rows = []
        critical_rows = []

        for a in filtered:
            borrower = str(a.get("borrower", "")).strip()
            bal = float(a.get("balance", 0) or 0.0)

            # Days late: prefer JSON, else from loans
            try:
                days = int(a.get("days_late") or 0)
            except Exception:
                days = 0

            has_title = False
            has_guarantor = False

            if have_loans and borrower:
                matches = loans_df[loans_df["Borrower"] == borrower]
                if not matches.empty:
                    try:
                        # if multiple rows, use the max lateness / any flags
                        days = max(days, int(matches["Days Late"].fillna(0).astype(float).max()))
                    except Exception:
                        pass
                    has_title = bool(matches["Has Title"].fillna(False).astype(bool).any())
                    has_guarantor = bool(matches["Has Guarantor"].fillna(False).astype(bool).any())

            row_payload = {
                "borrower": borrower,
                "balance_fmt": f"${bal:,.2f}",
                "days_late": int(days),
                "note": a.get("note", ""),
            }

            # Bucket logic
            if int(days) > 21 and (not has_title) and (not has_guarantor):
                critical_rows.append(row_payload)
            elif int(days) > 21:
                high_rows.append(row_payload)
            else:
                # If the note is set but <22 days late, we leave it out.
                # (You can move it to high_rows if you want to still show it.)
                pass

        # Sort within each bucket by lateness
        critical_rows.sort(key=lambda r: r["days_late"], reverse=True)
        high_rows.sort(key=lambda r: r["days_late"], reverse=True)

        # Render
        env = _get_env()
        template = _safe_get_template(env, "ceo_must_contact.html")
        if template is None:
            print("[CEO] Template missing. Skipping PDF render.")
            return None

        html_string = template.render(
            week=week,
            expected_note=EXPECTED_NOTE,
            high_rows=high_rows,
            critical_rows=critical_rows
        )

        out_dir = _reports_dir()
        pdf_path = os.path.join(out_dir, f"CEO_MustContact_{week}.pdf")
        try:
            HTML(string=html_string).write_pdf(pdf_path)
            print(f"[CEO] PDF generated at {pdf_path}")
        except Exception as e:
            print("[CEO] PDF render failed:", e)
            return None

        if send_notifications:
            try:
                send_email_with_attachment(pdf_path)
            except Exception as e:
                print("[CEO] Email send failed:", e)
            try:
                send_telegram_document(pdf_path)
            except Exception as e:
                print("[CEO] Telegram send failed:", e)

        return pdf_path
    except Exception as e:
        print("[CEO] Unexpected error:", e)
        return None


# ========== script entry ==========
if __name__ == "__main__":
    try:
        generate_take_action_report()
    except Exception as e:
        print("[Main] TakeAction crashed:", e)
    try:
        generate_ceo_must_contact_report(send_notifications=False)
    except Exception as e:
        print("[Main] CEO report crashed:", e)