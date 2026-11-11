"""Validation and normalization schemas for IoT telemetry payloads."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class TTSEndDeviceIds(BaseModel):
    dev_eui: str = Field(..., description="Canonical 64-bit IEEE hardware address (hex string)")
    device_id: Optional[str] = None
    join_eui: Optional[str] = None

    @field_validator("dev_eui")
    @classmethod
    def validate_dev_eui(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("dev_eui cannot be empty")
        return cleaned


class TTSUplinkMessage(BaseModel):
    session_key_id: str = Field(..., description="Opaque LoRaWAN session key identifier")
    f_cnt: int = Field(..., ge=0, description="Uplink frame counter")
    f_port: int = Field(1, ge=1, le=255)
    received_at: str = Field(..., description="Network Server reception timestamp (ISO 8601)")
    decoded_payload: Optional[Dict[str, Any]] = None
    rx_metadata: Optional[List[Dict[str, Any]]] = None

    @field_validator("session_key_id")
    @classmethod
    def validate_session_key_id(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("session_key_id cannot be empty for OTAA devices")
        return cleaned


class TTSWebhookPayload(BaseModel):
    end_device_ids: TTSEndDeviceIds
    uplink_message: TTSUplinkMessage
    correlation_ids: List[str] = Field(default_factory=list)
    received_at: Optional[str] = None


class NormalizedMeasurement(BaseModel):
    sensor_identifier: str
    kind: str
    unit: str
    value_numeric: Optional[Decimal]
    value_text: Optional[str] = None
    raw_value_numeric: Optional[Decimal] = None
    raw_value_unit: Optional[str] = None
    quality_flag: str = "good"
    calibration_version: Optional[str] = None


def normalize_tts_telemetry(decoded: Dict[str, Any]) -> List[NormalizedMeasurement]:
    """Extracts, normalizes, and validates physical variables from decoded payload.

    Supports BME280 (temperature, humidity, pressure) and battery supply voltage.
    """
    measurements: List[NormalizedMeasurement] = []

    # 1. Temperature (°C)
    raw_temp = decoded.get("temperature") or decoded.get("temperature_c") or decoded.get("temp")
    if raw_temp is not None:
        try:
            val = Decimal(str(raw_temp))
            if -40 <= val <= 85:
                quality = "good" if -20 <= val <= 60 else "suspect"
            else:
                quality = "erroneous"
            measurements.append(NormalizedMeasurement(
                sensor_identifier="bme280_temp",
                kind="bme280",
                unit="celsius",
                value_numeric=val,
                raw_value_numeric=val,
                raw_value_unit="celsius",
                quality_flag=quality,
            ))
        except Exception:
            pass

    # 2. Relative Humidity (%)
    raw_hum = decoded.get("humidity") or decoded.get("relative_humidity") or decoded.get("rh")
    if raw_hum is not None:
        try:
            val = Decimal(str(raw_hum))
            if 0 <= val <= 100:
                quality = "good" if val <= 95 else "suspect"
            else:
                quality = "erroneous"
            measurements.append(NormalizedMeasurement(
                sensor_identifier="bme280_humidity",
                kind="bme280",
                unit="percent",
                value_numeric=val,
                raw_value_numeric=val,
                raw_value_unit="percent",
                quality_flag=quality,
            ))
        except Exception:
            pass

    # 3. Barometric Pressure (hPa)
    raw_press = decoded.get("pressure") or decoded.get("surface_pressure") or decoded.get("pressure_hpa")
    if raw_press is not None:
        try:
            val = Decimal(str(raw_press))
            # Convert Pa to hPa if sent in Pa (e.g. 101325 -> 1013.25)
            if val > 2000:
                raw_val = val
                val = val / Decimal("100")
                raw_unit = "pascal"
            else:
                raw_val = val
                raw_unit = "hpa"
            if 300 <= val <= 1100:
                quality = "good" if 800 <= val <= 1100 else "suspect"
            else:
                quality = "erroneous"
            measurements.append(NormalizedMeasurement(
                sensor_identifier="bme280_pressure",
                kind="bme280",
                unit="hpa",
                value_numeric=val,
                raw_value_numeric=raw_val,
                raw_value_unit=raw_unit,
                quality_flag=quality,
            ))
        except Exception:
            pass

    # 4. Battery Voltage (V)
    raw_bat = decoded.get("battery") or decoded.get("battery_voltage") or decoded.get("vbat")
    if raw_bat is not None:
        try:
            val = Decimal(str(raw_bat))
            # Convert mV to V if sent in mV (e.g. 3700 -> 3.70)
            if val > 10:
                raw_val = val
                val = val / Decimal("1000")
                raw_unit = "millivolt"
            else:
                raw_val = val
                raw_unit = "volt"
            if 0 <= val <= 6:
                if val >= Decimal("3.5"):
                    quality = "good"
                elif val >= Decimal("3.2"):
                    quality = "low_battery"
                else:
                    quality = "critical"
            else:
                quality = "erroneous"
            measurements.append(NormalizedMeasurement(
                sensor_identifier="battery_voltage",
                kind="battery",
                unit="volt",
                value_numeric=val,
                raw_value_numeric=raw_val,
                raw_value_unit=raw_unit,
                quality_flag=quality,
            ))
        except Exception:
            pass

    return measurements
