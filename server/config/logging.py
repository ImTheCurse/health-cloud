"""Logging configuration.

Human-readable and colourised while developing, structured JSON everywhere
else. The fields are identical either way -- only the rendering changes -- so
a line you read in the terminal is the same line a log aggregator would parse.
"""

import sys

from loguru import logger

from server.config.const import LOCAL_ENV
from server.config.settings import get_settings
from server.config.util import human_format


def configure_logging() -> None:
    """Install the single sink this process logs through.

    Replaces loguru's default sink rather than adding to it, so calling this
    twice does not double every line.
    """
    settings = get_settings()
    level = settings.log_level.upper()
    logger.remove()

    if settings.environment == LOCAL_ENV:
        logger.add(sys.stderr, level=level, format=human_format, colorize=True)
        return

    # serialize=True emits one JSON object per line, carrying everything bound
    # with logger.bind(). diagnose=False is deliberate and not negotiable: the
    # diagnostic traceback inlines local variable values, which on this code
    # path would mean notification bodies and decrypted tokens in the log.
    logger.add(sys.stderr, level=level, serialize=True, diagnose=False)
