"""Constants for the Google Health webhook integration."""

import re
from enum import StrEnum
from typing import Final

API_ROOT: Final = "https://health.googleapis.com/v4"

#: Subscriber management is authorised by a service account holding this scope
CLOUD_PLATFORM_SCOPE: Final = "https://www.googleapis.com/auth/cloud-platform"

#: Path this app serves the receiver on, appended to the public origin.
WEBHOOK_PATH: Final = "/webhooks/health"

HTTP_TIMEOUT_SECONDS: Final = 30

#: Google signs the raw JSON body with ECDSA P-256 / SHA-256 and sends the
#: base64 signature in this header.
SIGNATURE_HEADER: Final = "GOOGLE-HEALTH-API-SIGNATURE"

#: Public keyset Google signs notifications with. Keys rotate every 30 days and
#: several are enabled at once, so verification uses the whole keyset and the
#: URL is permanent: never pin a single key.
KEYSET_URL: Final = (
    "https://www.gstatic.com/googlehealthapi/webhooks/webhooks_public_keyset.json"
)

#: How long a fetched keyset is trusted before being refreshed. Far shorter
#: than the 30-day rotation, and a failed verification forces a refresh anyway.
KEYSET_CACHE_SECONDS: Final = 3600

#: Body Google posts during the endpoint verification handshake.
VERIFICATION_TYPE: Final = "verification"

#: Google's own constraint on subscriberId, quoted from the API reference:
#: "4-36 characters, and valid characters are /[a-z]([a-z0-9-]{2,34}[a-z0-9])/"
SUBSCRIBER_ID_PATTERN: Final = re.compile(r"^[a-z]([a-z0-9-]{2,34}[a-z0-9])$")

class SubscriptionPolicy(StrEnum):
    """Who creates the per-user subscriptions.

    Google's own closed set, so an enum: the CLI derives its `choices` from it
    rather than repeating the values as string literals that can drift.
    """

    #: Google creates subscriptions on consent, with no per-user bookkeeping
    #: from us. What this project uses.
    AUTOMATIC = "AUTOMATIC"

    #: We would have to create a subscription per user per data type.
    MANUAL = "MANUAL"


class SubscriberState(StrEnum):
    """The lifecycle states the discovery document describes.

    Worth knowing: the live API returns **no** `state` field at all, so code
    reading it must treat absence as normal rather than as a fault. The values
    are enumerated here because the discovery document defines them, not because
    they have been observed.
    """

    #: The verification handshake passed.
    ACTIVE = "ACTIVE"

    #: Created, handshake not yet passed.
    UNVERIFIED = "UNVERIFIED"

    #: Disabled by Google, e.g. after repeated delivery failures.
    INACTIVE = "INACTIVE"

#: Every data type that can be subscribed to, in the kebab-case tokens the API
#: expects, plus the two system events. Capture wide, model narrow: a type not
#: subscribed to today may be unrecoverable later, since subscriptions do not
#: backfill.
DATA_TYPES: Final = (
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
    "oxygen-saturation",
    "respiratory-rate-sleep-summary",
    "run-vo2-max",
    "sedentary-period",
    "sleep",
    "steps",
    "time-in-heart-rate-zone",
    "vo2-max",
    "weight",
    "user-deleted",
    "user-revoked-access",
)

#: The entries in ``DATA_TYPES`` that are account events rather than data: there
#: is nothing to fetch for them.
SYSTEM_EVENTS: Final[frozenset[str]] = frozenset({"user-deleted", "user-revoked-access"})


