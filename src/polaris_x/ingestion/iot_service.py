"""IoT Ingestion Service for The Things Stack v3 OTAA uplinks.

Guarantees atomic, savepoint-isolated database persistence and idempotency
anchored on (dev_eui, session_id, f_cnt).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Tuple
from uuid import UUID

from dateutil.parser import isoparse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from polaris_x.db.models import IOTUplink, MonitoringLocation, Sensor, SensorKind, SensorMeasurement, SensorNode
from polaris_x.ingestion.iot_schemas import TTSWebhookPayload, normalize_tts_telemetry

logger = logging.getLogger(__name__)


def ingest_tts_uplink_transactional(
    session: Session,
    raw_payload: Dict[str, Any],
) -> Tuple[Dict[str, Any], int]:
    """Ingests a TTS v3 OTAA uplink payload atomically within a savepoint.

    Returns:
        (response_body, http_status_code)
    """
    # 1. Validate payload schema
    try:
        parsed = TTSWebhookPayload.model_validate(raw_payload)
    except Exception as exc:
        logger.warning(f"Rejected invalid TTS payload: {exc}")
        return {"error": "unprocessable_entity", "message": str(exc)}, 422

    dev_eui = parsed.end_device_ids.dev_eui
    session_id = parsed.uplink_message.session_key_id
    f_cnt = parsed.uplink_message.f_cnt

    # 2. Resolve SensorNode
    node = session.query(SensorNode).filter(
        (SensorNode.dev_eui == dev_eui) | (SensorNode.node_identifier == dev_eui)
    ).one_or_none()

    if node is None and parsed.end_device_ids.device_id:
        node = session.query(SensorNode).filter_by(
            node_identifier=parsed.end_device_ids.device_id
        ).one_or_none()

    if node is None:
        logger.warning(f"Uplink rejected: Node with DevEUI '{dev_eui}' is not provisioned.")
        return {"error": "not_found", "message": f"Device {dev_eui} is not provisioned."}, 404

    # 3. Reject inactive or decommissioned stations before any persistence or status update
    if not node.active or node.status in ("retired", "decommissioned"):
        logger.warning(f"Uplink rejected: Station '{dev_eui}' is inactive or {node.status}.")
        return {
            "error": "forbidden",
            "message": f"Station {dev_eui} is inactive or decommissioned.",
        }, 403

    # 4. Parse and assign timestamps
    try:
        lns_received_at = isoparse(parsed.uplink_message.received_at)
        if lns_received_at.tzinfo is None:
            lns_received_at = lns_received_at.replace(tzinfo=timezone.utc)
    except Exception:
        lns_received_at = datetime.now(timezone.utc)

    backend_received_at = datetime.now(timezone.utc)
    # In V1 prototype, device-sampling time remains strictly NULL unless verified
    sampled_at = None

    # 4. Capture immutable location snapshot
    location_id = None
    location_name_snapshot = None
    location_point_snapshot = None

    if node.location_id:
        loc = session.get(MonitoringLocation, node.location_id)
        if loc:
            location_id = loc.id
            location_name_snapshot = loc.name
            location_point_snapshot = loc.point

    # 5. Extract RF and Gateway metadata
    rx_metadata = parsed.uplink_message.rx_metadata or []
    gateway_count = len(rx_metadata) if rx_metadata else 1
    rssi_dbm = None
    snr_db = None
    frequency_hz = None

    if rx_metadata:
        # Pick best gateway reception by SNR or RSSI
        best_rx = max(
            rx_metadata,
            key=lambda m: (m.get("snr") if m.get("snr") is not None else -999, m.get("rssi") if m.get("rssi") is not None else -999)
        )
        if best_rx.get("rssi") is not None:
            rssi_dbm = int(best_rx["rssi"])
        if best_rx.get("snr") is not None:
            snr_db = Decimal(str(best_rx["snr"]))

    # 6. Savepoint-isolated atomic persistence
    nested = session.begin_nested()
    try:
        insert_stmt = (
            insert(IOTUplink)
            .values(
                node_id=node.id,
                location_id=location_id,
                location_name_snapshot=location_name_snapshot,
                location_point=location_point_snapshot,
                provider_type="the_things_stack",
                dev_eui=dev_eui,
                session_id=session_id,
                f_cnt=f_cnt,
                f_port=parsed.uplink_message.f_port,
                correlation_ids=parsed.correlation_ids,
                rssi_dbm=rssi_dbm,
                snr_db=snr_db,
                frequency_hz=frequency_hz,
                gateway_count=gateway_count,
                rx_metadata=rx_metadata,
                sampled_at=sampled_at,
                transmitted_at=None,
                lns_received_at=lns_received_at,
                backend_received_at=backend_received_at,
                raw_payload=raw_payload,
            )
            .on_conflict_do_nothing(
                index_elements=["dev_eui", "session_id", "f_cnt"]
            )
            .returning(IOTUplink.id)
        )
        uplink_id = session.execute(insert_stmt).scalar_one_or_none()

        if uplink_id is None:
            # Duplicate delivery detected via unique constraint conflict
            nested.rollback()
            return {
                "status": "duplicate_ignored",
                "dev_eui": dev_eui,
                "session_id": session_id,
                "f_cnt": f_cnt,
            }, 200

        # 7. Normalize measurements and link to uplink
        normalized = normalize_tts_telemetry(parsed.uplink_message.decoded_payload or {})
        for m in normalized:
            # Find or auto-bind sensor for this node
            sensor = session.query(Sensor).filter_by(
                node_id=node.id,
                sensor_identifier=m.sensor_identifier
            ).one_or_none()

            if sensor is None:
                sensor = Sensor(
                    node_id=node.id,
                    sensor_identifier=m.sensor_identifier,
                    kind=SensorKind(m.kind),
                    unit=m.unit,
                )
                session.add(sensor)
                session.flush()

            meas = SensorMeasurement(
                sensor_id=sensor.id,
                uplink_id=uplink_id,
                measured_at=None,
                received_at=lns_received_at,
                value_numeric=m.value_numeric,
                raw_value_numeric=m.raw_value_numeric,
                raw_value_unit=m.raw_value_unit,
                quality_flag=m.quality_flag,
            )
            session.add(meas)

        # 8. Update node telemetry health
        node.last_seen_at = lns_received_at
        node.last_f_cnt = f_cnt
        node.last_session_id = session_id
        for m in normalized:
            if m.sensor_identifier == "battery_voltage" and m.value_numeric is not None:
                node.battery_voltage = m.value_numeric

        nested.commit()  # Release savepoint into outer transaction
        return {
            "status": "created",
            "uplink_id": str(uplink_id),
            "dev_eui": dev_eui,
            "measurements_count": len(normalized),
        }, 201

    except Exception:
        nested.rollback()
        raise
