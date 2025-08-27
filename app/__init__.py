from flask import Flask, redirect, url_for, session, request, flash
from flask_session import Session
from datetime import timedelta, datetime

def create_app():
    app = Flask(__name__)
    app.secret_key = "super-secret-key"  # TODO: change in production / move to env
    app.config["SESSION_TYPE"] = "filesystem"

    # Idle timeout window (30 minutes)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

    Session(app)

    # Register routes
    from app.routes.login import login_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.loan_summary import loan_summary_bp
    from app.routes.medium_risk_loans import medium_risk_bp
    from app.routes.high_risk_loans import high_risk_bp
    from app.routes.take_action import take_action_bp

    app.register_blueprint(login_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(loan_summary_bp)
    app.register_blueprint(medium_risk_bp)
    app.register_blueprint(high_risk_bp)
    app.register_blueprint(take_action_bp)

    @app.before_request
    def require_login_and_enforce_timeout():
        """Redirect unauthenticated users and expire idle sessions."""
        # Allow unauthenticated access to login page and static assets
        if request.path.startswith("/static") or request.path == "/login":
            return None

        # Require login for everything else
        if not session.get("logged_in"):
            return redirect(url_for("login.login"))

        # Enforce idle timeout
        now_ts = int(datetime.utcnow().timestamp())
        last_seen = session.get("last_seen")
        if last_seen is not None:
            idle_seconds = now_ts - int(last_seen)
            if idle_seconds > int(app.config["PERMANENT_SESSION_LIFETIME"].total_seconds()):
                session.clear()
                flash("Your session expired due to inactivity. Please log in again.", "warning")
                return redirect(url_for("login.login"))

        # Refresh activity timestamp
        session["last_seen"] = now_ts
        return None

    @app.after_request
    def add_no_cache_headers(response):
        """Prevent cached pages from appearing after logout/back button."""
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    return app