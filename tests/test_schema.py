from polaris_x.db.base import Base
import polaris_x.db.models  # noqa: F401

def test_expected_tables_and_spatial_columns():
    assert len(Base.metadata.tables) == 27
    assert Base.metadata.tables["monitoring_locations"].c.point.type.srid == 4326
    assert Base.metadata.tables["hiking_routes"].c.path.type.geometry_type == "LINESTRING"
    assert "ix_monitoring_locations_point" in {i.name for i in Base.metadata.tables["monitoring_locations"].indexes}
    assert Base.metadata.tables["chat_messages"].c.role is not None
    assert "alert_recipients" in Base.metadata.tables
    assert "iot_uplinks" in Base.metadata.tables
    assert Base.metadata.tables["iot_uplinks"].c.location_point.type.srid == 4326

def test_integrity_constraints_are_declared():
    table = Base.metadata.tables["monitoring_subscriptions"]
    assert any(c.name == "ck_monitoring_subscriptions_radius_positive" for c in table.constraints)
    assert any(c.name == "uq_subscription_user_location" for c in table.constraints)
    assert Base.metadata.tables["user_roles"].primary_key.columns.keys() == ["user_id", "role_id"]
    assert any(c.name == "ck_monitoring_subscriptions_subscription_one_target" for c in Base.metadata.tables["monitoring_subscriptions"].constraints)
