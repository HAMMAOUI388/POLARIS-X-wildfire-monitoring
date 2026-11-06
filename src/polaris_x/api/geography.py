from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import ValidationError

from polaris_x.api.errors import error_response
from polaris_x.api.schemas import GeographyReverseRequest, GeographySearchRequest, RoutePreviewRequest
from polaris_x.integrations.geography import GeoPoint, GraphHopperAdapter, NominatimAdapter, OSRMAdapter, ProviderError, RequestClient

bp = Blueprint("geography", __name__)

def _adapter_client():
    return RequestClient(current_app.config["GEOGRAPHY_USER_AGENT"], current_app.config["GEOGRAPHY_PROVIDER_TIMEOUT"], retries=current_app.config["GEOGRAPHY_PROVIDER_RETRIES"])

def _nominatim():
    adapter = current_app.extensions.get("polaris_nominatim")
    if adapter is None:
        adapter = NominatimAdapter(current_app.config["NOMINATIM_URL"], _adapter_client())
        current_app.extensions["polaris_nominatim"] = adapter
    return adapter

def _routing():
    adapter = current_app.extensions.get("polaris_routing")
    if adapter is not None: return adapter
    client = _adapter_client()
    provider = current_app.config["ROUTING_PROVIDER"]
    if provider == "osrm":
        endpoint = current_app.config["OSRM_URL"]
        if not endpoint: raise ProviderError("provider_not_configured", "The routing provider is not configured.", 503)
        adapter = OSRMAdapter(endpoint, client)
        current_app.extensions["polaris_routing"] = adapter
        return adapter
    if provider == "graphhopper":
        key = current_app.config["GRAPHHOPPER_API_KEY"]
        if not key: raise ProviderError("provider_not_configured", "The routing provider is not configured.", 503)
        adapter = GraphHopperAdapter(current_app.config["GRAPHHOPPER_URL"], key, client)
        current_app.extensions["polaris_routing"] = adapter
        return adapter
    raise ProviderError("provider_not_configured", "The routing provider is not configured.", 503)

def _provider_error(exc):
    return error_response(exc.code, exc.message, exc.status)

def _point(result):
    return {"longitude": result.longitude, "latitude": result.latitude}

@bp.get("/search")
@jwt_required()
def search():
    try: data = GeographySearchRequest.model_validate(request.args.to_dict())
    except ValidationError as exc: return error_response("validation_error", "Request validation failed.", 422, exc.errors())
    try:
        results = _nominatim().search(data.q, data.limit, data.countrycodes)
        return jsonify(provider="nominatim", attribution="OpenStreetMap contributors; geocoding by Nominatim", results=[{"provider_id": item.provider_id, "display_name": item.display_name, "point": _point(item.point), "category": item.category, "type": item.raw_type} for item in results])
    except ProviderError as exc: return _provider_error(exc)

@bp.get("/reverse")
@jwt_required()
def reverse():
    try: data = GeographyReverseRequest.model_validate(request.args.to_dict())
    except ValidationError as exc: return error_response("validation_error", "Request validation failed.", 422, exc.errors())
    try:
        item = _nominatim().reverse(GeoPoint(data.longitude, data.latitude))
        return jsonify(provider="nominatim", attribution="OpenStreetMap contributors; geocoding by Nominatim", result={"provider_id": item.provider_id, "display_name": item.display_name, "point": _point(item.point), "category": item.category, "type": item.raw_type})
    except ProviderError as exc: return _provider_error(exc)

@bp.post("/routes/preview")
@jwt_required()
def route_preview():
    try: data = RoutePreviewRequest.model_validate(request.get_json(silent=False) or {})
    except ValidationError as exc: return error_response("validation_error", "Request validation failed.", 422, exc.errors())
    try:
        result = _routing().preview(GeoPoint(data.origin.longitude, data.origin.latitude), GeoPoint(data.destination.longitude, data.destination.latitude), [GeoPoint(item.longitude, item.latitude) for item in data.waypoints], data.profile)
        return jsonify({"provider": result.provider, "profile": result.profile, "distance_m": result.distance_m, "duration_s": result.duration_s, "geometry": result.geometry, "waypoints": [_point(point) for point in result.waypoints], "saved": False, "message": "Preview only; explicit confirmation is required before saving a route."})
    except ProviderError as exc: return _provider_error(exc)
