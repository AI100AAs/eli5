from __future__ import annotations

from flask import Flask
from flask.json.provider import DefaultJSONProvider
from werkzeug.middleware.proxy_fix import ProxyFix

from .api import register_api_routes
from .config import load_settings
from .db import close_db, initialize_database, verify_database_schema
from .shells import shell_settings
from .views import register_page_routes


class StrictJSONProvider(DefaultJSONProvider):
    def dumps(self, obj, **kwargs):
        kwargs.setdefault("allow_nan", False)
        return super().dumps(obj, **kwargs)


def create_app(test_config: dict | None = None, shell_variant: str | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder=None)
    app.json = StrictJSONProvider(app)
    app.config.update(load_settings(shell_variant=shell_variant))

    if test_config:
        app.config.update(test_config)

    app.config.update(shell_settings(app.config.get("APP_SHELL")))

    if app.config["TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1, x_port=1, x_proto=1, x_prefix=1)

    if app.config["AUTO_MIGRATE"]:
        initialize_database(app.config)
    else:
        verify_database_schema(app.config)
    app.teardown_appcontext(close_db)

    register_api_routes(app)
    register_page_routes(app)
    return app
