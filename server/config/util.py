"""Formatting helpers for the human-readable log sink."""


def escape(value: str) -> str:
    """Make a value safe to splice into a loguru format template.

    The template is formatted after we return it, so an unescaped brace in a
    value would be read as a field reference and raise.
    """
    return value.replace("{", "{{").replace("}", "}}")


def summary(extra: dict) -> str:
    """The parts of an aggregated record worth seeing at a glance.

    JSON carries every field regardless; this is purely about reading a
    terminal, where a request with an event is the one you care about and an
    uneventful 200 is scenery.
    """
    parts = []
    if user := extra.get("user"):
        parts.append(f"user={user}")
    for event in extra.get("events") or []:
        described = " ".join(
            str(value) for key, value in event.items() if key != "event" and value
        )
        parts.append(
            f"{event.get('event')}({described})"
            if described
            else f"{event.get('event')}"
        )
    if error := extra.get("error"):
        parts.append(f"{error.get('cause')}: {error.get('message')}")
    return "  " + "  ".join(parts) if parts else ""


def human_format(record) -> str:
    """Put the request id in front of the message, and the story after it.

    A format *function* rather than a format string because most lines have no
    request id, and a string template referring to a missing key raises.
    """
    extra = record["extra"]
    request_id = extra.get("request_id")
    prefix = f"<cyan>{escape(request_id)}</cyan> " if request_id else ""
    suffix = escape(summary(extra))
    return (
        "<green>{time:HH:mm:ss.SSS}</green> <level>{level: <8}</level> "
        + prefix
        + "<level>{message}</level>"
        + f"<yellow>{suffix}</yellow>"
        + "\n{exception}"
    )
