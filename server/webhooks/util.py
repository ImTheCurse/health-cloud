"""Helpers for the Google Health webhook integration."""


def authorization_value(secret: str) -> str:
    """The exact string Google stores and replays in the Authorization header.

    Registered at subscriber creation and compared on every notification, so
    both sides must build it the same way.
    """
    return f"Bearer {secret}"
