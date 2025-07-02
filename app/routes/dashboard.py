from flask import Blueprint, render_template, session, redirect, url_for
from utils import load_latest_loans  # adjust path if needed

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
def dashboard_home():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()

    # Build summary stats for top cards
    stats = {
        "total_loans": len(df),
        "critical_loans": len(df[df["Risk Level"] == "Critical"]),
        "active_borrowers": len(df[df["Activity Status"] == "Active"]),
        "with_title": len(df[df["Has Title"] == True]),
        "no_contract": len(df[df["Has Contract"] == False]),
        "with_guarantor": len(df[df["Has Guarantor"] == True])
    }

    # Convert DataFrame to dict for rendering in HTML
    table_rows = df.to_dict(orient="records")

    return render_template("dashboard.html", stats=stats, table_rows=table_rows)