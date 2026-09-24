"""The requests SubscriberClient puts on the wire.

Google's subscriber API is write-then-confirm: there is no `get`, so every
mutation is followed by a `list`.
"""

from server.webhooks.const import DATA_TYPES, WEBHOOK_PATH, authorization_value
from server.webhooks.subscriber import SubscriberClient
from tests.webhooks.fakes import (
    PROJECT,
    VALID_ENDPOINT,
    VALID_ID,
    FakeResponse,
    FakeSession,
    created_subscriber,
    subscriber_payload,
)


def test_list_returns_subscribers():
    session = FakeSession(FakeResponse(payload={"subscribers": [subscriber_payload()]}))

    result = SubscriberClient(PROJECT, session).list()

    assert len(result) == 1
    assert session.calls[0]["method"] == "GET"


def test_list_is_empty_when_none_registered():
    assert SubscriberClient(PROJECT, FakeSession(FakeResponse(payload={}))).list() == []


def test_create_sends_the_expected_payload():
    session = FakeSession(*created_subscriber())

    SubscriberClient(PROJECT, session).create(VALID_ID, VALID_ENDPOINT, "s3cret")

    created = session.calls[0]
    assert created["method"] == "POST"
    assert created["params"] == {"subscriberId": VALID_ID}
    body = created["json"]
    assert body["endpointUri"] == VALID_ENDPOINT
    assert body["subscriberConfigs"][0]["subscriptionCreatePolicy"] == "AUTOMATIC"
    assert len(body["subscriberConfigs"][0]["dataTypes"]) == len(DATA_TYPES)


def test_create_registers_the_secret_with_its_bearer_scheme():
    """The receiver compares against this exact string, so both must agree."""
    session = FakeSession(*created_subscriber())

    SubscriberClient(PROJECT, session).create(VALID_ID, VALID_ENDPOINT, "s3cret")

    secret = session.calls[0]["json"]["endpointAuthorization"]["secret"]
    assert secret == authorization_value("s3cret") == "Bearer s3cret"


def test_create_reports_the_verified_state():
    session = FakeSession(*created_subscriber("ACTIVE"))

    result = SubscriberClient(PROJECT, session).create(VALID_ID, VALID_ENDPOINT, "s")

    assert result["state"] == "ACTIVE"


def test_patch_repoints_with_an_update_mask():
    new_endpoint = f"https://health.example.com{WEBHOOK_PATH}"
    session = FakeSession(*created_subscriber())

    SubscriberClient(PROJECT, session).patch(VALID_ID, new_endpoint)

    assert session.calls[0]["method"] == "PATCH"
    assert session.calls[0]["params"] == {"updateMask": "endpointUri"}
    assert session.calls[0]["json"] == {"endpointUri": new_endpoint}


def test_delete_passes_force_only_when_asked():
    session = FakeSession(FakeResponse(payload={}))
    SubscriberClient(PROJECT, session).delete(VALID_ID)
    assert session.calls[0]["params"] is None

    session = FakeSession(FakeResponse(payload={}))
    SubscriberClient(PROJECT, session).delete(VALID_ID, force=True)
    assert session.calls[0]["params"] == {"force": "true"}
