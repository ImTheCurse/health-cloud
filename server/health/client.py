"""Reading measurements out of the Health API.

The notification says only *that* something changed; this is what goes and gets
the values. ``requests`` with an injectable session, mirroring
``SubscriberClient``, so every test runs against a fake transport rather than the
network.
"""

import datetime as dt
import time
from collections.abc import Callable, Iterator
from typing import Any

import requests
from loguru import logger

from server.health.const import (
    API_ROOT,
    FETCH_RETRIES,
    FILTER_FIELDS,
    LIST_UNSUPPORTED,
    MAX_PAGES,
    PAGE_SIZE,
    RETRY_BASE_DELAY_SECONDS,
    RETRYABLE_STATUSES,
    SEED_STRUCTURES,
    SESSION_PAGE_SIZE,
)
from server.health.error import (
    FetchError,
    TokenExpiredError,
    UnsupportedDataTypeError,
)
from server.health.util import parse_civil, parse_timestamp
from server.models.const import TimeStructure

#: Google's own timeout is generous; ours is not. A hung read holds a JetStream
#: message past its ack_wait and earns a redelivery on top of the stall.
REQUEST_TIMEOUT_SECONDS = 30.0


class HealthDataClient:
    """Lists dataPoints for one data type over one interval.

    Stateless with respect to users: the access token is passed per call, because
    one flow run may work through messages belonging to different users.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        api_root: str = API_ROOT,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        retries: int = FETCH_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._session = session or requests.Session()
        self._api_root = api_root.rstrip("/")
        self._timeout = timeout
        self._retries = retries
        # Injected so a test can assert the backoff without waiting it out. A test
        # that sleeps for real is a test people start skipping.
        self._sleep = sleep

    def list_data_points(
        self,
        *,
        access_token: str,
        data_type: str,
        start: dt.datetime,
        end: dt.datetime,
    ) -> Iterator[dict[str, Any]]:
        """Every dataPoint of ``data_type`` in ``[start, end)``.

        Yields rather than returning a list so a large interval is not held in
        memory in its entirety, and so a caller can commit as it goes.

        Raises:
            UnsupportedDataTypeError: this type cannot be read with ``list`` at
                all. Checked before the first request, so a notification for one
                costs nothing rather than a 400 per redelivery.
            TokenExpiredError: the token was rejected. Distinct from a transient
                failure: retrying with the same credential cannot succeed.
            FetchError: anything else Google said no to.
        """
        if data_type in LIST_UNSUPPORTED:
            raise UnsupportedDataTypeError(
                f"{data_type} cannot be read with list; Google exposes it only "
                "through rollup or for writing"
            )

        filtered = data_type in FILTER_FIELDS
        page_token: str | None = None
        for page in range(MAX_PAGES):
            body = self._page(
                access_token=access_token,
                data_type=data_type,
                start=start,
                end=end,
                page_token=page_token,
            )
            points = body.get("dataPoints") or []
            if not isinstance(points, list):
                raise FetchError(f"dataPoints was {type(points).__name__}, not a list")

            for point in points:
                if isinstance(point, dict):
                    yield point

            page_token = body.get("nextPageToken") or None
            if page_token is None:
                return

            # An unfiltered read starts at "now" and walks backwards, and results
            # are newest first, so once a whole page sits before the window there
            # is nothing older left to find. Without this, fetching one hour of
            # heart-rate means paging through every point Google holds.
            if not filtered and _entirely_before(points, start):
                logger.debug(
                    "stopping {} after {} page(s): past the start of the window",
                    data_type,
                    page + 1,
                )
                return

        raise FetchError(
            f"{data_type} did not stop paginating after {MAX_PAGES} pages; "
            "refusing to keep asking"
        )

    def _page(
        self,
        *,
        access_token: str,
        data_type: str,
        start: dt.datetime,
        end: dt.datetime,
        page_token: str | None,
    ) -> dict[str, Any]:
        url = f"{self._api_root}/users/me/dataTypes/{data_type}/dataPoints"
        params: dict[str, Any] = {"pageSize": _page_size(data_type)}

        time_filter = _time_filter(data_type, start, end)
        if time_filter is None:
            # No verified filter field for this type, which is not the same as not
            # knowing its structure -- heart-rate's shape is known and it still
            # accepts no filter. Fetching unfiltered and narrowing locally costs
            # bandwidth and keeps the type working.
            logger.debug("no filter field known for {}; fetching unfiltered", data_type)
        else:
            params["filter"] = time_filter
        if page_token is not None:
            params["pageToken"] = page_token

        response = self._request_with_retries(url, params, access_token, data_type)
        return self._response_body(response, data_type)

    def daily_floor_rollup(
        self, *, access_token: str, day: dt.date
    ) -> list[dict[str, Any]]:
        """The all-sources floor total for one civil day, not raw dataPoints.

        Floors has no ``list`` endpoint. A one-day ``dailyRollUp`` request is
        aligned with its daily aggregation window, so it can return at most one
        bucket. Refuse unexpected pagination rather than silently lose data.
        """
        start = {"year": day.year, "month": day.month, "day": day.day}
        following = day + dt.timedelta(days=1)
        end = {"year": following.year, "month": following.month, "day": following.day}
        request = {
            "range": {"start": {"date": start}, "end": {"date": end}},
            "windowSizeDays": 1,
        }
        url = f"{self._api_root}/users/me/dataTypes/floors/dataPoints:dailyRollUp"
        response = self._request_with_retries(
            url, {}, access_token, "floors", body=request
        )
        payload = self._response_body(response, "floors")
        points = payload.get("rollupDataPoints") or []
        if not isinstance(points, list) or any(not isinstance(p, dict) for p in points):
            raise FetchError("floors rollup did not contain a list of objects")
        if len(points) > 1 or payload.get("nextPageToken"):
            raise FetchError("floors rollup returned more than one daily bucket")
        return points

    @staticmethod
    def _response_body(response: requests.Response, data_type: str) -> dict[str, Any]:
        if response.status_code in (401, 403):
            raise TokenExpiredError(
                f"Health API rejected the access token with {response.status_code}"
            )
        if response.status_code >= 400:
            # Never the body: a 4xx from this endpoint can echo the filter, and
            # the filter carries the interval a user's data was requested for.
            raise FetchError(
                f"Health API answered {response.status_code} for {data_type}"
            )

        try:
            body = response.json()
        except ValueError as error:
            raise FetchError(
                "Health API answered with something that is not JSON"
            ) from error
        if not isinstance(body, dict):
            raise FetchError(
                f"Health API answered with {type(body).__name__}, not an object"
            )
        return body

    def _request_with_retries(
        self,
        url: str,
        params: dict[str, Any],
        access_token: str,
        data_type: str,
        body: dict[str, Any] | None = None,
    ) -> requests.Response:
        """GET or POST, retrying a throttle or a wobble with a doubling delay.

        Worth having rather than leaving to the broker's redelivery: a 503 in the
        middle of pagination discards the pages already fetched, and the limit is
        300 requests a minute for one user, which a paginated read of a
        high-frequency type reaches on its own. Observed live: heart-rate answered
        503 partway through.

        A non-retryable answer is returned as-is for the caller to interpret; only
        throttling, a 5xx and an unreachable host are retried.
        """
        delay = RETRY_BASE_DELAY_SECONDS
        last_error: Exception | None = None

        for attempt in range(self._retries + 1):
            try:
                headers = {"Authorization": f"Bearer {access_token}"}
                if body is None:
                    response = self._session.get(
                        url, params=params, headers=headers, timeout=self._timeout
                    )
                else:
                    response = self._session.post(
                        url, json=body, headers=headers, timeout=self._timeout
                    )
            except requests.RequestException as error:
                last_error = error
            else:
                if response.status_code not in RETRYABLE_STATUSES:
                    return response
                last_error = None
                if attempt == self._retries:
                    return response
                logger.info(
                    "Health API answered {} for {}; retrying in {}s",
                    response.status_code,
                    data_type,
                    delay,
                )

            if attempt == self._retries:
                break
            self._sleep(delay)
            delay *= 2

        raise FetchError(
            f"could not reach the Health API for {data_type}: "
            f"{type(last_error).__name__ if last_error else 'unknown'}"
        )


def _entirely_before(points: list[Any], start: dt.datetime) -> bool:
    """Whether every point on this page falls before the window.

    Daily summaries have only a civil date. Allow one day on either side of
    the UTC window for the user's unknown offset. An unreadable point prevents
    an early stop: we cannot prove that everything on the page is too old.
    """
    if not points:
        return False
    for point in points:
        moment = _point_time(point)
        if moment is not None:
            if moment >= start:
                return False
            continue
        civil_date = _point_date(point)
        if civil_date is None or civil_date >= start.date() - dt.timedelta(days=1):
            return False
    return True


def _point_time(point: Any) -> dt.datetime | None:
    """A point's own time, wherever its shape keeps it."""
    if not isinstance(point, dict):
        return None
    for key, payload in point.items():
        if key in {"name", "dataSource", "dataType", "etag"} or not isinstance(
            payload, dict
        ):
            continue
        interval = payload.get("interval")
        if isinstance(interval, dict):
            return parse_timestamp(interval.get("startTime"))
        sample = payload.get("sampleTime")
        if isinstance(sample, dict):
            return parse_timestamp(sample.get("physicalTime"))
    return None


def _point_date(point: Any) -> dt.date | None:
    """The bare civil date on a daily summary, if it has one."""
    if not isinstance(point, dict):
        return None
    for key, payload in point.items():
        if key in {"name", "dataSource", "dataType", "etag"} or not isinstance(
            payload, dict
        ):
            continue
        civil = parse_civil(payload.get("date"))
        if civil is not None:
            return civil.date()
    return None


def _page_size(data_type: str) -> int:
    """Google caps session types at 25 and rejects a larger ask outright."""
    if SEED_STRUCTURES.get(data_type) is TimeStructure.SESSION:
        return SESSION_PAGE_SIZE
    return PAGE_SIZE


def _time_filter(data_type: str, start: dt.datetime, end: dt.datetime) -> str | None:
    """Google's AIP-160 filter for the window, or None if it cannot be spelled.

    The field path is prefixed with the data type, and which field is accepted is
    a property of the *type* rather than of its structure: ``steps`` takes
    ``interval.start_time``, ``sleep`` -- also an interval-shaped session -- takes
    ``interval.end_time``, and ``heart-rate`` takes nothing at all. All verified
    against the live API rather than read off the reference, which was wrong about
    sleep.

    A type with no known field is fetched unfiltered. A guess would be worse than
    none: a wrong field name is a 400, and a wrong-but-valid field silently filters
    on something else.
    """
    field = FILTER_FIELDS.get(data_type)
    if field is None:
        return None
    return (
        f'{data_type}.{field} >= "{_rfc3339(start)}" '
        f'AND {data_type}.{field} < "{_rfc3339(end)}"'
    )


def _rfc3339(moment: dt.datetime) -> str:
    """UTC, Z-suffixed, which is the only form the filter accepts."""
    return (
        moment.astimezone(dt.UTC).replace(tzinfo=None).isoformat(timespec="seconds")
        + "Z"
    )


def within(
    point_start: dt.datetime | None,
    start: dt.datetime,
    end: dt.datetime,
    civil_date: dt.date | None = None,
) -> bool:
    """Whether an unfiltered point falls in the requested window.

    Daily summaries have no physical timestamp; their civil date is compared
    with one day's margin for an unknown UTC offset. A point with neither is
    kept rather than discarded on the strength of a field Google may omit.
    """
    if point_start is not None:
        return start <= point_start < end
    if civil_date is not None:
        return (
            start.date() - dt.timedelta(days=1)
            <= civil_date
            <= end.date() + dt.timedelta(days=1)
        )
    return True
