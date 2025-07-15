from flask import Blueprint, render_template
from utils import load_latest_loans

high_risk_bp = Blueprint("high-risk", __name__, url_prefix="/dashboard/high-risk")

@high_risk_bp.route("/")
def show_high_risk_loans():
    df = load_latest_loans()
    # Only include "High Risk"
    high_df = df[df["Risk Level"] == "High Risk"]
    return render_template("dashboardsidebar/high_risk_loans.html", loans=high_df.to_dict(orient="records"))