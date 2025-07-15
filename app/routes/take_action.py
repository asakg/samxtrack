from flask import Blueprint, render_template, request, redirect
import os, json
from datetime import datetime, timedelta
import pandas as pd
from utils import load_latest_loans

take_action_bp = Blueprint("take_action", __name__, url_prefix="/dashboard/actions")

@take_action_bp.route("/", methods=["GET", "POST"])
def show_take_action():
    today = datetime.today()
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    week_tag = friday.strftime("%Y-%m-%d")

    # Ensure folder exists and define JSON file path
    os.makedirs("data/weekly_actions", exist_ok=True)
    json_path = os.path.join("data", "weekly_actions", f"{week_tag}.json")

    # Load past incomplete actions (from all previous weeks)
    past_entries = []
    if os.path.exists("data/weekly_actions"):
        for fname in os.listdir("data/weekly_actions"):
            fpath = os.path.join("data/weekly_actions", fname)
            with open(fpath, "r") as f:
                for entry in json.load(f):
                    if not entry.get("contacted") or not entry.get("note"):
                        past_entries.append(entry)

    # Handle form submission
    if request.method == "POST":
        form_data = request.form.to_dict()
        submitted = []
        for key in form_data:
            if key.startswith("check_"):
                loan_key = key.replace("check_", "")
                note = form_data.get(f"note_{loan_key}", "").strip()
                submitted.append({
                    "week": week_tag,
                    "loan_key": loan_key,
                    "borrower": loan_key.split("|")[0],
                    "balance": float(loan_key.split("|")[1]),
                    "contacted": True,
                    "note": note
                })
        with open(json_path, "w") as f:
            json.dump(submitted, f, indent=2)
        return redirect("/dashboard/actions")

    # Load current loans and filter
    df = load_latest_loans()
    df["Loan Key"] = df["Borrower"].astype(str) + "|" + df["Principal Balance"].astype(str)

    def row_entry(row, category):
        key = row["Loan Key"]
        match = next((x for x in past_entries if x["loan_key"] == key), {})
        return {
            "loan_key": key,
            "borrower": row["Borrower"],
            "balance": row["Principal Balance"],
            "category": category,
            "note": match.get("note", ""),
            "contacted": match.get("contacted", False)
        }

    # High Risk: >21 days late
    high_risk = df[(df["Risk Level"] == "High Risk") & (df["Days Late"] > 21)]
    high_risk_entries = [row_entry(row, "High Risk") for _, row in high_risk.iterrows()]

    # Critical: >21 days late, no title, no guarantor
    critical = df[
        (df["Risk Level"] == "Critical") &
        (df["Days Late"] > 21) &
        (df["Has Guarantor"] == False) &
        (df["Has Title"] == False)
    ]
    critical_entries = [row_entry(row, "Critical") for _, row in critical.iterrows()]

    return render_template(
        "dashboardsidebar/takeaction/take_action.html",
        high_risk_loans=high_risk_entries,
        critical_loans=critical_entries,
        week=week_tag
    )
@take_action_bp.route("/history")
def take_action_history():
    history = []
    base_path = "data/weekly_actions"
    if os.path.exists(base_path):
        for fname in sorted(os.listdir(base_path)):
            with open(os.path.join(base_path, fname), "r") as f:
                entries = json.load(f)
                history.extend(entries)

    return render_template("dashboardsidebar/takeaction/take_action_history.html", history=history)