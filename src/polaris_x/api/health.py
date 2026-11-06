from flask import Blueprint, jsonify
from sqlalchemy import text
from polaris_x.extensions import db_session
bp = Blueprint("health", __name__)
@bp.get("/health")
def health():
    try: db_session().execute(text("SELECT 1")); return jsonify(status="ok", database="ok")
    except Exception: return jsonify(status="degraded", database="unavailable"), 503
