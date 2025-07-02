from flask import Blueprint, render_template, session, redirect, url_for
from utils import load_latest_loans
import datetime

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
def dashboard_home():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()

    # Safety check
    if df.empty:
        return render_template("dashboard.html", error="No data available")

    # Normalize column names if needed
    df.columns = [col.strip() for col in df.columns]

    # 1. Total loans
    total_loans = len(df)

    # 2. Critical loans = 3+ weeks behind
    current_week = datetime.datetime.utcnow().isocalendar().week
    def get_weeks_behind(row):
        try:
            last_collected = int(row["Last W Collected"].replace("W", ""))
            return current_week - last_collected
        except:
            return None

    df["Weeks Behind"] = df.apply(get_weeks_behind, axis=1)
    critical_loans = len(df[df["Weeks Behind"] >= 3])

    # 3. Active borrowers
    active_borrowers = len(df[df["Group"].str.lower() == "active"])

    # 4. Inactive = not "active" or 2+ weeks behind
    inactive_borrowers = len(df[
        (df["Group"].str.lower() != "active") | (df["Weeks Behind"] >= 2)
    ])

    # 5. Loans with Title
    df["Has Title"] = df["Title Ownership"].astype(str).str.upper().isin(["OWN", "SAM"])
    with_title = df["Has Title"].sum()

    # 6. With Guarantor
    df["Has Guarantor"] = df["Guarantor"].notna()
    with_guarantor = df["Has Guarantor"].sum()

    # 7. Missing Contract
    df["Has Contract"] = df["Contract"].astype(str).str.lower() == "yes"
    no_contract = (~df["Has Contract"]).sum()

    summary_stats = {
        "Total Loans": total_loans,
        "Critical Loans": critical_loans,
        "Active Borrowers": active_borrowers,
        "Inactive Borrowers": inactive_borrowers,
        "Loans with Title": with_title,
        "With Guarantor": with_guarantor,
        "Missing Contract": no_contract
    }

    # Pass both full df and summary stats to template
    return render_template(
        "dashboard.html",
        df=df.to_dict(orient="records"),
        summary=summary_stats
    )