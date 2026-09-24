"""Errors raised by the webhook integration."""


class WebhookError(RuntimeError):
    """Base for anything that goes wrong talking to, or for, Google's webhooks."""


class SubscriberError(WebhookError):
    """Google refused a subscriber operation, or the request was malformed."""


class SignatureError(WebhookError):
    """A notification's signature did not verify against Google's keyset."""
