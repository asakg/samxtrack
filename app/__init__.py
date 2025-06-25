from flask import Flask

def create_app():
    app = Flask(__name__)
    app.secret_key = "replace_this_with_a_secure_key"

    from .routes.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)

    return app