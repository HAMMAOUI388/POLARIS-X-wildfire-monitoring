"""Public monitoring subscription API."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from sqlalchemy import select

from polaris_x.api.authz import current_user, is_admin, location_for_user
from polaris_x.api.errors import error_response
from polaris_x.api.schemas import CreateSubscriptionRequest, UpdateSubscriptionRequest
from polaris_x.db.models import MonitoringLocation, MonitoringSubscription, Severity
from polaris_x.extensions import db_session

bp = Blueprint("subscriptions", __name__)


def output_subscription(item: MonitoringSubscription) -> dict:
    loc = item.location
    return {
        "id": str(item.id),
        "user_id": str(item.user_id),
        "location_id": str(item.location_id) if item.location_id else None,
        "location_name": loc.name if loc else None,
        "route_id": str(item.route_id) if item.route_id else None,
        "radius_m": float(item.radius_m),
        "minimum_severity": item.minimum_severity.value,
        "enabled": item.enabled,
    }


@bp.get("")
@jwt_required()
def list_subscriptions():
    user = current_user()
    session = db_session()
    items = session.execute(
        select(MonitoringSubscription)
        .where(MonitoringSubscription.user_id == user.id)
        .order_by(MonitoringSubscription.id)
    ).scalars().all()
    return jsonify(subscriptions=[output_subscription(s) for s in items])


@bp.post("")
@jwt_required()
def create_subscription():
    data = CreateSubscriptionRequest.model_validate(request.get_json(silent=False) or {})


    user = current_user()
    session = db_session()

    location, denied = location_for_user(data.location_id, write=False)
    if denied:
        return error_response("not_found", "Location not found.", 404)

    existing = session.scalar(
        select(MonitoringSubscription).where(
            MonitoringSubscription.user_id == user.id,
            MonitoringSubscription.location_id == location.id,
        )
    )
    if existing is not None:
        return error_response("conflict", "A subscription for this location already exists.", 409)

    subscription = MonitoringSubscription(
        user_id=user.id,
        location_id=location.id,
        radius_m=Decimal(str(data.radius_m)),
        minimum_severity=Severity(data.minimum_severity),
        enabled=data.enabled,
    )
    session.add(subscription)
    session.commit()
    return jsonify(subscription=output_subscription(subscription)), 201


@bp.get("/<uuid:subscription_id>")
@jwt_required()
def get_subscription(subscription_id: UUID):
    user = current_user()
    session = db_session()
    sub = session.get(MonitoringSubscription, subscription_id)
    if sub is None or (sub.user_id != user.id and not is_admin(user)):
        return error_response("not_found", "Subscription not found.", 404)

    if sub.location_id and not is_admin(user):
        _, denied = location_for_user(sub.location_id, write=False)
        if denied:
            return error_response("not_found", "Subscription not found.", 404)

    return jsonify(subscription=output_subscription(sub))


@bp.patch("/<uuid:subscription_id>")
@jwt_required()
def update_subscription(subscription_id: UUID):
    user = current_user()
    session = db_session()
    sub = session.get(MonitoringSubscription, subscription_id)
    if sub is None or (sub.user_id != user.id and not is_admin(user)):
        return error_response("not_found", "Subscription not found.", 404)

    data = UpdateSubscriptionRequest.model_validate(request.get_json(silent=False) or {})


    if data.radius_m is not None:
        sub.radius_m = Decimal(str(data.radius_m))
    if data.minimum_severity is not None:
        sub.minimum_severity = Severity(data.minimum_severity)
    if data.enabled is not None:
        sub.enabled = data.enabled

    session.commit()
    return jsonify(subscription=output_subscription(sub))


@bp.delete("/<uuid:subscription_id>")
@jwt_required()
def delete_subscription(subscription_id: UUID):
    user = current_user()
    session = db_session()
    sub = session.get(MonitoringSubscription, subscription_id)
    if sub is None or (sub.user_id != user.id and not is_admin(user)):
        return error_response("not_found", "Subscription not found.", 404)

    session.delete(sub)
    session.commit()
    return "", 204
