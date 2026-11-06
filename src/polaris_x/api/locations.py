from uuid import UUID
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from polaris_x.api.authz import current_user, location_for_user
from polaris_x.api.errors import error_response
from polaris_x.api.schemas import LocationRequest, ShareRequest
from polaris_x.db.models import LocationAccess, LocationType, MonitoringLocation, User
from polaris_x.extensions import db_session
bp = Blueprint("locations", __name__, url_prefix="/locations")
def output(item):
    point = to_shape(item.point)
    return {"id": str(item.id), "owner_id": str(item.owner_id), "name": item.name, "location_type": item.location_type.value, "description": item.description, "point": {"longitude": point.x, "latitude": point.y}}
def parse(): return LocationRequest.model_validate(request.get_json(silent=False) or {})
@bp.get("")
@jwt_required()
def list_locations():
    user=current_user(); session=db_session(); ids=session.query(LocationAccess.location_id).filter_by(user_id=user.id).subquery(); items=session.query(MonitoringLocation).filter((MonitoringLocation.owner_id==user.id)|(MonitoringLocation.id.in_(ids))).all(); return jsonify(locations=[output(x) for x in items])
@bp.post("")
@jwt_required()
def create_location():
    data=parse(); user=current_user(); session=db_session(); location=MonitoringLocation(owner_id=user.id,name=data.name,location_type=LocationType(data.location_type),point=WKTElement(f"POINT({data.longitude} {data.latitude})",srid=4326),description=data.description); session.add(location); session.commit(); return jsonify(location=output(location)),201
@bp.get("/<uuid:location_id>")
@jwt_required()
def get_location(location_id):
    location, response=location_for_user(location_id); return response or jsonify(location=output(location))
@bp.patch("/<uuid:location_id>")
@jwt_required()
def update_location(location_id):
    location,response=location_for_user(location_id,write=True)
    if response: return response
    data=parse(); location.name=data.name; location.location_type=LocationType(data.location_type); location.point=WKTElement(f"POINT({data.longitude} {data.latitude})",srid=4326); location.description=data.description; db_session().commit(); return jsonify(location=output(location))
@bp.delete("/<uuid:location_id>")
@jwt_required()
def delete_location(location_id):
    location,response=location_for_user(location_id,write=True)
    if response: return response
    db_session().delete(location); db_session().commit(); return "",204
@bp.post("/<uuid:location_id>/shares")
@jwt_required()
def share_location(location_id):
    location,response=location_for_user(location_id,write=True)
    if response: return response
    data=ShareRequest.model_validate(request.get_json(silent=False) or {}); session=db_session(); target=session.get(User,data.user_id)
    if target is None: return error_response("not_found","User not found.",404)
    grant=LocationAccess(location_id=location.id,user_id=target.id,permission=data.permission); session.add(grant); session.commit(); return jsonify(user_id=str(target.id),permission=grant.permission),201
