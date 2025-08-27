from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import os, json, base64, hmac
import boto3

login_bp = Blueprint("login", __name__)

# Simple in-process cache (disable by setting LOGIN_USERS_CACHE_TTL=0)
_secret_cache = None

def _load_users_from_secret():
    """
    Load users from AWS Secrets Manager.
    - Secret name from env LOGIN_USERS_SECRET (default: 'samxtrack/app-users')
    - Region from env AWS_REGION or current boto3 session region (fallback 'us-east-2')
    Supports both:
      {"users":[{"username":"full_access","password":"...","show_amounts":true}, ...]}
    and:
      {"full_access":{"password":"...","show_amounts":true}, "team_member":{...}}
    """
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache

    secret_name = os.getenv("LOGIN_USERS_SECRET", "samxtrack/app-users")
    region_name = os.getenv("AWS_REGION") or boto3.session.Session().region_name or "us-east-2"

    try:
        client = boto3.client("secretsmanager", region_name=region_name)
        resp = client.get_secret_value(SecretId=secret_name)

        # secret may be string or binary
        if "SecretString" in resp and resp["SecretString"]:
            raw = resp["SecretString"]
        else:
            raw = base64.b64decode(resp["SecretBinary"]).decode("utf-8")

        payload = json.loads(raw)

        users = {}
        # Shape 1: {"users":[{username,..}, ...]}
        if isinstance(payload, dict) and "users" in payload and isinstance(payload["users"], list):
            for u in payload["users"]:
                name = (u.get("username") or "").strip()
                if name:
                    users[name] = {
                        "password": str(u.get("password", "")),
                        "show_amounts": bool(u.get("show_amounts", False)),
                    }
        # Shape 2: {"full_access":{...}, "team_member":{...}}
        elif isinstance(payload, dict):
            for name, u in payload.items():
                if isinstance(u, dict):
                    users[str(name)] = {
                        "password": str(u.get("password", "")),
                        "show_amounts": bool(u.get("show_amounts", False)),
                    }

        _secret_cache = users
        return users
    except Exception:
        # Quiet fallback: no users (login will fail safely)
        _secret_cache = {}
        return {}

@login_bp.route("/login", methods=["GET", "POST"])
def login():
    # Already signed in? go home
    if session.get("logged_in"):
        return redirect(url_for("dashboard.dashboard_home"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        USERS = _load_users_from_secret()
        user = USERS.get(username)

        # constant-time compare avoids timing side-channel (defensive habit)
        valid = bool(user) and hmac.compare_digest(str(user.get("password", "")), password)

        if valid:
            # Minimal session payload used elsewhere in the app
            session.clear()
            session["logged_in"] = True
            session["username"] = username
            session["show_amounts"] = bool(user.get("show_amounts", False))
            # idle-timeout tracking (PERMANENT_SESSION_LIFETIME set in app factory)
            session.permanent = True
            session["last_seen"] = int(datetime.utcnow().timestamp())
            return redirect(url_for("dashboard.dashboard_home"))

        flash("Invalid username or password", "danger")
        return redirect(url_for("login.login"))

    return render_template("login.html")

@login_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login.login"))