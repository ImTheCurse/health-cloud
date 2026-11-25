"""Errors raised by the flows."""


class BackfillFailed(Exception):
    """One or more types could not be fetched; the rest were."""
