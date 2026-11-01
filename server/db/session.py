"""Engine and session handling."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

# Importing the models package registers every table on SQLModel.metadata
# before create_all() runs.
import server.models  # noqa: F401
from server.config.settings import get_settings

_settings = get_settings()
_engine = create_engine(_settings.database_url, echo=_settings.sql_echo)


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


def reset_tables(models: Sequence[type[SQLModel]]) -> None:
    """Drop the tables behind ``models`` and recreate them, empty.

    How a column changes type without migrations: ``create_all()`` only creates
    tables that are missing, so a changed table must be dropped first. Tables not
    named are left alone, with their rows.
    """
    tables = [SQLModel.metadata.tables[model.__table__.name] for model in models]  # type: ignore[attr-defined]
    SQLModel.metadata.drop_all(_engine, tables=tables)
    SQLModel.metadata.create_all(_engine, tables=tables)
