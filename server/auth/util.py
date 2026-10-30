"""Helpers for reasoning about a user's consent window."""

import datetime as dt

from server.auth.const import REFRESH_TOKEN_LIFETIME
from server.models.user import User


def days_until_reconsent(user: User) -> float:
    """Days left before the refresh token dies and re-consent is required."""
    expires_at = user.refreshed_at + REFRESH_TOKEN_LIFETIME
    return (expires_at - dt.datetime.now(dt.UTC)).total_seconds() / 86400
