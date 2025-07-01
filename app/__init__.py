from flask import Flask
from flask_session import Session

def create_app():
    app = Flask(__name__)
    app.secret_key = "super-secret-key"  # Change this in production!
    app.config["SESSION_TYPE"] = "filesystem"
    Session(app)

    # Register routes
    from app.routes.login import login_bp
    from app.routes.dashboard import dashboard_bp
    app.register_blueprint(login_bp)
    app.register_blueprint(dashboard_bp)

    return app