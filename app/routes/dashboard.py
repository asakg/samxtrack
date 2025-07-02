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
    no_title_guarantor = len(df[(df["Has Title"] == False) & (df["Has Guarantor"] == False)])

    stats = {
        "total_loans": total_loans,
        "critical_loans": critical_loans,
        "active_borrowers": active_borrowers,
        "inactive_borrowers": inactive_borrowers,
        "title_loans": with_title,
        "missing_contract": no_contract,
        "with_guarantor": with_guarantor,
        "no_title_guarantor": no_title_guarantor
    }

    # Charts breakdown
    charts_data = {
        "loan_status": {
            "Paid Off": len(df[df["Principal Balance"] == 0]),
            "Remaining": len(df[df["Principal Balance"] > 0])
        },
        "risk_distribution": {
            "Critical": critical_loans,
            "Non-Critical": total_loans - critical_loans
        },
        "borrower_activity": {
            "Active": active_borrowers,
            "Inactive": inactive_borrowers
        },
        "payment_status": df["Status"].value_counts().to_dict(),
        "collateral": {
            "Has Title": with_title,
            "No Title": total_loans - with_title
        }
    }

    stats.update({
    "total_outstanding": round(df["Principal Balance"].sum(), 2),
    "total_weekly_due": round(df["Next Payment Amount"].sum(), 2),
    "avg_weekly_payment": round(df[df["Next Payment Amount"] > 0]["Next Payment Amount"].mean(), 2),
    "avg_weeks_remaining": int(df["Remaining Payments"].mean()),
    "past_due_count": len(df[df["Days Late"] > 0]),
    "critical_late_count": len(df[df["Days Late"] > 21]),
    "unsecured_loans": len(df[(df["Has Contract"] == False) | (df["Has Title"] == False)]),
    "unique_borrowers": df["Group"].nunique(),
    "percent_paid_off": round((len(df[df["Principal Balance"] == 0]) / len(df)) * 100, 1)
    })

    return render_template(
        "dashboard.html",
        stats=stats,
        table_rows=df.to_dict(orient="records"),
        charts_data=charts_data  # ✅ match updated variable in HTML
    )