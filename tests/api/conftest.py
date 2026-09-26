"""Fixtures for the route tests."""

import pytest
from fastapi.testclient import TestClient

from server.db.session import get_session
from server.main import app
from server.providers import (
    get_endpoint_authorizer,
    get_publisher,
    get_signature_verifier,
)
from server.webhooks.receiver import EndpointAuthorizer
from server.webhooks.signature import SignatureVerifier
from tests.api.fakes import FakePublisher, FakeSession, Journal
from tests.google_webhook import AUTH, Keyset, make_keypair

#: The dependency FastAPI actually registered. SessionDep wraps the undecorated
#: generator, so overriding get_session itself would silently do nothing.
SESSION_DEPENDENCY = get_session.__wrapped__


@pytest.fixture
def journal():
    """One ordered record of what the route did, shared by both doubles."""
    return Journal()


@pytest.fixture
def session(journal):
    return FakeSession(journal)


@pytest.fixture
def publisher(journal):
    return FakePublisher(journal)


@pytest.fixture
def signer_and_client(session, publisher):
    """A client whose app trusts a secret and a keyset the test controls.

    The database and the broker are doubles: these tests are about what the
    route decides, not about whether Postgres and NATS work.
    """
    signer, public_json = make_keypair()
    app.dependency_overrides[get_endpoint_authorizer] = lambda: EndpointAuthorizer(AUTH)
    app.dependency_overrides[get_signature_verifier] = lambda: SignatureVerifier(
        fetch=Keyset(public_json)
    )
    app.dependency_overrides[SESSION_DEPENDENCY] = lambda: session
    app.dependency_overrides[get_publisher] = lambda: publisher
    yield signer, TestClient(app)
    app.dependency_overrides.clear()
