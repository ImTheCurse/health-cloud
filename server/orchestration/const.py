"""Constants for triggering flow runs."""

import datetime as dt
from typing import Final

#: Short on purpose. The trigger runs after the response has already been sent,
#: so a slow Prefect cannot delay Google's acknowledgement -- but it can still
#: occupy a worker thread, and there is nothing to wait around for: the queue,
#: not this call, is what guarantees the work happens.
TRIGGER_TIMEOUT_SECONDS: Final = 5.0

#: Prefect's REST path for starting a run of a deployment.
CREATE_RUN_PATH: Final = "/deployments/{deployment_id}/create_flow_run"

#: The fetcher deployment's name, as ``server.flows.fetch:deploy`` serves it.
FETCHER_DEPLOYMENT_NAME: Final = "fetcher"

#: The same deployment as ``flow/deployment``, the form Prefect looks it up by.
#: The receiver finds it by name, so a fresh Prefect needs no setting.
FETCHER_DEPLOYMENT: Final = f"fetch-notifications/{FETCHER_DEPLOYMENT_NAME}"

#: The rollup deployment's name, as the fetcher flow's process serves it.
ROLLUP_DEPLOYMENT_NAME: Final = "rollup"

#: The same deployment as ``flow/deployment``, the form Prefect looks it up by.
ROLLUP_DEPLOYMENT: Final = f"rollup-heart-rate/{ROLLUP_DEPLOYMENT_NAME}"

#: Prefect's REST path for reading a deployment by its flow and deployment name.
DEPLOYMENT_BY_NAME_PATH: Final = "/deployments/name/{name}"

#: The scheduled backfill's deployment name, served by the fetcher flow's process.
BACKFILL_DEPLOYMENT_NAME: Final = "recent"

#: Every hour, on the hour, in Prefect's cron notation. Prefect's scheduler
#: creates the runs, so nothing on the host needs a timer.
BACKFILL_SCHEDULE: Final = "0 * * * *"

#: How far back each scheduled backfill reaches. Google lists a workout only
#: once it is finished and sends no notification for the finished session, and
#: a phone can upload hours late, so the window is a day rather than the hour
#: between runs: anything listed within a day is fetched by roughly 23 runs.
BACKFILL_WINDOW: Final = dt.timedelta(days=1)

#: Prefect's REST path for reading one flow run.
FLOW_RUN_PATH: Final = "/flow_runs/{run_id}"

#: The scheduled backfill deployment as ``flow/deployment``. The dashboard's
#: backfill button finds it by name, like the receiver finds the fetcher.
BACKFILL_DEPLOYMENT: Final = f"backfill-recent/{BACKFILL_DEPLOYMENT_NAME}"
