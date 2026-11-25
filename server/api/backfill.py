"""The dashboard's backfill button.

``POST /backfill`` starts a ``backfill-recent`` run of the last day for the
signed-in user, and ``GET /backfill/{run_id}`` reports how it is going, so the
dashboard can refresh its charts once the data is in. The run is the same one
the hourly schedule starts; a click while another run is going is queued behind
it by the deployment's concurrency limit.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from loguru import logger

from server.api.auth import current_user
from server.api.const import BACKFILL_FAILED, REQUESTED_WITH
from server.models.user import User
from server.observability.util import hashed_log_id
from server.orchestration.client import FlowRuns, FlowTrigger
from server.orchestration.error import TriggerError
from server.providers import get_backfill_trigger, get_flow_runs

router = APIRouter(prefix="/backfill", tags=["backfill"])

CurrentUser = Annotated[User, Depends(current_user)]


def require_requested_with(
    x_requested_with: Annotated[str | None, Header()] = None,
) -> None:
    """Refuse a request without the dashboard's own header.

    The session cookie is ``SameSite=Lax``, which already keeps it off another
    site's POST. The header is a second layer: a cross-site form cannot set it,
    and a cross-site ``fetch`` that does must pass a CORS preflight first.
    """
    if x_requested_with != REQUESTED_WITH:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="missing X-Requested-With"
        )


@router.post("", dependencies=[Depends(require_requested_with)])
def start_backfill(
    user: CurrentUser,
    trigger: Annotated[FlowTrigger, Depends(get_backfill_trigger)],
) -> dict[str, str]:
    """Start a backfill of the last day for the signed-in user."""
    unavailable = HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="the backfill could not be started",
    )
    try:
        run_id = trigger.trigger({"health_user_id": user.health_user_id})
    except TriggerError as error:
        logger.warning("backfill not started: {}", error)
        raise unavailable from error
    if run_id is None:
        raise unavailable
    logger.info(
        "backfill run {} started for user {}", run_id, hashed_log_id(user.health_user_id)
    )
    return {"run_id": run_id}


@router.get("/{run_id}")
def backfill_state(
    run_id: str,
    user: CurrentUser,
    runs: Annotated[FlowRuns, Depends(get_flow_runs)],
) -> dict[str, str]:
    """How a backfill run is going: ``running``, ``completed`` or ``failed``.

    Answers 404 for a run that is not the signed-in user's backfill, so a run id
    reveals nothing about anyone else's runs.
    """
    try:
        run = runs.read(run_id)
    except TriggerError as error:
        logger.warning("backfill run {} not read: {}", run_id, error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="the backfill's state could not be read",
        ) from error
    if run is None or run.parameters.get("health_user_id") != user.health_user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such run")

    if run.state_type == "COMPLETED":
        return {"state": "completed"}
    if run.state_type in BACKFILL_FAILED:
        return {"state": "failed"}
    # Scheduled, pending, running, or a state this code does not know: the
    # dashboard keeps asking rather than giving up on a run that may finish.
    return {"state": "running"}
