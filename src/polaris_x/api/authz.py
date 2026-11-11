from functools import wraps
from uuid import UUID
from flask import g
from flask_jwt_extended import get_jwt_identity, jwt_required
from polaris_x.db.models import LocationAccess, MonitoringLocation, Role, User
from polaris_x.extensions import db_session

def current_user():
    user = db_session().get(User, UUID(get_jwt_identity()))
    if user is None or not user.is_active:
        from flask_jwt_extended.exceptions import NoAuthorizationError
        raise NoAuthorizationError("Authentication required.")
    return user

def user_roles(user) -> set[str]:
    return {role.name for role in user.roles}

def has_role(user, *role_names) -> bool:
    return bool(user_roles(user).intersection(role_names))

def is_admin(user) -> bool:
    return has_role(user, "admin")

def is_authority(user) -> bool:
    return has_role(user, "authority")

def is_farm_owner(user) -> bool:
    return has_role(user, "farm_owner")

def roles_required(*allowed):
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapped(*args, **kwargs):
            user = current_user(); g.current_user = user
            if not {role.name for role in user.roles}.intersection(allowed):
                from polaris_x.api.errors import error_response
                return error_response("forbidden", "Insufficient role.", 403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def location_for_user(location_id, write=False):
    user = current_user(); session = db_session()
    location = session.get(MonitoringLocation, location_id)
    if location is None: return None, error_response("not_found", "Location not found.", 404)
    names = {role.name for role in user.roles}
    if "admin" in names or location.owner_id == user.id: return location, None
    grant = session.query(LocationAccess).filter_by(location_id=location.id, user_id=user.id).one_or_none()
    if grant and (not write or grant.permission == "manage"): return location, None
    from polaris_x.api.errors import error_response
    return None, error_response("not_found", "Location not found.", 404)
