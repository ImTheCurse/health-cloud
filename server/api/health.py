"""Liveness and readiness endpoints."""

from fastapi import APIRouter
from sqlmodel import select

import server.db.session as db
from server.config.settings import get_settings
from server.db.session import SessionDep

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness: the process is up. Deliberately touches nothing."""
    return {"status": "ok", "environment": get_settings().environment}


@router.get("/readyz")
def readyz(session: SessionDep) -> dict[str, str]:
    """Readiness: the database is reachable."""
    with db.get_session() as sess:
        statment = select(1)
        sess.exec(statment)
    return {"status": "ready"}
