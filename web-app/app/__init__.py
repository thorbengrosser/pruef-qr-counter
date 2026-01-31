"""Flask application factory. No cookies, no session."""
import logging
import os
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import SERVER_SECRET
from .db import init_db

_webapp_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEV_SECRET = b"dev-secret-change-in-production"


def create_app():
    app = Flask(
        __name__,
        static_folder=os.path.join(_webapp_root, "static"),
        template_folder=os.path.join(_webapp_root, "templates"),
    )
    app.config["SECRET_KEY"] = SERVER_SECRET.decode("utf-8") if isinstance(SERVER_SECRET, bytes) else str(SERVER_SECRET)
    # Do not use sessions or cookies
    app.config["SESSION_COOKIE_HTTPONLY"] = False
    app.config["SESSION_COOKIE_SAMESITE"] = None
    app.config["SESSION_COOKIE_SECURE"] = False
    # Disable session entirely so no Set-Cookie
    app.config["SESSION_TYPE"] = None

    # Trust exactly one proxy (X-Forwarded-For first entry = client)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    from . import routes
    app.register_blueprint(routes.bp)

    with app.app_context():
        init_db()

    if SERVER_SECRET == _DEV_SECRET:
        logging.getLogger(__name__).warning(
            "SERVER_SECRET is the default dev value. Set SERVER_SECRET env var in production."
        )

    return app
