"""Google OAuth endpoints, scopes, and cookie names."""

import datetime as dt

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
IDENTITY_URI = "https://health.googleapis.com/v4/users/me/identity"

_HEALTH_SCOPE_NAMES = (
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

HEALTH_SCOPES = tuple(
    f"https://www.googleapis.com/auth/googlehealth.{name}.readonly"
    for name in _HEALTH_SCOPE_NAMES
)

#: Non-restricted, and on the same consent screen. They are what give the
#: session an email and display name; the health scopes carry no identity.
IDENTITY_SCOPES = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "profile",
)

SCOPES = list(HEALTH_SCOPES + IDENTITY_SCOPES)

SESSION_COOKIE = "health_cloud_session"
OAUTH_STATE_COOKIE = "health_cloud_oauth_state"

TOKEN_ISSUER = "health-cloud"
SESSION_AUDIENCE = "session"
STATE_AUDIENCE = "oauth-state"

#: Custom claim carrying the PKCE code verifier across the redirect.
CODE_VERIFIER_CLAIM = "cv"

#: One in-flight consent redirect. Long enough to read a consent screen.
STATE_TTL = dt.timedelta(minutes=10)

#: Testing-mode refresh tokens expire 7 days after issue. The app stays in
#: testing mode deliberately -- restricted scopes need a paid CASA assessment
#: -- so this countdown is permanent, not a development quirk.
REFRESH_TOKEN_LIFETIME = dt.timedelta(days=7)

HTTP_TIMEOUT_SECONDS = 30
