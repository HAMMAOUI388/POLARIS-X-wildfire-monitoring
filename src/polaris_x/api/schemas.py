from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)

class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class LocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    location_type: str

    @field_validator("location_type")
    @classmethod
    def valid_location_type(cls, value):
        if value not in {"farm", "point", "campsite", "trailhead", "other"}: raise ValueError("invalid location_type")
        return value
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    description: str | None = None

class ShareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    permission: str

    @field_validator("permission")
    @classmethod
    def valid_permission(cls, value):
        if value not in {"view", "manage"}: raise ValueError("permission must be view or manage")
        return value


class SpatialQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    radius_m: float = Field(default=5000, gt=0, le=100000)
    start: str | None = None
    end: str | None = None
    page: int = Field(default=1, ge=1, le=1000000)
    limit: int = Field(default=100, ge=1, le=100)


class GeographySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(min_length=2, max_length=200)
    limit: int = Field(default=5, ge=1, le=10)
    countrycodes: str = Field(default="ma", min_length=2, max_length=20)

class GeographyReverseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)

class RoutePointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)

class RoutePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: RoutePointRequest
    destination: RoutePointRequest
    waypoints: list[RoutePointRequest] = Field(default_factory=list, max_length=5)
    profile: str = Field(default="foot", min_length=2, max_length=20)


class CreateSubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: UUID
    radius_m: float = Field(default=5000.0, gt=0, le=100000)
    minimum_severity: Literal["low", "moderate", "high", "critical"] = "low"
    enabled: bool = Field(default=True)


class UpdateSubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    radius_m: float | None = Field(default=None, gt=0, le=100000)
    minimum_severity: Literal["low", "moderate", "high", "critical"] | None = None
    enabled: bool | None = None
