"""Add IoT telemetry foundation, RESTRICT deletion policies, and spatial provenance.

Revision ID: 0007_iot_telemetry_foundation
Revises: 0006_alert_recipients
"""
import logging
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geography

logger = logging.getLogger(__name__)

revision = "0007_iot_telemetry_foundation"
down_revision = "0006_alert_recipients"
branch_labels = None
depends_on = None


def find_exact_fk(bind, source_table_qualified: str, source_col: str,
                  target_table_qualified: str, target_col: str) -> str:
    """Finds the exact foreign key constraint name from PostgreSQL catalog or aborts.

    Uses schema-qualified table OIDs to guarantee unambiguous constraint resolution.
    """
    query = sa.text("""
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_class s ON s.oid = c.conrelid
        JOIN pg_class t ON t.oid = c.confrelid
        JOIN pg_attribute sa ON sa.attrelid = s.oid AND sa.attnum = c.conkey[1]
        JOIN pg_attribute ta ON ta.attrelid = t.oid AND ta.attnum = c.confkey[1]
        WHERE s.oid = to_regclass(:source_table_qualified)
          AND t.oid = to_regclass(:target_table_qualified)
          AND sa.attname = :source_col
          AND ta.attname = :target_col
          AND c.contype = 'f'
          AND array_length(c.conkey, 1) = 1;
    """)
    rows = bind.execute(query, {
        "source_table_qualified": source_table_qualified,
        "source_col": source_col,
        "target_table_qualified": target_table_qualified,
        "target_col": target_col,
    }).fetchall()

    if len(rows) == 0:
        raise RuntimeError(
            f"Foreign key discovery failed: No FK constraint found connecting "
            f"'{source_table_qualified}.{source_col}' -> '{target_table_qualified}.{target_col}'. "
            "Aborting before destructive DDL."
        )
    if len(rows) > 1:
        names = [r[0] for r in rows]
        raise RuntimeError(
            f"Foreign key discovery ambiguous: Found multiple constraints {names} connecting "
            f"'{source_table_qualified}.{source_col}' -> '{target_table_qualified}.{target_col}'. "
            "Aborting before destructive DDL."
        )
    return rows[0][0]


def upgrade():
    bind = op.get_bind()

    # 1. Expand PostgreSQL enum sensor_kind with 'battery'
    op.execute("ALTER TYPE sensor_kind ADD VALUE IF NOT EXISTS 'battery'")

    # 2. Add LoRaWAN and operational fields to sensor_nodes
    op.add_column("sensor_nodes", sa.Column("dev_eui", sa.String(32), nullable=True))
    op.add_column("sensor_nodes", sa.Column("join_eui", sa.String(32), nullable=True))
    op.add_column("sensor_nodes", sa.Column("hardware_version", sa.String(40), nullable=True))
    op.add_column("sensor_nodes", sa.Column("firmware_version", sa.String(40), nullable=True))
    op.add_column("sensor_nodes", sa.Column("battery_voltage", sa.Numeric(4, 2), nullable=True))
    op.add_column("sensor_nodes", sa.Column("last_session_id", sa.String(120), nullable=True))
    op.add_column("sensor_nodes", sa.Column("last_f_cnt", sa.BigInteger(), nullable=True))
    op.add_column("sensor_nodes", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sensor_nodes", sa.Column("status", sa.String(30), nullable=False, server_default="active"))
    op.create_unique_constraint("uq_sensor_nodes_dev_eui", "sensor_nodes", ["dev_eui"])

    # 2b. Explicitly backfill pre-existing inactive stations so they are not marked active
    op.execute("UPDATE sensor_nodes SET status = 'retired' WHERE active IS FALSE;")

    # 3. Create immutable iot_uplinks table with spatial snapshot and RESTRICT foreign key
    op.create_table(
        "iot_uplinks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sensor_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("monitoring_locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("location_name_snapshot", sa.String(160), nullable=True),
        sa.Column("location_point", Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=True),
        sa.Column("provider_type", sa.String(30), nullable=False, server_default="the_things_stack"),
        sa.Column("dev_eui", sa.String(32), nullable=False),
        sa.Column("session_id", sa.String(120), nullable=False),
        sa.Column("f_cnt", sa.BigInteger(), nullable=False),
        sa.Column("f_port", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("correlation_ids", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("rssi_dbm", sa.SmallInteger(), nullable=True),
        sa.Column("snr_db", sa.Numeric(5, 2), nullable=True),
        sa.Column("frequency_hz", sa.BigInteger(), nullable=True),
        sa.Column("gateway_count", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("rx_metadata", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_uptime_ms", sa.BigInteger(), nullable=True),
        sa.Column("transmitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lns_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("backend_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("raw_payload", postgresql.JSONB, nullable=False),
        sa.UniqueConstraint("dev_eui", "session_id", "f_cnt", name="uq_iot_uplinks_dev_session_fcnt"),
    )
    op.create_index("ix_iot_uplinks_node_received", "iot_uplinks", ["node_id", "lns_received_at"])
    op.create_index("ix_iot_uplinks_location_point", "iot_uplinks", ["location_point"], postgresql_using="gist")

    # 4. Remove ON DELETE CASCADE from existing sensors table and replace with RESTRICT
    sensor_fk = find_exact_fk(bind, "public.sensors", "node_id", "public.sensor_nodes", "id")
    op.drop_constraint(sensor_fk, "sensors", type_="foreignkey")
    op.create_foreign_key(
        "fk_sensors_node_id_sensor_nodes",
        "sensors", "sensor_nodes",
        ["node_id"], ["id"],
        ondelete="RESTRICT"
    )

    # 5. Remove ON DELETE CASCADE from existing sensor_measurements and replace with RESTRICT
    measurement_fk = find_exact_fk(bind, "public.sensor_measurements", "sensor_id", "public.sensors", "id")
    op.drop_constraint(measurement_fk, "sensor_measurements", type_="foreignkey")
    op.create_foreign_key(
        "fk_sensor_measurements_sensor_id_sensors",
        "sensor_measurements", "sensors",
        ["sensor_id"], ["id"],
        ondelete="RESTRICT"
    )

    # 6. Update sensor_measurements: nullable measured_at, nullable raw_payload, add uplink link
    op.alter_column("sensor_measurements", "measured_at", nullable=True)
    op.alter_column("sensor_measurements", "raw_payload", nullable=True)
    op.add_column("sensor_measurements", sa.Column("uplink_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("iot_uplinks.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("sensor_measurements", sa.Column("raw_value_numeric", sa.Numeric(16, 6), nullable=True))
    op.add_column("sensor_measurements", sa.Column("raw_value_unit", sa.String(40), nullable=True))
    op.create_index("ix_sensor_measurements_uplink", "sensor_measurements", ["uplink_id"])
    op.create_index("ix_sensor_measurements_sensor_received", "sensor_measurements", ["sensor_id", "received_at"])


def downgrade():
    bind = op.get_bind()

    # 1. Acquire table locks immediately before any preflight queries
    bind.execute(sa.text("""
        LOCK TABLE iot_uplinks, sensor_measurements, sensor_nodes
        IN ACCESS EXCLUSIVE MODE;
    """))

    # 2. Comprehensive preflight data-loss checks
    uplinks_count = bind.execute(sa.text("SELECT COUNT(*) FROM iot_uplinks")).scalar()
    if uplinks_count > 0:
        raise RuntimeError(
            f"Downgrade aborted: 'iot_uplinks' contains {uplinks_count} records. "
            "Dropping this table would permanently destroy historical radio telemetry, "
            "gateway metadata, and immutable spatial coordinate snapshots. "
            "You must manually inspect, export, or purge these records before downgrading."
        )

    sm_data_count = bind.execute(sa.text("""
        SELECT COUNT(*) FROM sensor_measurements
        WHERE uplink_id IS NOT NULL
           OR raw_value_numeric IS NOT NULL
           OR raw_value_unit IS NOT NULL
    """)).scalar()
    if sm_data_count > 0:
        raise RuntimeError(
            f"Downgrade aborted: {sm_data_count} rows in 'sensor_measurements' have non-null values "
            "in 'uplink_id', 'raw_value_numeric', or 'raw_value_unit'. Dropping these columns "
            "would permanently destroy uncalibrated/raw telemetry data."
        )

    sm_null_count = bind.execute(sa.text("""
        SELECT COUNT(*) FROM sensor_measurements
        WHERE measured_at IS NULL
           OR raw_payload IS NULL
    """)).scalar()
    if sm_null_count > 0:
        raise RuntimeError(
            f"Downgrade aborted: {sm_null_count} rows in 'sensor_measurements' have NULL "
            "'measured_at' or 'raw_payload'. Reverting to NOT NULL constraints cannot succeed "
            "without corrupting data, fabricating false timestamps, or deleting historical records."
        )

    sn_data_count = bind.execute(sa.text("""
        SELECT COUNT(*) FROM sensor_nodes
        WHERE dev_eui IS NOT NULL
           OR join_eui IS NOT NULL
           OR hardware_version IS NOT NULL
           OR firmware_version IS NOT NULL
           OR battery_voltage IS NOT NULL
           OR last_session_id IS NOT NULL
           OR last_f_cnt IS NOT NULL
           OR last_seen_at IS NOT NULL
           OR status IS DISTINCT FROM 'active'
    """)).scalar()
    if sn_data_count > 0:
        raise RuntimeError(
            f"Downgrade aborted: {sn_data_count} rows in 'sensor_nodes' contain provisioned "
            "LoRaWAN identifiers (dev_eui/join_eui), hardware metadata, telemetry status, or battery "
            "state. Dropping these columns would permanently erase node provisioning records."
        )

    # 3. Revert sensor_measurements
    op.drop_index("ix_sensor_measurements_sensor_received", table_name="sensor_measurements")
    op.drop_index("ix_sensor_measurements_uplink", table_name="sensor_measurements")
    op.drop_column("sensor_measurements", "raw_value_unit")
    op.drop_column("sensor_measurements", "raw_value_numeric")
    op.drop_column("sensor_measurements", "uplink_id")
    op.alter_column("sensor_measurements", "raw_payload", nullable=False)
    op.alter_column("sensor_measurements", "measured_at", nullable=False)

    # Revert foreign key to CASCADE
    meas_fk = find_exact_fk(bind, "public.sensor_measurements", "sensor_id", "public.sensors", "id")
    op.drop_constraint(meas_fk, "sensor_measurements", type_="foreignkey")
    op.create_foreign_key(
        "fk_sensor_measurements_sensor_id_sensors",
        "sensor_measurements", "sensors",
        ["sensor_id"], ["id"],
        ondelete="CASCADE"
    )

    # Revert sensors foreign key to CASCADE
    sensor_fk = find_exact_fk(bind, "public.sensors", "node_id", "public.sensor_nodes", "id")
    op.drop_constraint(sensor_fk, "sensors", type_="foreignkey")
    op.create_foreign_key(
        "fk_sensors_node_id_sensor_nodes",
        "sensors", "sensor_nodes",
        ["node_id"], ["id"],
        ondelete="CASCADE"
    )

    # 4. Drop iot_uplinks
    op.drop_index("ix_iot_uplinks_location_point", table_name="iot_uplinks")
    op.drop_index("ix_iot_uplinks_node_received", table_name="iot_uplinks")
    op.drop_constraint("uq_iot_uplinks_dev_session_fcnt", "iot_uplinks", type_="unique")
    op.drop_table("iot_uplinks")

    # 5. Revert sensor_nodes
    op.drop_constraint("uq_sensor_nodes_dev_eui", "sensor_nodes", type_="unique")
    op.drop_column("sensor_nodes", "status")
    op.drop_column("sensor_nodes", "last_seen_at")
    op.drop_column("sensor_nodes", "last_f_cnt")
    op.drop_column("sensor_nodes", "last_session_id")
    op.drop_column("sensor_nodes", "battery_voltage")
    op.drop_column("sensor_nodes", "firmware_version")
    op.drop_column("sensor_nodes", "hardware_version")
    op.drop_column("sensor_nodes", "join_eui")
    op.drop_column("sensor_nodes", "dev_eui")

    # 6. Enum downgrade disclosure
    logger.warning(
        "PostgreSQL does not support removing values from enum types. "
        "The label 'battery' remains permanently in 'sensor_kind'."
    )
