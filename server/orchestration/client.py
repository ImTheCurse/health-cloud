"""Starting and reading flow runs: the fetcher's doorbell, the backfill's
rollup, and the dashboard's backfill button.

Prefect's REST API over ``requests``, rather than ``run_deployment`` from the
``prefect`` package. This is one endpoint, so a small
client is a better trade than that dependency -- and it fakes cleanly in tests,
the same way ``SubscriberClient`` does.

The trigger carries **no payload**. The flow's input is the durable consumer, not
this call. Passing the pointers here would mean either the queue is never drained
or every pointer is processed twice, and it would put the work back in a
fire-and-forget HTTP call.

The rollup run the backfill starts is the exception, and carries the span of
hours to rebuild: that span is the whole of its input.
"""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

import requests
from loguru import logger

from server.orchestration.const import (
    CREATE_RUN_PATH,
    DEPLOYMENT_BY_NAME_PATH,
    FLOW_RUN_PATH,
    TRIGGER_TIMEOUT_SECONDS,
)
from server.orchestration.error import TriggerError


class FlowTrigger:
    """Asks Prefect to start a run of one deployment.

    Built from a deployment id, or from a deployment name that is resolved on
    the first trigger and resolved again whenever Prefect no longer knows the
    id. A name survives the deployment being re-registered; an id does not.
    """

    def __init__(
        self,
        api_url: str,
        deployment_id: str | None = None,
        session: requests.Session | None = None,
        timeout: float = TRIGGER_TIMEOUT_SECONDS,
        *,
        deployment_name: str | None = None,
    ) -> None:
        if (deployment_id is None) == (deployment_name is None):
            raise ValueError("give exactly one of deployment_id and deployment_name")
        self._api_url = api_url.rstrip("/")
        self._deployment_id = deployment_id
        self._deployment_name = deployment_name
        self._session = session or requests.Session()
        self._timeout = timeout

    @classmethod
    def by_name(
        cls,
        api_url: str,
        name: str,
        session: requests.Session | None = None,
        timeout: float = TRIGGER_TIMEOUT_SECONDS,
    ) -> "FlowTrigger":
        """A trigger for the deployment called ``name``, looked up now.

        ``name`` is ``flow/deployment``. Use it where a missing deployment
        should fail at once rather than at the first trigger.

        Raises:
            TriggerError: Prefect could not be reached, or has no such deployment.
        """
        trigger = cls(api_url, session=session, timeout=timeout, deployment_name=name)
        trigger._resolve()
        return trigger

    def trigger(self, parameters: dict[str, Any] | None = None) -> str | None:
        """Start a run, returning its id if Prefect gave one.

        Raises:
            TriggerError: the run was not started. The doorbell's caller logs it
                and carries on -- see the error's docstring for why that is safe.
        """
        deployment_id = self._deployment_id or self._resolve()
        url = self._api_url + CREATE_RUN_PATH.format(deployment_id=deployment_id)
        body = {} if parameters is None else {"parameters": parameters}
        try:
            response = self._session.post(url, json=body, timeout=self._timeout)
        except requests.RequestException as error:
            raise TriggerError(f"could not reach Prefect: {error}") from error

        if response.status_code == HTTPStatus.NOT_FOUND and self._deployment_name:
            # Forget the id, so the next trigger looks the name up again.
            self._deployment_id = None
        if response.status_code >= 400:
            raise TriggerError(f"Prefect answered {response.status_code}")

        return _run_id(response)

    def _resolve(self) -> str:
        """Look the deployment's id up by name and remember it."""
        name = self._deployment_name
        if name is None:
            raise TriggerError("this trigger was given an id, not a name to look up")
        url = self._api_url + DEPLOYMENT_BY_NAME_PATH.format(name=name)
        try:
            response = self._session.get(url, timeout=self._timeout)
        except requests.RequestException as error:
            raise TriggerError(f"could not reach Prefect: {error}") from error
        if response.status_code >= 400:
            raise TriggerError(f"Prefect answered {response.status_code} for {name}")
        deployment_id = _run_id(response)
        if deployment_id is None:
            raise TriggerError(f"Prefect named no id for {name}")
        self._deployment_id = deployment_id
        return deployment_id


def _run_id(response: requests.Response) -> str | None:
    """The new run's id, if the answer carried one.

    Absence is not a failure: Prefect accepted the request, which is all the
    trigger needs. The id is only useful for correlating a log line with a run in
    Prefect's UI.
    """
    try:
        body: Any = response.json()
    except ValueError:
        logger.debug("Prefect accepted the trigger but answered with no JSON")
        return None
    if isinstance(body, dict) and isinstance(body.get("id"), str):
        return body["id"]
    return None


@dataclass(frozen=True)
class FlowRun:
    """What the dashboard needs to know about one run."""

    #: Prefect's state type: ``SCHEDULED``, ``PENDING``, ``RUNNING``,
    #: ``COMPLETED``, ``FAILED``, ``CRASHED``, ``CANCELLED`` and so on.
    state_type: str
    parameters: dict[str, Any]


class FlowRuns:
    """Reads flow runs from Prefect's REST API."""

    def __init__(
        self,
        api_url: str,
        session: requests.Session | None = None,
        timeout: float = TRIGGER_TIMEOUT_SECONDS,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._session = session or requests.Session()
        self._timeout = timeout

    def read(self, run_id: str) -> FlowRun | None:
        """The run, or ``None`` if Prefect has no run with that id.

        Raises:
            TriggerError: Prefect could not be reached or refused the read.
        """
        url = self._api_url + FLOW_RUN_PATH.format(run_id=run_id)
        try:
            response = self._session.get(url, timeout=self._timeout)
        except requests.RequestException as error:
            raise TriggerError(f"could not reach Prefect: {error}") from error
        # Prefect answers 422 for an id that is not a UUID.
        if response.status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.UNPROCESSABLE_ENTITY):
            return None
        if response.status_code >= 400:
            raise TriggerError(f"Prefect answered {response.status_code}")
        try:
            body: Any = response.json()
        except ValueError as error:
            raise TriggerError("Prefect answered with no JSON") from error
        if not isinstance(body, dict):
            raise TriggerError("Prefect answered with something other than a run")
        state = body.get("state") or {}
        parameters = body.get("parameters") or {}
        return FlowRun(
            state_type=str(state.get("type") or body.get("state_type") or "UNKNOWN"),
            parameters=parameters if isinstance(parameters, dict) else {},
        )
