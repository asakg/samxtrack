from flask import Blueprint, render_template
from utils import load_latest_loans

medium_risk_bp = Blueprint("medium_risk", __name__, url_prefix="/dashboard/medium-risk")

@medium_risk_bp.route("/")
def show_medium_risk_loans():
    df = load_latest_loans()
    # Only include "At Risk" (exclude "High Risk")
    medium_df = df[df["Risk Level"] == "At Risk"]
    return render_template("dashboardsidebar/medium_risk_loans.html", loans=medium_df.to_dict(orient="records"))