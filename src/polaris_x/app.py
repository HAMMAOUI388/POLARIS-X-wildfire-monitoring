from flask import Flask
from flask_cors import CORS
from polaris_x.config import Config
from polaris_x.extensions import close_db, configure_jwt_errors, init_database, jwt
from polaris_x.api.errors import register_error_handlers

def create_app(config_object=None):
    app=Flask(__name__)
    config = config_object or Config
    if isinstance(config, dict):
        app.config.from_object(Config)
        app.config.from_mapping(config)
    else:
        app.config.from_object(config)
    secret = app.config.get("JWT_SECRET_KEY")
    if not app.config.get("TESTING") and (not secret or len(secret) < 32 or secret in {"change-me", "replace-with-a-long-random-secret"}):
        raise RuntimeError("JWT_SECRET_KEY must be a random value of at least 32 characters")
    init_database(app); app.teardown_appcontext(close_db); jwt.init_app(app); configure_jwt_errors()
    if app.config.get("CORS_ORIGINS"):
        CORS(
            app,
            origins=app.config["CORS_ORIGINS"],
            allow_private_network=app.config.get("CORS_ALLOW_PRIVATE_NETWORK", False),
        )
    register_error_handlers(app)
    from polaris_x.api.auth import bp as auth_bp
    from polaris_x.api.health import bp as health_bp
    from polaris_x.api.locations import bp as locations_bp
    from polaris_x.api.geospatial import bp as geospatial_bp
    from polaris_x.api.geography import bp as geography_bp
    from polaris_x.api.alerts import bp as alerts_bp
    from polaris_x.api.chat import bp as chat_bp
    from polaris_x.api.subscriptions import bp as subscriptions_bp
    from polaris_x.api.authority import bp as authority_bp
    from polaris_x.api.admin import bp as admin_bp
    from polaris_x.api.iot import bp as iot_bp
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(health_bp, url_prefix="/api/v1")
    app.register_blueprint(locations_bp, url_prefix="/api/v1/locations")
    app.register_blueprint(alerts_bp)
    app.register_blueprint(chat_bp)
    # These Phase 4/6 blueprints existed but were not mounted in create_app.
    app.register_blueprint(geospatial_bp, url_prefix="/api/v1/geospatial")
    app.register_blueprint(geography_bp, url_prefix="/api/v1/geography")
    # Phase 11 subscriptions and professional portal authorization foundations.
    app.register_blueprint(subscriptions_bp, url_prefix="/api/v1/subscriptions")
    app.register_blueprint(authority_bp, url_prefix="/api/v1/authority")
    app.register_blueprint(admin_bp, url_prefix="/api/v1/admin")
    # Phase 13 IoT telemetry foundation.
    app.register_blueprint(iot_bp, url_prefix="/api/v1/iot")
    return app
