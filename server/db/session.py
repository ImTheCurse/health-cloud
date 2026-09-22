"""Engine and session handling."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

# Importing the models package registers every table on SQLModel.metadata
# before create_all() runs.
import server.models  # noqa: F401
from server.config.settings import get_settings

_engine = create_engine(get_settings().database_url, echo=True)


@contextmanager
def get_session() -> Iterator[Session]:
    """Create a short-lived SQLModel session.

    Yields:
        A session bound to the module-level ``engine``.

    Example:
        >>> with get_session() as session:
        ...     session is not None
        True
    """

    with Session(_engine) as session:
        yield session


# Depends() must receive the undecorated generator. FastAPI detects yielding
# dependencies with inspect.isgeneratorfunction(), which is False for a
# @contextmanager: depending on get_session directly injects the
# _GeneratorContextManager object instead of a Session, then fails on teardown
# with "'_GeneratorContextManager' object has no attribute 'throw'".
# @contextmanager uses functools.wraps, so __wrapped__ is that generator.
SessionDep = Annotated[Session, Depends(get_session.__wrapped__)]


def create_all() -> None:
    SQLModel.metadata.create_all(_engine)
