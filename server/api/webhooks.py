"""The webhook receiver.

Deliberately the dumbest thing in the codebase: verify, record, publish,
acknowledge. Google retries anything that is not a 204 for up to 7 days, so the
endpoint must answer immediately and do the real work elsewhere.

Durability rests on the *order* of those steps, not on a transaction. No broker
can join a Postgres transaction, so instead: the audit row commits, then every
message is confirmed persisted by the broker, and only then is Google told the
delivery was accepted. Any failure answers 503 and Google redelivers. The worst
outcome is therefore a duplicate audit row, never a lost notification.

The audit row commits first on purpose. The reverse order could leave work
queued with no record of what asked for it.

The two handshake responses are not optional. On subscriber creation Google
posts twice -- once with the Authorization header, once without -- and demands
200/201 then 401/403. Failing either makes subscriber creation fail with
FAILED_PRECONDITION, so the authorization check comes before anything else,
including parsing the body.
"""

import datetime as dt

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from loguru import logger
from sqlmodel import Session

from server.db.session import SessionDep
from server.models.notification import RawNotification
from server.observability import context as log
from server.providers import (
    get_endpoint_authorizer,
    get_publisher,
    get_signature_verifier,
)
from server.queue.error import QueueError
from server.queue.publisher import NotificationPublisher
from server.webhooks.const import WEBHOOK_PATH
from server.webhooks.error import NotificationError, SignatureError
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
Publisher = Depends(get_publisher)


@router.post(WEBHOOK_PATH)
async def receive(
    request: Request,
    session: SessionDep,
    body: bytes = Body,
    authorizer: EndpointAuthorizer = Authorizer,
    verifier: SignatureVerifier = Verifier,
    publisher: NotificationPublisher = Publisher,
    authorization: str | None = Header(default=None),
    google_health_api_signature: str | None = Header(default=None),
) -> Response:
    # Validate against our provided secret to google.
    if not authorizer.authorized(authorization):
        # Also the correct answer to the handshake's unauthorized challenge.
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    if is_verification_request(body):
        return Response(status_code=status.HTTP_200_OK)

    try:
        # Check google is the one who sent the request, via its signature.
        verifier.verify(google_health_api_signature, body)
    except SignatureError as error:
        log.add_event(request, "signature_rejected", reason=str(error))
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    try:
        delivery = parse_notification(body)
    except NotificationError as error:
        log.add_event(request, "notification_unparseable", reason=str(error))
        logger.warning("signed notification could not be parsed: {}", error)
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    # Events record change pointers, never measurements: the values are not in
    # the body, and fetching them is step 5.
    for pointer in delivery.pointers:
        if health_user_id := pointer.get("healthUserId"):
            log.set_user_to_request(request, health_user_id)
        log.add_event(
            request,
            "notification",
            operation=pointer.get("operation"),
            data_type=pointer.get("dataType"),
            intervals=len(pointer.get("intervals") or []),
        )

    record = log.get_request_log(request)
    notification = RawNotification(
        received_at=dt.datetime.now(dt.UTC),
        request_id=record.request_id if record else None,
        body=delivery.payload,
        pointer_count=len(delivery.pointers),
    )
    try:
        # SQLModel is synchronous and this handler is not, so committing inline
        # would block the event loop uvicorn serves every other request on. The
        # threadpool is where FastAPI already runs blocking work.
        notification_id = await run_in_threadpool(
            _record_delivery, session, notification
        )
    except Exception as error:
        session.rollback()
        # The exception's *type*, never its message. A SQLAlchemy
        # StatementError stringifies to include the statement and its bound
        # parameters, and those parameters are this delivery's health data --
        # so logging the message would put the payload in the log the rest of
        # this module carefully keeps it out of.
        reason = type(error).__name__
        log.add_event(request, "audit_write_failed", reason=reason)
        # Nothing was queued, so nothing is half-done. Refusing means Google
        # redelivers and the notification is not lost.
        logger.error("could not record notification: {}", reason)
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        for pointer in delivery.pointers:
            await publisher.publish(pointer, notification_id=notification_id)
    except QueueError as error:
        log.add_event(request, "publish_failed", reason=str(error))
        # The audit row stays: it is a true record that this delivery arrived,
        # and the redelivery will simply add another. What must not happen is
        # acknowledging work that was never queued.
        logger.error("could not publish notification: {}", error)
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    log.add_event(request, "queued", notification_id=notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _record_delivery(session: Session, notification: RawNotification) -> int:
    """Write the audit row and return the id the database assigned it.

    Separate so it reaches the threadpool as one blocking unit rather than three.

    Returning the id rather than reading `notification.id` at the call site is
    what makes it an `int`: the column is `int | None` because it is unset before
    the insert, and every message published carries this value as the link back
    to the row. A message with a null link would be unattributable.
    """
    session.add(notification)
    session.commit()
    session.refresh(notification)
    if notification.id is None:  # the database assigns it; this cannot happen
        raise RuntimeError("audit row committed without an id")
    return notification.id
