"""A fake transport for SubscriberClient.

The client takes its HTTP session in the constructor precisely so the tests
can drive it without touching Google.
"""

import json

from server.webhooks.const import DATA_TYPES, WEBHOOK_PATH

PROJECT = "123456789"
VALID_ID = "health-cloud-local"
VALID_ENDPOINT = f"https://example.ngrok.app{WEBHOOK_PATH}"


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = {} if payload is None else payload
        self.text = json.dumps(self._payload)
        self.content = self.text.encode()
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class FakeSession:
    """Records calls and replays queued responses in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0) if self.responses else FakeResponse()


def subscriber_payload(state="ACTIVE"):
    return {
        "name": f"projects/{PROJECT}/subscribers/{VALID_ID}",
        "endpointUri": VALID_ENDPOINT,
        "state": state,
        "subscriberConfigs": [{"dataTypes": list(DATA_TYPES)}],
    }


def created_subscriber(state="ACTIVE"):
    """The two responses a successful create makes: the operation, then a list.

    There is no `get` on this API, so the client confirms the result by
    listing.
    """
    return (
        FakeResponse(payload={"done": True}),
        FakeResponse(payload={"subscribers": [subscriber_payload(state)]}),
    )
