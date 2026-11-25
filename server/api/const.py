"""Constants for the API routes."""

from typing import Final

#: The value the dashboard sends as ``X-Requested-With`` on a request that
#: changes something. A cross-site form cannot set a header at all.
REQUESTED_WITH: Final = "health-cloud"

#: Prefect state types that mean a backfill run ended without its data. Every
#: other state but ``COMPLETED`` is reported as still running.
BACKFILL_FAILED: Final[frozenset[str]] = frozenset({"FAILED", "CRASHED", "CANCELLED"})
