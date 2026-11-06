from flask_jwt_extended import JWTManager
from flask import jsonify
from sqlalchemy.orm import Session
from polaris_x.db.session import make_engine

jwt = JWTManager()

def init_database(app):
    engine = make_engine(app.config["DATABASE_URL"])
    app.extensions["polaris_engine"] = engine
    app.extensions["polaris_session_factory"] = __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(bind=engine, expire_on_commit=False)
    @app.teardown_appcontext
    def dispose_database(_exception=None):
        return None

def db_session():
    from flask import current_app, g
    if "polaris_db" not in g:
        g.polaris_db = current_app.extensions["polaris_session_factory"]()
    return g.polaris_db

def close_db(_exception=None):
    from flask import g
    session = g.pop("polaris_db", None)
    if session is not None:
        session.close()


def configure_jwt_errors():
    @jwt.unauthorized_loader
    def unauthorized(_reason):
        return jsonify(error={"code": "authentication_error", "message": "Authentication token is required."}), 401
    @jwt.invalid_token_loader
    def invalid_token(_reason):
        return jsonify(error={"code": "authentication_error", "message": "Authentication token is invalid or expired."}), 401
    @jwt.expired_token_loader
    def expired_token(_header, _payload):
        return jsonify(error={"code": "authentication_error", "message": "Authentication token is invalid or expired."}), 401
    @jwt.token_in_blocklist_loader
    def token_in_blocklist(_header, _payload):
        return False
    @jwt.revoked_token_loader
    def revoked_token(_header, _payload):
        return jsonify(error={"code": "authentication_error", "message": "Authentication token is revoked."}), 401
    @jwt.needs_fresh_token_loader
    def fresh_token_required(_header, _payload):
        return jsonify(error={"code": "authentication_error", "message": "A fresh access token is required."}), 401
