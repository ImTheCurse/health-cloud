"""Readiness reports whether a delivery could actually be accepted.

Not decoration: the receiver refuses to acknowledge a notification unless the
database commits and the broker confirms, so a service missing either is not
ready for traffic. Saying so here is better than discovering it on Google's
first real delivery.
"""


def test_ready_when_the_database_and_the_broker_are_both_reachable(signer_and_client):
    _, client = signer_and_client

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "queue": "ok"}


def test_not_ready_when_the_broker_is_unreachable(signer_and_client, publisher):
    _, client = signer_and_client
    publisher.fail = True

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["queue"] == "unreachable"
    assert response.json()["database"] == "ok"


def test_not_ready_when_the_database_is_unreachable(signer_and_client, session):
    _, client = signer_and_client
    session.fail = True

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["database"] == "unreachable"


def test_liveness_does_not_depend_on_either(client):
    """healthz answers while everything downstream is broken, by design.

    A liveness probe that fails when a dependency fails gets the process
    restarted for someone else's outage.
    """
    response = client.get("/healthz")

    assert response.status_code == 200
