"""Liveness and readiness endpoints."""

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse

from server.api.util import database_reachable, readiness_labels
from server.config.settings import get_settings
from server.db.session import SessionDep
from server.observability.const import LogPolicy
from server.observability.policy import log_policy
from server.providers import get_publisher
from server.queue.publisher import NotificationPublisher

Publisher = Depends(get_publisher)

router = APIRouter(tags=["health"])


@router.get("/healthz")
@log_policy(LogPolicy.QUIET)
def healthz() -> dict[str, str]:
    """Liveness: the process is up. Deliberately touches nothing."""
    return {"status": "ok", "environment": get_settings().environment}


@router.get("/readyz")
@log_policy(LogPolicy.QUIET)
def readyz(
    session: SessionDep, publisher: NotificationPublisher = Publisher
) -> Response:
    """Readiness: everything the receiver needs before it can accept a delivery.

    Both dependencies are load-bearing rather than informational. The receiver
    will not acknowledge a notification unless the audit row commits *and* the
    broker confirms the message, so a service that cannot reach either is not
    ready to be sent traffic -- and saying so here is far better than finding
    out on Google's first real delivery.

    Both are injected rather than reached for, so a test can describe a broken
    dependency instead of having to break one.
    """
    checks = {
        "database": database_reachable(session),
        "queue": publisher.connected(),
    }
    ready = all(checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK
        if ready
        else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if ready else "not ready",
            **readiness_labels(checks),
        },
    )
