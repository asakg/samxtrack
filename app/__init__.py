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

    return app