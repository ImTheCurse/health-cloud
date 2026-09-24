"""The webhook receiver.

Deliberately the dumbest thing in the codebase: verify, acknowledge, hand off.
Google retries anything that is not a 204 for up to 7 days, so the endpoint
must answer immediately and do the real work elsewhere.

The two handshake responses are not optional. On subscriber creation Google
posts twice -- once with the Authorization header, once without -- and demands
200/201 then 401/403. Failing either makes subscriber creation fail with
FAILED_PRECONDITION, so the authorization check comes before anything else,
including parsing the body.
"""

from fastapi import APIRouter, Depends, Header, Request, Response, status

from server.providers import get_endpoint_authorizer, get_signature_verifier
from server.webhooks.const import WEBHOOK_PATH
from server.webhooks.error import SignatureError
from server.webhooks.receiver import (
    EndpointAuthorizer,
    is_verification_request,
    parse_notification,
)
from server.webhooks.signature import SignatureVerifier

router = APIRouter(tags=["webhooks"])


async def raw_body(request: Request) -> bytes:
    """The exact bytes Google signed.

    An async dependency so the route handler itself can stay synchronous, in
    keeping with the rest of the backend. Signatures are computed over these
    bytes, so nothing may re-serialise the JSON before verification.
    """
    return await request.body()


Body = Depends(raw_body)
Authorizer = Depends(get_endpoint_authorizer)
Verifier = Depends(get_signature_verifier)


@router.post(WEBHOOK_PATH)
def receive(
    body: bytes = Body,
    authorizer: EndpointAuthorizer = Authorizer,
    verifier: SignatureVerifier = Verifier,
    authorization: str | None = Header(default=None),
    google_health_api_signature: str | None = Header(default=None),
) -> Response:
    if not authorizer.authorized(authorization):
        # Also the correct answer to the handshake's unauthorized challenge.
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    if is_verification_request(body):
        return Response(status_code=status.HTTP_200_OK)

    try:
        verifier.verify(google_health_api_signature, body)
        parse_notification(body)
    except SignatureError:
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    # TODO(step 3): persist to raw_notifications and enqueue for the fetcher.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
