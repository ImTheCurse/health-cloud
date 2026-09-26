"""Managing the project's webhook subscriber registration.

A subscriber is the endpoint Google delivers notifications to. Creating or
updating one triggers a verification handshake against that endpoint, so these
calls only succeed once the receiver is live and publicly reachable.
"""

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from server.webhooks.const import (
    API_ROOT,
    AUTOMATIC,
    CLOUD_PLATFORM_SCOPE,
    DATA_TYPES,
    HTTP_TIMEOUT_SECONDS,
    STATE_ACTIVE,
    SUBSCRIBER_ID_PATTERN,
)
from server.webhooks.error import SubscriberError
from server.webhooks.util import authorization_value


class SubscriberClient:
    """Calls projects.subscribers on behalf of the service account.

    The session is injected rather than built here, so tests can drive the
    client without credentials or network.
    """

    def __init__(self, project_number: str, session) -> None:
        self._parent = f"projects/{project_number}"
        self._session = session

    @classmethod
    def from_service_account_file(cls, project_number: str, key_path: str):
        credentials = service_account.Credentials.from_service_account_file(
            key_path, scopes=[CLOUD_PLATFORM_SCOPE]
        )
        return cls(project_number, AuthorizedSession(credentials))

    # -- requests ---------------------------------------------------------

    def _call(self, method: str, url: str, **kwargs) -> dict:
        response = self._session.request(
            method, url, timeout=HTTP_TIMEOUT_SECONDS, **kwargs
        )
        if not response.ok:
            raise SubscriberError(self._explain(response))
        return response.json() if response.content else {}

    @staticmethod
    def _explain(response) -> str:
        """Turn Google's error envelope into something worth reading."""
        try:
            error = response.json().get("error", {})
            message = error.get("message", response.text)
            status = error.get("status", "")
        except ValueError:
            message, status = response.text, ""

        if response.status_code == 400 and "FAILED_PRECONDITION" in status:
            return (
                f"{message}\n"
                "The endpoint failed Google's verification handshake. It must "
                "answer an authorised POST with 200/201 and an unauthorised "
                "POST with 401/403, over public HTTPS."
            )
        if response.status_code == 403:
            return (
                f"{message}\nThe service account lacks permission to manage "
                "subscribers. Grant it 'Google Health API Admin'."
            )
        return f"HTTP {response.status_code} {status}: {message}"

    # -- operations -------------------------------------------------------

    def list(self) -> list[dict]:
        payload = self._call("GET", f"{API_ROOT}/{self._parent}/subscribers")
        return payload.get("subscribers", [])

    def get(self, subscriber_id: str) -> dict | None:
        """Find one subscriber.

        The API exposes no get method, only list, so this filters by name.
        """
        suffix = f"/subscribers/{subscriber_id}"
        return next(
            (s for s in self.list() if str(s.get("name", "")).endswith(suffix)), None
        )

    def create(
        self,
        subscriber_id: str,
        endpoint_uri: str,
        secret: str,
        data_types: tuple[str, ...] = DATA_TYPES,
        policy: str = AUTOMATIC,
    ) -> dict:
        """Register the endpoint, then read back what Google stored.

        Google returns a long-running Operation but exposes no endpoint to poll
        it against, and -- despite the discovery document describing a
        ``state`` enum -- the subscriber resource comes back without one. The
        proof that verification passed is this call returning at all: a failed
        handshake fails it with FAILED_PRECONDITION rather than registering an
        unverified subscriber.
        """
        self.validate(subscriber_id, endpoint_uri)

        operation = self._call(
            "POST",
            f"{API_ROOT}/{self._parent}/subscribers",
            params={"subscriberId": subscriber_id},
            json={
                "endpointUri": endpoint_uri,
                "endpointAuthorization": {"secret": authorization_value(secret)},
                "subscriberConfigs": [
                    {
                        "dataTypes": list(data_types),
                        "subscriptionCreatePolicy": policy,
                    }
                ],
            },
        )
        if error := operation.get("error"):
            raise SubscriberError(error.get("message", str(error)))

        return self.get(subscriber_id) or {}

    def patch(self, subscriber_id: str, endpoint_uri: str) -> dict:
        """Repoint an existing subscriber, e.g. ngrok to the real server.

        The handshake runs again against the new URI.
        """
        self.validate(subscriber_id, endpoint_uri)

        operation = self._call(
            "PATCH",
            f"{API_ROOT}/{self._parent}/subscribers/{subscriber_id}",
            params={"updateMask": "endpointUri"},
            json={"endpointUri": endpoint_uri},
        )
        if error := operation.get("error"):
            raise SubscriberError(error.get("message", str(error)))

        return self.get(subscriber_id) or {}

    def delete(self, subscriber_id: str, force: bool = False) -> None:
        self._call(
            "DELETE",
            f"{API_ROOT}/{self._parent}/subscribers/{subscriber_id}",
            params={"force": "true"} if force else None,
        )

    # -- validation -------------------------------------------------------

    @staticmethod
    def validate(subscriber_id: str, endpoint_uri: str) -> None:
        """Reject locally what Google would reject remotely, but clearly.

        Public so callers can check before announcing what they are about to do.
        """
        if not SUBSCRIBER_ID_PATTERN.match(subscriber_id):
            raise SubscriberError(
                f"subscriber id {subscriber_id!r} is invalid: it must be 4-36 "
                "characters of lowercase letters, digits and hyphens, starting "
                "with a letter and ending with a letter or digit"
            )
        if not endpoint_uri.startswith("https://"):
            raise SubscriberError(
                f"endpoint {endpoint_uri!r} must use https. Google will not "
                "deliver to plain http, and localhost is not reachable from "
                "Google's servers"
            )


def describe(subscriber: dict) -> str:
    """Summary for the CLI.

    Google does not return a ``state`` field on this resource in practice, so
    a missing one is normal and must not be reported as a problem -- doing so
    made a successful registration print as a failure. The marker flags only
    what Google actually tells us is wrong: a state that is present and not
    ACTIVE, or an endpoint with no secret registered against it.
    """
    if not subscriber:
        return "no subscriber found"
    state = subscriber.get("state")
    secret_set = subscriber.get("endpointAuthorization", {}).get("secretSet", False)
    healthy = secret_set and state in (None, STATE_ACTIVE)
    types = sum(
        len(config.get("dataTypes", []))
        for config in subscriber.get("subscriberConfigs", [])
    )
    return (
        f"[{'ok' if healthy else '!!'}] {subscriber.get('name')}\n"
        f"     endpoint   {subscriber.get('endpointUri')}\n"
        f"     state      {state or 'not reported by Google'}\n"
        f"     secret     {'registered' if secret_set else 'MISSING'}\n"
        f"     dataTypes  {types}"
    )
