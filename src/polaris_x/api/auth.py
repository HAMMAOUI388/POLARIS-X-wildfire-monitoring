from uuid import UUID
from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required
from pydantic import ValidationError
from werkzeug.security import check_password_hash, generate_password_hash
from polaris_x.api.errors import error_response
from polaris_x.api.schemas import LoginRequest, RegisterRequest
from polaris_x.db.models import Role, User
from polaris_x.extensions import db_session

bp = Blueprint("auth", __name__, url_prefix="/auth")
def public_user(user): return {"id": str(user.id), "email": user.email, "display_name": user.display_name, "roles": sorted(role.name for role in user.roles)}
def parse(schema): return schema.model_validate(request.get_json(silent=False) or {})
def tokens(user, fresh): return {"access_token": create_access_token(identity=str(user.id), fresh=fresh), "refresh_token": create_refresh_token(identity=str(user.id))}
@bp.post("/register")
def register():
    data = parse(RegisterRequest); session = db_session()
    role = session.query(Role).filter_by(name="user").one()
    user = User(email=str(data.email).lower(), display_name=data.display_name, password_hash=generate_password_hash(data.password)); user.roles.append(role); session.add(user); session.commit(); return jsonify(user=public_user(user)), 201
@bp.post("/login")
def login():
    data = parse(LoginRequest); user = db_session().query(User).filter_by(email=str(data.email).lower()).one_or_none()
    if user is None or not user.is_active or not check_password_hash(user.password_hash, data.password): return error_response("invalid_credentials", "Invalid email or password.", 401)
    return jsonify(user=public_user(user), **tokens(user, True))
@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh(): return jsonify(access_token=create_access_token(identity=get_jwt_identity(), fresh=False))
@bp.get("/me")
@jwt_required()
def me():
    user = db_session().get(User, UUID(get_jwt_identity()))
    if user is None or not user.is_active: return error_response("unauthorized", "Authentication required.", 401)
    return jsonify(user=public_user(user))
