"""Real Postgres and real NATS.

Everything the receiver's durability rests on is a property of infrastructure:
that a row survives a commit, that a message survives being published, that the
stream is file-backed. None of that can be shown with a double -- a fake cannot
roll back a transaction it is not in, and cannot persist anything.

These tests run against a throwaway database created and dropped per session,
and a stream named for the test run, They skip rather than fail when the infrastructure is absent;
CI runs both, so the guarantees are always checked somewhere.
"""

import os
import socket
from urllib.parse import urlsplit

import psycopg
import pytest
from sqlmodel import Session, SQLModel, create_engine

import server.models  # noqa: F401  -- registers the tables on the metadata
from server.config.settings import get_settings
from server.queue.publisher import NotificationPublisher

# Suffixed with the process id so two test runs cannot collide. The app's own
# database and stream are never touched -- it writes to `healthcloud` and
# publishes to `health.notifications.*`, so a real notification arriving mid-test
# cannot reach these -- but without the suffix, one `pytest` run would drop the
# database and stream out from under another running at the same time.
_RUN = os.getpid()
TEST_DATABASE = f"health_cloud_integration_{_RUN}"
TEST_STREAM = f"health_integration_{_RUN}"
TEST_SUBJECT_PREFIX = f"health.integration.{_RUN}"


def _admin_dsn(url: str) -> str:
    return (
        url.replace("postgresql+psycopg://", "postgresql://").rsplit("/", 1)[0]
        + "/postgres"
    )


def _reachable(url: str) -> bool:
    parts = urlsplit(url)
    try:
        with socket.create_connection((parts.hostname, parts.port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def engine():
    """A throwaway database with our schema, dropped when the session ends."""
    url = get_settings().database_url
    if not _reachable(url.replace("postgresql+psycopg", "postgresql")):
        pytest.skip("Postgres is not reachable")

    admin = _admin_dsn(url)
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(f"DROP DATABASE IF EXISTS {TEST_DATABASE}")
        connection.execute(f"CREATE DATABASE {TEST_DATABASE}")

    test_url = url.rsplit("/", 1)[0] + f"/{TEST_DATABASE}"
    test_engine = create_engine(test_url)
    SQLModel.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()

    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(f"DROP DATABASE IF EXISTS {TEST_DATABASE}")


@pytest.fixture
def session(engine):
    """A session whose writes are undone when the test ends.

    The session joins a transaction opened here and commits into a savepoint, so
    a test can call commit() and see committed behaviour while the outer
    rollback still leaves the database empty for the next one. Truncating
    between tests would work too, but this way nothing a test writes is ever
    durable, even if the test crashes.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
async def publisher():
    """A started publisher on a stream of its own, removed afterwards.

    Async, like the client and like the app's lifespan -- the tests await the
    same calls the running server does, with no bridging in between.
    """
    url = get_settings().nats_url
    if not _reachable(url):
        pytest.skip("NATS is not reachable")

    published = NotificationPublisher(
        url,
        stream=TEST_STREAM,
        subject_prefix=TEST_SUBJECT_PREFIX,
        # The tests read messages back, which a work-queue stream only permits
        # with direct access -- the same reason it is enabled locally.
        allow_direct=True,
    )
    await published.start()
    yield published
    try:
        await published._js.delete_stream(TEST_STREAM)
    except Exception:
        pass  # a test that never created it is not a failure
    await published.stop()
