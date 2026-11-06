from flask import jsonify
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException
from flask_jwt_extended.exceptions import JWTExtendedException
from werkzeug.exceptions import BadRequest

def error_response(code, message, status, details=None):
    body = {"error": {"code": code, "message": message}}
    if details is not None: body["error"]["details"] = details
    return jsonify(body), status

def register_error_handlers(app):
    @app.errorhandler(ValidationError)
    def validation_error(error): return error_response("validation_error", "Request validation failed.", 422, error.errors())
    @app.errorhandler(IntegrityError)
    def integrity_error(_error):
        from polaris_x.extensions import db_session
        db_session().rollback(); return error_response("conflict", "The request conflicts with existing data.", 409)
    @app.errorhandler(JWTExtendedException)
    def jwt_error(error): return error_response("authentication_error", "Authentication token is invalid or expired.", 401)
    @app.errorhandler(BadRequest)
    def bad_request(error): return error_response("bad_request", "Request body must contain valid JSON.", 400)
    @app.errorhandler(HTTPException)
    def http_error(error): return error_response(error.name.lower().replace(" ", "_"), error.description, error.code)
    @app.errorhandler(Exception)
    def internal_error(error):
        app.logger.exception("Unhandled application error", exc_info=error); return error_response("internal_error", "An internal error occurred.", 500)
