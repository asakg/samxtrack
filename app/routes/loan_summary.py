from flask import Blueprint, render_template, session, redirect, url_for
from utils import load_latest_loans

loan_summary_bp = Blueprint("loan_summary", __name__)

@loan_summary_bp.route("/loan-summary")
def loan_summary():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()

    def determine_risk(row):
        if row.get("Days Late", 0) >= 21:
            return "Critical"
        elif row.get("Days Late", 0) >= 7:
            return "Medium"
        elif not row.get("Has Title", True) or not row.get("Has Contract", True):
            return "Medium"
        else:
            return "Low"

    df["Risk Level"] = df.apply(determine_risk, axis=1)

    stats = {
        "total_loans": len(df),
        "active_borrowers": len(df[df["Activity Status"] == "Active"]),
        "inactive_borrowers": len(df[df["Activity Status"] == "Inactive"]),
        "critical_loans": len(df[df["Risk Level"] == "Critical"]),
        "missing_contract": len(df[df["Has Contract"] == False]),
        "title_loans": len(df[df["Has Title"] == True]),
        "with_guarantor": len(df[df["Has Guarantor"] == True]),
        "no_title_no_guarantor": len(df[(df["Has Title"] == False) & (df["Has Guarantor"] == False)])
    }

    total_loans = stats["total_loans"]
    stats["critical_percentage"] = round(stats["critical_loans"] / total_loans * 100, 1) if total_loans else 0
    stats["active_percentage"] = round(stats["active_borrowers"] / total_loans * 100, 1) if total_loans else 0
    stats["inactive_percentage"] = round(stats["inactive_borrowers"] / total_loans * 100, 1) if total_loans else 0
    stats["missing_contract_percentage"] = round(stats["missing_contract"] / total_loans * 100, 1) if total_loans else 0
    stats["title_percentage"] = round(stats["title_loans"] / total_loans * 100, 1) if total_loans else 0
    stats["guarantor_percentage"] = round(stats["with_guarantor"] / total_loans * 100, 1) if total_loans else 0
    stats["no_title_guarantor_percentage"] = round(stats["no_title_no_guarantor"] / total_loans * 100, 1) if total_loans else 0

    links = {
        "total_loans": "/loan-summary/all",
        "active_borrowers": "/loan-summary/active",
        "inactive_borrowers": "/loan-summary/all",
        "critical_loans": "/loan-summary/critical-loans",
        "missing_contract": "/loan-summary/missing-contracts",
        "title_loans": "/loan-summary/with-title",
        "with_guarantor": "/loan-summary/with-guarantor",
        "no_title_guarantor": "/loan-summary/no-title-guarantor"
    }

    # Top 10 critical loans by principal balance
    top_critical = df[df["Risk Level"] == "Critical"].nlargest(10, "Principal Balance").to_dict(orient="records")
    # Top 10 loans missing contracts by principal balance
    top_missing_contracts = df[df["Has Contract"] == False].nlargest(10, "Principal Balance").to_dict(orient="records")
    # Top 10 loans with no title and no guarantor by principal balance
    top_no_title_guarantor = df[(df["Has Title"] == False) & (df["Has Guarantor"] == False)].nlargest(10, "Principal Balance").to_dict(orient="records")

    return render_template(
        "dashboardsidebar/loan_summary.html",
        stats=stats,
        links=links,
        critical_loans=top_critical,
        missing_contracts=top_missing_contracts,
        no_title_guarantor=top_no_title_guarantor
    )


# Additional routes for loan summary details
@loan_summary_bp.route("/loan-summary/all")
def all_loans():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()
    loans = df.to_dict(orient="records")
    return render_template("dashboardsidebar/loansummary/all_loans.html", loans=loans)

@loan_summary_bp.route("/loan-summary/active")
def active_borrowers():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()
    filtered = df[df["Activity Status"] == "Active"].to_dict(orient="records")
    return render_template("dashboardsidebar/loansummary/active_borrowers.html", loans=filtered)


@loan_summary_bp.route("/loan-summary/missing-contracts")
def missing_contracts():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()
    filtered = df[df["Has Contract"] == False].to_dict(orient="records")
    return render_template("dashboardsidebar/loansummary/missing_contracts.html", loans=filtered)


@loan_summary_bp.route("/loan-summary/critical-loans")
def critical_loans():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()

    def determine_risk(row):
        if row.get("Days Late", 0) >= 21:
            return "Critical"
        elif row.get("Days Late", 0) >= 7:
            return "Medium"
        elif not row.get("Has Title", True) or not row.get("Has Contract", True):
            return "Medium"
        else:
            return "Low"

    df["Risk Level"] = df.apply(determine_risk, axis=1)
    filtered = df[df["Risk Level"] == "Critical"].to_dict(orient="records")
    return render_template("dashboardsidebar/loansummary/critical_loans.html", loans=filtered)


@loan_summary_bp.route("/loan-summary/no-title-guarantor")
def no_title_guarantor():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()
    filtered = df[(df["Has Title"] == False) & (df["Has Guarantor"] == False)].to_dict(orient="records")
    return render_template("dashboardsidebar/loansummary/no_title_guarantor.html", loans=filtered)


# Route for loans with guarantor
@loan_summary_bp.route("/loan-summary/with-guarantor")
def with_guarantor():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()
    filtered = df[df["Has Guarantor"] == True].to_dict(orient="records")
    return render_template("dashboardsidebar/loansummary/with_guarantor.html", loans=filtered)


# Route for loans with title
@loan_summary_bp.route("/loan-summary/with-title")
def with_title():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()
    filtered = df[df["Has Title"] == True].to_dict(orient="records")
    return render_template("dashboardsidebar/loansummary/with_title.html", loans=filtered)

# Route for inactive borrowers
@loan_summary_bp.route("/loan-summary/inactive-borrowers")
def inactive_borrowers():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()
    filtered = df[df["Activity Status"] == "Inactive"].to_dict(orient="records")
    return render_template("dashboardsidebar/loansummary/inactive_borrowers.html", loans=filtered)