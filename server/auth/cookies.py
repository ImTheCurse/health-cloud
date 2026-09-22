"""Setting and clearing the auth cookies."""

import datetime as dt

from fastapi import Response

from server.auth.const import OAUTH_STATE_COOKIE, SESSION_COOKIE, STATE_TTL


class SessionCookies:
    """Writes the session and OAuth-state cookies.

    Both are ``httpOnly`` and ``SameSite=Lax``: the session token must be
    unreachable from JavaScript, which is the XSS exposure this design exists
    to close. ``secure`` is configurable only because plain ``http://localhost``
    needs it off in development.
    """

    def __init__(self, secure: bool, session_ttl: dt.timedelta) -> None:
        self._secure = secure
        self._session_ttl = session_ttl

    def _set(self, response: Response, name: str, value: str, ttl: dt.timedelta) -> None:
        response.set_cookie(
            key=name,
            value=value,
            max_age=int(ttl.total_seconds()),
            httponly=True,
            secure=self._secure,
            samesite="lax",
            path="/",
        )

    def set_session(self, response: Response, token: str) -> None:
        self._set(response, SESSION_COOKIE, token, self._session_ttl)

    def set_state(self, response: Response, token: str) -> None:
        self._set(response, OAUTH_STATE_COOKIE, token, STATE_TTL)

    def clear_session(self, response: Response) -> None:
        response.delete_cookie(SESSION_COOKIE, path="/")

    def clear_state(self, response: Response) -> None:
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
