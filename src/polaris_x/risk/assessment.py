from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Mapping
from uuid import UUID

from polaris_x.db.models import RiskAssessment

REQUIRED_FEATURES = ("weather", "iot", "terrain", "vegetation", "fuel")
MODEL_NAME = "assessment-foundation"
MODEL_VERSION = "1.0"


@dataclass(frozen=True)
class AssessmentInput:
    location_id: UUID
    assessed_at: datetime
    features: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    required_features: tuple[str, ...] = REQUIRED_FEATURES
    model_name: str = MODEL_NAME
    model_version: str = MODEL_VERSION


@dataclass(frozen=True)
class AssessmentResult:
    location_id: UUID
    assessed_at: datetime
    model_name: str
    model_version: str
    assessment_status: str
    score: None = None
    risk_level: None = None
    feature_snapshot: dict[str, Any] = field(default_factory=dict)
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    data_quality: dict[str, Any] = field(default_factory=dict)
    uncertainty: dict[str, Any] = field(default_factory=dict)
    input_provenance: dict[str, Any] = field(default_factory=dict)


def _validate_input(item: AssessmentInput) -> None:
    if item.assessed_at.tzinfo is None or item.assessed_at.utcoffset() is None:
        raise ValueError("assessed_at must be timezone-aware")
    if not item.model_name.strip() or not item.model_version.strip():
        raise ValueError("model_name and model_version are required")
    if not isinstance(item.features, Mapping) or not isinstance(item.provenance, Mapping):
        raise ValueError("features and provenance must be mappings")
    for name, value in item.features.items():
        if isinstance(value, float) and not isfinite(value):
            raise ValueError(f"feature {name!r} must be finite")


def assess(item: AssessmentInput) -> AssessmentResult:
    _validate_input(item)
    missing: list[dict[str, str]] = []
    assessed_at = item.assessed_at.astimezone(timezone.utc)
    for name in item.required_features:
        if name not in item.features:
            missing.append({"feature": name, "reason": "not_available"})
            continue
        provenance = item.provenance.get(name)
        if not isinstance(provenance, Mapping):
            missing.append({"feature": name, "reason": "missing_provenance"})
            continue
        observed_at = provenance.get("observed_at") or provenance.get("valid_at")
        max_age_seconds = provenance.get("max_age_seconds")
        if observed_at is None or max_age_seconds is None:
            missing.append({"feature": name, "reason": "missing_freshness_metadata"})
            continue
        if isinstance(observed_at, str):
            try:
                observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            except ValueError:
                missing.append({"feature": name, "reason": "invalid_provenance_timestamp"})
                continue
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
            missing.append({"feature": name, "reason": "invalid_provenance_timestamp"})
            continue
        if not isinstance(max_age_seconds, (int, float)) or max_age_seconds < 0:
            missing.append({"feature": name, "reason": "invalid_freshness_metadata"})
            continue
        age_seconds = (assessed_at - observed_at.astimezone(timezone.utc)).total_seconds()
        if age_seconds < 0 or age_seconds > max_age_seconds:
            missing.append({"feature": name, "reason": "stale"})
    quality = {
        "status": "insufficient",
        "missing_features": missing,
        "validated": not missing,
    }
    evidence = {
        "interpretation": "Environmental assessment foundation only; no risk score calculated.",
        "limitations": [
            "No validated environmental feature pipeline is available.",
            "This result is not a fire-occurrence probability.",
        ],
    }
    return AssessmentResult(
        location_id=item.location_id,
        assessed_at=assessed_at,
        model_name=item.model_name,
        model_version=item.model_version,
        assessment_status="insufficient_data",
        feature_snapshot=dict(item.features),
        evidence_summary=evidence,
        data_quality=quality,
        uncertainty={"status": "not_quantified", "reason": "insufficient_data"},
        input_provenance=dict(item.provenance),
    )


def persist_assessment(session, result: AssessmentResult) -> RiskAssessment:
    assessment = RiskAssessment(
        location_id=result.location_id,
        assessed_at=result.assessed_at,
        model_name=result.model_name,
        model_version=result.model_version,
        assessment_status=result.assessment_status,
        risk_level=result.risk_level,
        score=result.score,
        feature_snapshot=result.feature_snapshot,
        evidence_summary=result.evidence_summary,
        data_quality=result.data_quality,
        uncertainty=result.uncertainty,
        input_provenance=result.input_provenance,
    )
    session.add(assessment)
    session.flush()
    return assessment
