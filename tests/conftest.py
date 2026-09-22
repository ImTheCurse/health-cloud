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
