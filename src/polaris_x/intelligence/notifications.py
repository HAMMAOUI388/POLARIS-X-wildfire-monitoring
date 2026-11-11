"""Notification service — provider-neutral notification delivery."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from polaris_x.db.models import (
    Alert,
    AlertRecipient,
    NotificationDeliveryAttempt,
    NotificationPreference,
    Severity,
    User,
)


NotificationChannel = Literal["in_app", "sms", "push"]


@dataclass(frozen=True)
class NotificationPayload:
    """Notification content to be delivered."""
    user_id: UUID
    alert_id: UUID
    channel: NotificationChannel
    title: str
    message: str
    severity: Severity


class NotificationProvider(ABC):
    """Base class for notification providers."""

    @abstractmethod
    def send(self, payload: NotificationPayload) -> tuple[bool, dict]:
        """
        Send a notification.

        Returns:
            (success: bool, provider_response: dict)
        """
        pass


class InAppNotificationProvider(NotificationProvider):
    """In-app notification provider — stores notifications in database."""

    def send(self, payload: NotificationPayload) -> tuple[bool, dict]:
        """In-app notifications are already persisted via NotificationDeliveryAttempt."""
        return True, {"method": "in_app", "persisted": True}


class SMSProviderStub(NotificationProvider):
    """SMS provider stub — does not send real SMS."""

    def send(self, payload: NotificationPayload) -> tuple[bool, dict]:
        """Stub implementation — logs but does not send."""
        return True, {
            "method": "sms",
            "stub": True,
            "warning": "SMS not sent - stub provider",
        }


class PushNotificationProviderStub(NotificationProvider):
    """Push notification provider stub — does not send real push notifications."""

    def send(self, payload: NotificationPayload) -> tuple[bool, dict]:
        """Stub implementation — logs but does not send."""
        return True, {
            "method": "push",
            "stub": True,
            "warning": "Push notification not sent - stub provider",
        }


def get_provider(channel: NotificationChannel) -> NotificationProvider:
    """Get notification provider for a channel."""
    if channel == "in_app":
        return InAppNotificationProvider()
    elif channel == "sms":
        return SMSProviderStub()
    elif channel == "push":
        return PushNotificationProviderStub()
    else:
        raise ValueError(f"Unknown channel: {channel}")


def should_notify_user(
    session: Session,
    user_id: UUID,
    channel: NotificationChannel,
    severity: Severity,
) -> bool:
    """
    Check if user should be notified on this channel for this severity level.

    Returns True if:
    - User has a preference for this channel and it's enabled
    - Alert severity meets or exceeds user's minimum severity

    Returns False otherwise.
    """
    preference = session.execute(
        select(NotificationPreference)
        .where(
            and_(
                NotificationPreference.user_id == user_id,
                NotificationPreference.channel == channel,
            )
        )
    ).scalar_one_or_none()

    # If no preference, use default (in_app enabled, others disabled)
    if preference is None:
        if channel != "in_app":
            return False
        # For in_app, default to enabled with low minimum
        return True

    if not preference.enabled:
        return False

    # Check severity threshold
    severity_order = {
        Severity.low: 1,
        Severity.moderate: 2,
        Severity.high: 3,
        Severity.critical: 4,
    }

    return severity_order[severity] >= severity_order[preference.minimum_severity]


def deliver_alert_to_user(
    session: Session,
    alert: Alert,
    user_id: UUID,
    channels: list[NotificationChannel] | None = None,
) -> list[NotificationDeliveryAttempt]:
    """
    Deliver an alert to a user via configured notification channels.

    Args:
        session: Database session
        alert: Alert to deliver
        user_id: User to notify
        channels: Optional list of channels to use (defaults to all enabled)

    Returns:
        List of NotificationDeliveryAttempt records
    """
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        return []

    # Phase 8 creates in-app deliveries only.  SMS/push providers remain
    # explicitly callable stubs for integration testing, but are never used by
    # the operational path and therefore cannot send a real message.
    if channels is None:
        channels = ["in_app"]

    attempts = []
    for channel in channels:
        # Check if user wants notifications on this channel
        if not should_notify_user(session, user_id, channel, alert.severity):
            continue

        existing = session.execute(
            select(NotificationDeliveryAttempt.id).where(
                NotificationDeliveryAttempt.alert_id == alert.id,
                NotificationDeliveryAttempt.user_id == user_id,
                NotificationDeliveryAttempt.channel == channel,
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        # Prepare payload
        payload = NotificationPayload(
            user_id=user_id,
            alert_id=alert.id,
            channel=channel,
            title=alert.title,
            message=alert.message,
            severity=alert.severity,
        )

        # Send via provider
        provider = get_provider(channel)
        success, provider_response = provider.send(payload)

        # Record attempt
        attempt = NotificationDeliveryAttempt(
            alert_id=alert.id,
            user_id=user_id,
            channel=channel,
            status="delivered" if success else "failed",
            attempted_at=datetime.now(timezone.utc),
            provider_response=provider_response,
        )

        session.add(attempt)
        attempts.append(attempt)

    return attempts


def deliver_alert_to_all_recipients(
    session: Session,
    alert: Alert,
) -> list[NotificationDeliveryAttempt]:
    """
    Deliver an alert to all users who should receive it.

    Determines recipients based on:
    - Location owner
    - Users with explicit location access grants

    Args:
        session: Database session
        alert: Alert to deliver

    Returns:
        List of NotificationDeliveryAttempt records
    """
    recipient = session.get(AlertRecipient, alert.id)
    if recipient is None:
        return []
    return deliver_alert_to_user(session, alert, recipient.user_id)
