"""The dashboard's backfill button: who may start a run, and what its state reads as."""

import pytest
from fastapi.testclient import TestClient

from server.api.auth import current_user
from server.main import app
from server.models.user import User
from server.orchestration.client import FlowRun
from server.orchestration.error import TriggerError
from server.providers import get_backfill_trigger, get_flow_runs
from tests.google_webhook import FAKE_HEALTH_USER_ID

HEADERS = {"X-Requested-With": "health-cloud"}
RUN_ID = "0ba5023b-f35f-479c-93e0-d2cc1eccba55"


class FakeTrigger:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.parameters: list[dict] = []

    def trigger(self, parameters=None):
        if self.fail:
            raise TriggerError("could not reach Prefect")
        self.parameters.append(parameters)
        return RUN_ID


class FakeRuns:
    def __init__(self, run: FlowRun | None = None, fail: bool = False) -> None:
        self.run = run
        self.fail = fail

    def read(self, run_id):
        if self.fail:
            raise TriggerError("could not reach Prefect")
        return self.run


def a_run(state_type: str, owner: str = FAKE_HEALTH_USER_ID) -> FlowRun:
    return FlowRun(state_type=state_type, parameters={"health_user_id": owner})


@pytest.fixture
def serve():
    """A signed-in client over a fake Prefect."""

    def client_over(trigger=None, runs=None):
        user = User(health_user_id=FAKE_HEALTH_USER_ID, refresh_token_enc=b"")
        app.dependency_overrides[current_user] = lambda: user
        app.dependency_overrides[get_backfill_trigger] = lambda: trigger or FakeTrigger()
        app.dependency_overrides[get_flow_runs] = lambda: runs or FakeRuns()
        return TestClient(app)

    yield client_over
    app.dependency_overrides.clear()


def test_starting_a_backfill_needs_a_session(client):
    assert client.post("/backfill", headers=HEADERS).status_code == 401


def test_reading_a_backfill_needs_a_session(client):
    assert client.get(f"/backfill/{RUN_ID}").status_code == 401


def test_a_backfill_starts_for_the_signed_in_user_only(serve):
    trigger = FakeTrigger()

    response = serve(trigger=trigger).post("/backfill", headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {"run_id": RUN_ID}
    assert trigger.parameters == [{"health_user_id": FAKE_HEALTH_USER_ID}]


def test_a_backfill_without_the_dashboards_header_is_refused(serve):
    """A cross-site form cannot set a header, so its POST stops here."""
    trigger = FakeTrigger()

    response = serve(trigger=trigger).post("/backfill")

    assert response.status_code == 403
    assert trigger.parameters == []


def test_an_unreachable_prefect_is_a_503(serve):
    response = serve(trigger=FakeTrigger(fail=True)).post("/backfill", headers=HEADERS)

    assert response.status_code == 503


@pytest.mark.parametrize(
    ("state_type", "state"),
    [
        ("SCHEDULED", "running"),
        ("PENDING", "running"),
        ("RUNNING", "running"),
        ("COMPLETED", "completed"),
        ("FAILED", "failed"),
        ("CRASHED", "failed"),
        ("CANCELLED", "failed"),
        ("SOMETHING_NEW", "running"),
    ],
)
def test_a_runs_state_is_reported_in_three_words(serve, state_type, state):
    response = serve(runs=FakeRuns(a_run(state_type))).get(f"/backfill/{RUN_ID}")

    assert response.status_code == 200
    assert response.json() == {"state": state}


def test_another_users_run_is_not_found(serve):
    runs = FakeRuns(a_run("COMPLETED", owner="someone-else"))

    assert serve(runs=runs).get(f"/backfill/{RUN_ID}").status_code == 404


def test_a_run_prefect_does_not_know_is_not_found(serve):
    assert serve(runs=FakeRuns(None)).get(f"/backfill/{RUN_ID}").status_code == 404


def test_a_state_prefect_cannot_answer_for_is_a_503(serve):
    response = serve(runs=FakeRuns(fail=True)).get(f"/backfill/{RUN_ID}")

    assert response.status_code == 503
