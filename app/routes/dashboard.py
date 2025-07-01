from flask import Blueprint, render_template, session, redirect, url_for

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
def dashboard_home():
    if not session.get("logged_in"):
        return redirect(url_for("login.login"))

    return render_template("dashboard.html")