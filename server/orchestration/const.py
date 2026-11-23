"""Constants for triggering flow runs."""

from typing import Final

#: Short on purpose. The trigger runs after the response has already been sent,
#: so a slow Prefect cannot delay Google's acknowledgement -- but it can still
#: occupy a worker thread, and there is nothing to wait around for: the queue,
#: not this call, is what guarantees the work happens.
TRIGGER_TIMEOUT_SECONDS: Final = 5.0

#: Prefect's REST path for starting a run of a deployment.
CREATE_RUN_PATH: Final = "/deployments/{deployment_id}/create_flow_run"

#: The rollup deployment's name, as the fetcher flow's process serves it.
ROLLUP_DEPLOYMENT_NAME: Final = "rollup"

#: The same deployment as ``flow/deployment``, the form Prefect looks it up by.
ROLLUP_DEPLOYMENT: Final = f"rollup-heart-rate/{ROLLUP_DEPLOYMENT_NAME}"

#: Prefect's REST path for reading a deployment by its flow and deployment name.
DEPLOYMENT_BY_NAME_PATH: Final = "/deployments/name/{name}"
