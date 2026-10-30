"""Errors raised by the webhook integration."""


class WebhookError(RuntimeError):
    """Base for anything that goes wrong talking to, or for, Google's webhooks."""


class SubscriberError(WebhookError):
    """Google refused a subscriber operation, or the request was malformed."""


class SignatureError(WebhookError):
    """A notification's signature did not verify against Google's keyset."""


class NotificationError(WebhookError):
    """A notification verified as Google's, but its body was not readable.

    Distinct from SignatureError on purpose: this means our parser and
    Google's payload disagree, which is a bug on our side rather than a
    rejected caller.
    """
