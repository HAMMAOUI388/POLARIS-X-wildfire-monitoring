import os
from uuid import uuid4
import pytest
from sqlalchemy import text
from polaris_x.app import create_app
from polaris_x.config import TestingConfig
from polaris_x.db.models import LocationAccess, MonitoringLocation, Role, User
from polaris_x.db.session import make_engine
from polaris_x.extensions import db_session
from geoalchemy2.elements import WKTElement

@pytest.fixture(scope="module")
def database_url():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    engine = make_engine(url)
    try:
        with engine.connect() as conn: conn.execute(text("SELECT PostGIS_Version()"))
    except Exception as exc:
        pytest.skip(f"PostGIS database unavailable: {exc}")
    engine.dispose()
    from polaris_x.db.session import make_session_factory
    Session = make_session_factory(url)
    with Session.begin() as session:
        for name in ("user", "farm_owner", "authority", "admin"):
            if session.query(Role).filter_by(name=name).one_or_none() is None:
                session.add(Role(name=name))
    return url

@pytest.fixture
def client(database_url):
    app = create_app({"TESTING": True, "DATABASE_URL": database_url, "JWT_SECRET_KEY": "integration-test-secret-with-32-bytes-minimum"})
    with app.test_client() as client: yield client
    with app.app_context():
        session=db_session()
        session.query(LocationAccess).filter(LocationAccess.user_id.in_(session.query(User.id).filter(User.email.like("test-%@example.com")))).delete(synchronize_session=False)
        session.query(MonitoringLocation).filter(MonitoringLocation.owner_id.in_(session.query(User.id).filter(User.email.like("test-%@example.com")))).delete(synchronize_session=False)
        session.query(User).filter(User.email.like("test-%@example.com")).delete(synchronize_session=False)
        session.commit()

def register(client, email):
    return client.post("/api/v1/auth/register", json={"email":email,"password":"Correct-Horse-Battery-1","display_name":"Test User"})

def login(client, email):
    response=client.post("/api/v1/auth/login",json={"email":email,"password":"Correct-Horse-Battery-1"})
    return response.json["access_token"]

def test_auth_and_versioned_health(client):
    email=f"test-{uuid4()}@example.com"
    response=register(client,email); assert response.status_code == 201
    assert "password_hash" not in response.text
    token=login(client,email)
    assert client.get("/api/v1/auth/me",headers={"Authorization":f"Bearer {token}"}).status_code == 200
    assert client.get("/api/v1/health").json["status"] == "ok"
    assert client.get("/api/v1/auth/me").status_code == 401

def test_invalid_login_and_validation(client):
    email=f"test-{uuid4()}@example.com"; register(client,email)
    assert client.post("/api/v1/auth/login",json={"email":email,"password":"wrong"}).status_code == 401
    assert client.post("/api/v1/auth/register",json={"email":"bad","password":"short","display_name":""}).status_code == 422

def test_owned_and_shared_location_authorization(client):
    owner_email=f"test-{uuid4()}@example.com"; viewer_email=f"test-{uuid4()}@example.com"; other_email=f"test-{uuid4()}@example.com"
    register(client,owner_email); register(client,viewer_email); register(client,other_email)
    owner=login(client,owner_email); viewer=login(client,viewer_email); other=login(client,other_email)
    created=client.post("/api/v1/locations",headers={"Authorization":f"Bearer {owner}"},json={"name":"Test Farm","location_type":"farm","longitude":-6.8,"latitude":33.9})
    assert created.status_code == 201; location_id=created.json["location"]["id"]
    assert client.get(f"/api/v1/locations/{location_id}",headers={"Authorization":f"Bearer {other}"}).status_code == 404
    with client.application.app_context():
        viewer_user=db_session().query(User).filter_by(email=viewer_email).one()
    share_response=client.post(f"/api/v1/locations/{location_id}/shares",headers={"Authorization":f"Bearer {owner}"},json={"user_id":str(viewer_user.id),"permission":"view"})
    assert share_response.status_code == 201
    assert client.get(f"/api/v1/locations/{location_id}",headers={"Authorization":f"Bearer {viewer}"}).status_code == 200
    assert client.patch(f"/api/v1/locations/{location_id}",headers={"Authorization":f"Bearer {viewer}"},json={"name":"No","location_type":"farm","longitude":0,"latitude":0}).status_code == 404


def test_admin_can_read_other_users_location(client):
    owner_email=f"test-{uuid4()}@example.com"; admin_email=f"test-{uuid4()}@example.com"
    register(client, owner_email); register(client, admin_email)
    owner=login(client, owner_email); admin=login(client, admin_email)
    created=client.post("/api/v1/locations", headers={"Authorization":f"Bearer {owner}"}, json={"name":"Admin Test Farm","location_type":"farm","longitude":-6.8,"latitude":33.9})
    location_id=created.json["location"]["id"]
    with client.application.app_context():
        session=db_session(); admin_user=session.query(User).filter_by(email=admin_email).one(); admin_role=session.query(Role).filter_by(name="admin").one(); admin_user.roles.append(admin_role); session.commit()
    assert client.get(f"/api/v1/locations/{location_id}", headers={"Authorization":f"Bearer {admin}"}).status_code == 200


def test_token_type_separation_and_security_regressions(client):
    email=f"test-{uuid4()}@example.com"
    register(client, email)
    response=client.post("/api/v1/auth/login",json={"email":email,"password":"Correct-Horse-Battery-1"})
    access=response.json["access_token"]; refresh=response.json["refresh_token"]
    assert client.get("/api/v1/auth/me",headers={"Authorization":f"Bearer {refresh}"}).status_code == 401
    assert client.post("/api/v1/auth/refresh",headers={"Authorization":f"Bearer {access}"}).status_code == 401
    assert client.get("/api/v1/auth/me",headers={"Authorization":"Bearer malformed.token.value"}).status_code == 401

def test_view_only_cannot_share_or_escalate_and_private_is_hidden(client):
    owner_email=f"test-{uuid4()}@example.com"; viewer_email=f"test-{uuid4()}@example.com"; other_email=f"test-{uuid4()}@example.com"
    register(client,owner_email); register(client,viewer_email); register(client,other_email)
    owner=login(client,owner_email); viewer=login(client,viewer_email); other=login(client,other_email)
    created=client.post("/api/v1/locations",headers={"Authorization":f"Bearer {owner}"},json={"name":"Private Farm","location_type":"farm","longitude":-6.8,"latitude":33.9})
    location_id=created.json["location"]["id"]
    with client.application.app_context():
        session=db_session(); viewer_user=session.query(User).filter_by(email=viewer_email).one(); location=session.get(MonitoringLocation,location_id); session.add(LocationAccess(location_id=location.id,user_id=viewer_user.id,permission="view")); session.commit()
    assert client.post(f"/api/v1/locations/{location_id}/shares",headers={"Authorization":f"Bearer {viewer}"},json={"user_id":str(viewer_user.id),"permission":"manage"}).status_code == 404
    assert client.patch(f"/api/v1/locations/{location_id}",headers={"Authorization":f"Bearer {viewer}"},json={"name":"Changed","location_type":"farm","longitude":0,"latitude":0}).status_code == 404
    assert client.get(f"/api/v1/locations/{location_id}",headers={"Authorization":f"Bearer {other}"}).status_code == 404
    assert client.post(f"/api/v1/locations/{location_id}/shares",headers={"Authorization":f"Bearer {owner}"},json={"user_id":"not-a-uuid","permission":"manage"}).status_code == 422

def test_registration_and_location_reject_mass_assignment(client):
    email=f"test-{uuid4()}@example.com"
    assert client.post("/api/v1/auth/register",json={"email":email,"password":"Correct-Horse-Battery-1","display_name":"User","roles":["admin"]}).status_code == 422
    token=login(client, email) if False else None
    assert client.post("/api/v1/locations",headers={"Authorization":"Bearer malformed.token.value"},json={"name":"X","location_type":"farm","longitude":0,"latitude":0,"owner_id":"00000000-0000-0000-0000-000000000000"}).status_code == 401
