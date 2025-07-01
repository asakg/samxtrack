from flask import Blueprint, render_template, request, redirect, url_for, session, flash

login_bp = Blueprint("login", __name__)

# Hardcoded user credentials
VALID_USER = {"username": "admin", "password": "password123"}

@login_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == VALID_USER["username"] and password == VALID_USER["password"]:
            session["logged_in"] = True
            return redirect(url_for("dashboard.dashboard_home"))
        else:
            flash("Invalid username or password", "danger")
            return redirect(url_for("login.login"))

    return render_template("login.html")

@login_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login.login"))