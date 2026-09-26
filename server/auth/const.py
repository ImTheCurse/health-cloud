"""Google OAuth endpoints, scopes, and cookie names."""

import datetime as dt
from typing import Final

AUTH_URI: Final = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI: Final = "https://oauth2.googleapis.com/token"
IDENTITY_URI: Final = "https://health.googleapis.com/v4/users/me/identity"

_HEALTH_SCOPE_NAMES: Final = (
    "activity_and_fitness",
    "ecg",
    "health_metrics_and_measurements",
    "irn",
    "location",
    "nutrition",
    "profile",
    "settings",
    "sleep",
)

HEALTH_SCOPES: Final = tuple(
    f"https://www.googleapis.com/auth/googlehealth.{name}.readonly"
    for name in _HEALTH_SCOPE_NAMES
)

#: Non-restricted, and on the same consent screen. They are what give the
#: session an email and display name; the health scopes carry no identity.
IDENTITY_SCOPES: Final = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "profile",
)

SCOPES: Final = list(HEALTH_SCOPES + IDENTITY_SCOPES)

SESSION_COOKIE: Final = "health_cloud_session"
OAUTH_STATE_COOKIE: Final = "health_cloud_oauth_state"

TOKEN_ISSUER: Final = "health-cloud"
SESSION_AUDIENCE: Final = "session"
STATE_AUDIENCE: Final = "oauth-state"

#: Custom claim carrying the PKCE code verifier across the redirect.
CODE_VERIFIER_CLAIM: Final = "cv"

#: One in-flight consent redirect. Long enough to read a consent screen.
STATE_TTL: Final = dt.timedelta(minutes=10)

#: Testing-mode refresh tokens expire 7 days after issue. The app stays in
#: testing mode deliberately -- restricted scopes need a paid CASA assessment
#: -- so this countdown is permanent, not a development quirk.
REFRESH_TOKEN_LIFETIME: Final = dt.timedelta(days=7)

HTTP_TIMEOUT_SECONDS: Final = 30
