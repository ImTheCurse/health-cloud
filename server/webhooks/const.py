"""Constants for the Google Health webhook integration."""

import re

API_ROOT = "https://health.googleapis.com/v4"

#: Subscriber management is authorised by a service account holding this scope
CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

#: Path this app serves the receiver on, appended to the public origin.
WEBHOOK_PATH = "/webhooks/health"

HTTP_TIMEOUT_SECONDS = 30

#: Google signs the raw JSON body with ECDSA P-256 / SHA-256 and sends the
#: base64 signature in this header.
SIGNATURE_HEADER = "GOOGLE-HEALTH-API-SIGNATURE"

#: Public keyset Google signs notifications with. Keys rotate every 30 days and
#: several are enabled at once, so verification uses the whole keyset and the
#: URL is permanent: never pin a single key.
KEYSET_URL = "https://www.gstatic.com/googlehealthapi/webhooks/webhooks_public_keyset.json"

#: How long a fetched keyset is trusted before being refreshed. Far shorter
#: than the 30-day rotation, and a failed verification forces a refresh anyway.
KEYSET_CACHE_SECONDS = 3600

#: Body Google posts during the endpoint verification handshake.
VERIFICATION_TYPE = "verification"

#: Google's own constraint on subscriberId, quoted from the API reference:
#: "4-36 characters, and valid characters are /[a-z]([a-z0-9-]{2,34}[a-z0-9])/"
SUBSCRIBER_ID_PATTERN = re.compile(r"^[a-z]([a-z0-9-]{2,34}[a-z0-9])$")

AUTOMATIC = "AUTOMATIC"
MANUAL = "MANUAL"

#: Subscriber.state values. ACTIVE means the verification handshake passed.
STATE_ACTIVE = "ACTIVE"
STATE_UNVERIFIED = "UNVERIFIED"

#: Every data type that can be subscribed to, in the kebab-case tokens the API
#: expects, plus the two system events. Capture wide, model narrow: a type not
#: subscribed to today may be unrecoverable later, since subscriptions do not
#: backfill.
DATA_TYPES = (
    "active-zone-minutes",
    "activity-level",
    "altitude",
    "blood-glucose",
    "body-fat",
    "calories-in-heart-rate-zone",
    "daily-heart-rate-variability",
    "daily-heart-rate-zones",
    "daily-oxygen-saturation",
    "daily-respiratory-rate",
    "daily-resting-heart-rate",
    "daily-sleep-temperature-derivations",
    "distance",
    "exercise",
    "floors",
    "heart-rate",
    "heart-rate-variability",
    "height",
    "hydration-log",
    "nutrition-log",
    "respiratory-rate-sleep-summary",
    "run-vo2-max",
    "sedentary-period",
    "sleep",
    "steps",
    "time-in-heart-rate-zone",
    "weight",
    "user-deleted",
    "user-revoked-access",
)


def authorization_value(secret: str) -> str:
    """The exact string Google stores and replays in the Authorization header.

    Registered at subscriber creation and compared on every notification, so
    both sides must build it the same way.
    """
    return f"Bearer {secret}"
