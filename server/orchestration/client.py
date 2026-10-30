"""Starting a fetcher flow run.

Prefect's REST API over ``requests``, rather than ``run_deployment`` from the
``prefect`` package. This is one endpoint, so a small
client is a better trade than that dependency -- and it fakes cleanly in tests,
the same way ``SubscriberClient`` does.

The trigger carries **no payload**. The flow's input is the durable consumer, not
this call. Passing the pointers here would mean either the queue is never drained
or every pointer is processed twice, and it would put the work back in a
fire-and-forget HTTP call
"""

from typing import Any

import requests
from loguru import logger

from server.orchestration.const import CREATE_RUN_PATH, TRIGGER_TIMEOUT_SECONDS
from server.orchestration.error import TriggerError


class FlowTrigger:
    """Rings the doorbell: asks Prefect to start a run of the fetcher deployment."""

    def __init__(
        self,
        api_url: str,
        deployment_id: str,
        session: requests.Session | None = None,
        timeout: float = TRIGGER_TIMEOUT_SECONDS,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._deployment_id = deployment_id
        self._session = session or requests.Session()
        self._timeout = timeout

    def trigger(self) -> str | None:
        """Start a run, returning its id if Prefect gave one.

        Raises:
            TriggerError: the run was not started. The caller logs it and carries
                on -- see the error's docstring for why that is safe.
        """
        url = self._api_url + CREATE_RUN_PATH.format(deployment_id=self._deployment_id)
        try:
            response = self._session.post(url, json={}, timeout=self._timeout)
        except requests.RequestException as error:
            raise TriggerError(f"could not reach Prefect: {error}") from error

        if response.status_code >= 400:
            raise TriggerError(f"Prefect answered {response.status_code}")

        return _run_id(response)


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
