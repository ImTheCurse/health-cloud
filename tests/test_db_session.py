import inspect

from server.db.session import SessionDep, get_session


def test_get_session_is_a_context_manager():
    assert hasattr(get_session(), "__enter__")


def test_session_dependency_is_a_generator_function():
    """FastAPI only treats a dependency as yielding if this holds.

    A ``@contextmanager`` makes it False, so the session is never injected and
    the request fails at teardown instead. Needs no database.
    """
    dependency = SessionDep.__metadata__[0].dependency

    assert inspect.isgeneratorfunction(dependency)
