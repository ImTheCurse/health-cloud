"""How a change pointer is routed to a subject."""

from server.queue.const import SUBJECT_PREFIX, UNKNOWN_DATA_TYPE
from server.queue.publisher import NotificationPublisher, subject_for


def test_a_pointer_goes_to_the_subject_for_its_data_type():
    assert subject_for("sleep") == f"{SUBJECT_PREFIX}.sleep"


def test_a_pointer_with_no_data_type_is_still_routable():
    """Google could add a type tomorrow; an unroutable message is a lost one."""
    assert subject_for(None) == f"{SUBJECT_PREFIX}.{UNKNOWN_DATA_TYPE}"
    assert subject_for("") == f"{SUBJECT_PREFIX}.{UNKNOWN_DATA_TYPE}"


def test_the_stream_covers_exactly_what_the_publisher_publishes():
    """These were once configured separately, and drifted.

    A stream whose filter does not match the subject being published fails as
    "no response from stream", which names neither the cause nor the fix. One
    prefix now derives both.
    """
    publisher = NotificationPublisher("nats://example.invalid:4222", subject_prefix="a.b")

    assert publisher._subjects == ("a.b.*",)
    assert subject_for("steps", "a.b").startswith("a.b.")
