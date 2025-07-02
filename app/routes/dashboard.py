from flask import Blueprint, render_template, session, redirect, url_for
from utils import load_latest_loans

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
def dashboard_home():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()

    # Pre-compute stats
    total_loans = len(df)
    critical_loans = len(df[df["Risk Level"] == "Critical"])
    active_borrowers = len(df[df["Activity Status"] == "Active"])
    inactive_borrowers = len(df[df["Activity Status"] == "Inactive"])
    with_title = len(df[df["Has Title"]])
    no_contract = len(df[df["Has Contract"] == False])
    with_guarantor = len(df[df["Has Guarantor"]])

    stats = {
        "total_loans": total_loans,
        "critical_loans": critical_loans,
        "active_borrowers": active_borrowers,
        "inactive_borrowers": inactive_borrowers,
        "title_loans": with_title,
        "missing_contract": no_contract,
        "with_guarantor": with_guarantor
    }

    return render_template(
        "dashboard.html",
        stats=stats,  # ✅ Pass stats
        table_rows=df.to_dict(orient="records")
    )