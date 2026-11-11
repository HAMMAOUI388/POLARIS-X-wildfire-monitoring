"""Synthetic test fixtures representing The Things Stack v3 OTAA uplinks."""
from __future__ import annotations

from typing import Any, Dict


def make_tts_uplink_payload(
    dev_eui: str = "0004A30B001F1234",
    device_id: str = "esp32-station-atlas-01",
    session_key_id: str = "01HXYZ1234567890ABCDEF",
    f_cnt: int = 42,
    temperature: float = 24.5,
    humidity: float = 45.2,
    pressure: float = 1013.25,
    battery: float = 3.85,
    received_at: str = "2026-11-11T12:00:00.123456789Z",
) -> Dict[str, Any]:
    """Generates a standard TTS v3 OTAA webhook uplink payload."""
    return {
        "end_device_ids": {
            "device_id": device_id,
            "dev_eui": dev_eui,
            "join_eui": "70B3D57ED0000000",
        },
        "correlation_ids": [
            "as:up:01HXYZ1234567890ABCDEF",
            "rpc:/ttn.lorawan.v3.AppAs/HandleUplink:01HXYZ1234567890ABCDEF",
        ],
        "received_at": "2026-11-11T12:00:00.150Z",
        "uplink_message": {
            "session_key_id": session_key_id,
            "f_cnt": f_cnt,
            "f_port": 1,
            "frm_payload": "AZ...",
            "decoded_payload": {
                "temperature": temperature,
                "humidity": humidity,
                "pressure": pressure,
                "battery": battery,
            },
            "rx_metadata": [
                {
                    "gateway_ids": {"gateway_id": "rak-gw-ifrane-01"},
                    "rssi": -82,
                    "channel_rssi": -82,
                    "snr": 9.2,
                    "received_at": received_at,
                },
                {
                    "gateway_ids": {"gateway_id": "dragino-gw-ifrane-02"},
                    "rssi": -94,
                    "channel_rssi": -94,
                    "snr": 4.1,
                    "received_at": received_at,
                },
            ],
            "received_at": received_at,
        },
    }
