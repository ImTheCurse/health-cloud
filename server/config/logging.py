"""Logging configuration.

Uvicorn configures its own loggers but leaves the root logger without a
handler, so anything logged under ``server.*`` is dropped unless we install
one. LOG_LEVEL has been a required setting since step 1; this is what finally
reads it.
"""

import logging

from server.config.settings import get_settings

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"


def configure_logging() -> None:
    """Attach a handler to the root logger at the configured level.

    ``force=True`` replaces any handler uvicorn's --log-config may have put
    there, so the level in .env is the one that actually applies.
    """
    logging.basicConfig(
        level=get_settings().log_level.upper(), format=LOG_FORMAT, force=True
    )
