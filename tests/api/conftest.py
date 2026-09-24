"""Fixtures for the route tests."""

import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.providers import get_endpoint_authorizer, get_signature_verifier
from server.webhooks.receiver import EndpointAuthorizer
from server.webhooks.signature import SignatureVerifier
from tests.google_webhook import AUTH, Keyset, make_keypair


@pytest.fixture
def signer_and_client():
    """A client whose app trusts a secret and a keyset the test controls."""
    signer, public_json = make_keypair()
    app.dependency_overrides[get_endpoint_authorizer] = lambda: EndpointAuthorizer(AUTH)
    app.dependency_overrides[get_signature_verifier] = lambda: SignatureVerifier(
        fetch=Keyset(public_json)
    )
    yield signer, TestClient(app)
    app.dependency_overrides.clear()
