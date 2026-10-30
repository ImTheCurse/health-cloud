import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client():
    """Test client used without a context manager, so lifespan never runs and
    no database is required.

    Tests needing real Postgres arrive at step 3, when the webhook receiver
    starts writing rows.
    """
    return TestClient(app)


@pytest.fixture
def logs():
    """Capture loguru records structurally, for assertions on fields.

    Yields the list of records themselves rather than rendered text, so a test
    can look at every value the log would carry -- which is what makes "the
    payload never appears anywhere in a log line" checkable at all.
    """
    from loguru import logger

    captured = []
    sink_id = logger.add(captured.append, level="DEBUG")
    try:
        yield captured
    finally:
        logger.remove(sink_id)


def logged_text(records) -> str:
    """Everything a set of captured records could possibly reveal."""
    return "\n".join(f"{r.record['message']} {r.record['extra']}" for r in records)
