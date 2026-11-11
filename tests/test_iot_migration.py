"""Unit tests for IoT migration safety guards, preflight data-loss checks, and FK discovery."""
from __future__ import annotations

import pytest
from sqlalchemy import text
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

_mig_path = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0007_iot_telemetry_foundation.py"
_spec = importlib.util.spec_from_file_location("mig_0007", str(_mig_path))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
find_exact_fk = _mod.find_exact_fk


def test_find_exact_fk_fails_on_missing_constraint():
    """find_exact_fk raises RuntimeError when foreign key does not exist."""
    mock_bind = MagicMock()
    mock_bind.execute.return_value.fetchall.return_value = []

    with pytest.raises(RuntimeError) as exc:
        find_exact_fk(mock_bind, "public.non_existent", "a_id", "public.target", "id")
    assert "No FK constraint found connecting" in str(exc.value)


def test_find_exact_fk_fails_on_ambiguous_constraints():
    """find_exact_fk raises RuntimeError when multiple foreign keys match."""
    mock_bind = MagicMock()
    mock_bind.execute.return_value.fetchall.return_value = [("fk_1",), ("fk_2",)]

    with pytest.raises(RuntimeError) as exc:
        find_exact_fk(mock_bind, "public.table_a", "b_id", "public.table_b", "id")
    assert "Found multiple constraints" in str(exc.value)


def test_find_exact_fk_succeeds_on_single_match():
    """find_exact_fk returns constraint name when exactly one match exists."""
    mock_bind = MagicMock()
    mock_bind.execute.return_value.fetchall.return_value = [("fk_sensors_node_id_sensor_nodes",)]

    res = find_exact_fk(mock_bind, "public.sensors", "node_id", "public.sensor_nodes", "id")
    assert res == "fk_sensors_node_id_sensor_nodes"
