"""Helpers for the health endpoints."""

from loguru import logger
from sqlmodel import Session, select


def database_reachable(session: Session) -> bool:
    try:
        session.exec(select(1))
    except Exception as error:
        logger.warning("readiness: database unreachable: {}", error)
        return False
    return True


def readiness_labels(checks: dict[str, bool]) -> dict[str, str]:
    return {name: "ok" if passed else "unreachable" for name, passed in checks.items()}
