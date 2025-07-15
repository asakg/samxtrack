from flask import Blueprint, render_template, session, redirect, url_for
from utils import load_latest_loans

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
def dashboard_home():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()

    # Add "Risk Level" column dynamically
    def determine_risk(row):
        if row.get("Days Late", 0) >= 21:
            return "Critical"
        elif row.get("Days Late", 0) >= 7:
            return "Medium"
        elif row.get("Has Title") == False or row.get("Has Contract") == False:
            return "Medium"
        else:
            return "Low"

    df["Risk Level"] = df.apply(determine_risk, axis=1)

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

    import re

    def extract_paid_off_amount(name):
        if not isinstance(name, str):
            return 0
        match = re.search(r"\$\s*([\d,\.]+)", name)
        if match:
            return float(match.group(1).replace(',', ''))
        return 0

    paid_off_names = df[df["State"] == "Paid Off"]["Loan Name"]
    paid_off_amt = paid_off_names.apply(extract_paid_off_amount).sum()

    stats.update({
        "total_outstanding": round(df["Principal Balance"].sum(), 2),
        "total_weekly_due": round(df["Next Payment Amount"].sum(), 2),
        "avg_weekly_payment": round(df[df["Next Payment Amount"] > 0]["Next Payment Amount"].mean(), 2),
        "avg_weeks_remaining": int(df["Remaining Payments"].mean()),
        "past_due_count": len(df[df["Days Late"] > 0]),
        "critical_late_count": len(df[df["Days Late"] > 21]),
        "unsecured_loans": len(df[(df["Has Contract"] == False) | (df["Has Title"] == False)]),
        "unique_borrowers": df["Group"].nunique(),
        "percent_paid_off": round((paid_off_amt) / (df["Principal Balance"].sum() + paid_off_amt) * 100, 1) if (df["Principal Balance"].sum() + paid_off_amt) else 0
    })

    stats['paid_off'] = len(df[df["Principal Balance"] == 0])
    stats['loans_past_due'] = len(df[df["Days Late"] > 0])

    stats_block3 = {
        "Outstanding Principal": f"${stats['total_outstanding']:,.2f}",
        "Loans Past Due": stats["past_due_count"],
        "3+ Weeks Late": stats["critical_late_count"],
        "No Contract / Title": stats["unsecured_loans"],
        "% Paid Off": f"{stats['percent_paid_off']}%"
    }

    medium_risk_df = df[(df["Risk Level"] == "Medium") & (df["Principal Balance"] > 0)]

    past_due_amt = df[(df["Status"] == "3+W Critical") | (df["Days Late"] > 21)]["Principal Balance"].sum()
    good_amt = df[df["Status"].isin(["1W Behind", "Ongoing"])]["Principal Balance"].sum()

    total_active_loans_amt = good_amt + past_due_amt
    total_loan_amt = total_active_loans_amt + paid_off_amt

    amount_breakdown = {
        "Paid Off": float(paid_off_amt),
        "In Good Standing": float(good_amt),
        "Past Due": float(past_due_amt),
        "Total Active Loans": float(total_active_loans_amt),
        "Total Loan Amount": float(total_loan_amt)
    }

    bar_colors = {
        "In Good Standing": "#4CAF50",     # Green
        "Paid Off": "#9E9E9E",             # Grey
        "Past Due": "#F44336",             # Red
        "Total Active Loans": "#9C27B0",   # Purple
        "Total Loan Amount": "#90CAF9"     # Light Blue (base), handled in HTML for partial overlay
    }

    return render_template(
        "dashboard.html",
        stats=stats,
        table_rows=df.to_dict(orient="records"),
        charts_data=charts_data,
        stats_block3=stats_block3,
        medium_risk_rows=medium_risk_df.to_dict(orient="records"),
        amount_breakdown=amount_breakdown,
        bar_colors=bar_colors
    )