from flask import Blueprint, render_template, session, redirect, url_for
from utils import load_latest_loans  # adjust path if needed

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
def dashboard_home():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    df = load_latest_loans()
    
    # Example summary counts (you can send to template)
    total_loans = len(df)
    critical_loans = len(df[df["Risk Level"] == "Critical"])
    active_borrowers = len(df[df["Activity Status"] == "Active"])
    with_title = len(df[df["Has Title"]])
    no_contract = len(df[df["Has Contract"] == False])
    with_guarantor = len(df[df["Has Guarantor"]])

    return render_template("dashboard.html", 
        df=df.to_dict(orient="records"),
        total_loans=total_loans,
        critical_loans=critical_loans,
        active_borrowers=active_borrowers,
        with_title=with_title,
        no_contract=no_contract,
        with_guarantor=with_guarantor
    )