"""The human-readable sink's formatter.

Untested until a rename broke it silently: the definitions were renamed but the
calls between them were not, so every line the terminal sink tried to emit
raised NameError inside loguru -- which swallows formatter errors and prints
"--- End of logging error ---" rather than failing. The suite stayed green.
"""

from server.config.util import escape, human_format, summary


def record(message="GET /x 200", **extra):
    return {"extra": extra, "message": message}


def test_a_line_with_no_request_id_still_formats():
    """Most lines have no request id, which is why this is a function."""
    result = human_format(record())

    assert "{message}" in result
    assert "<cyan>" not in result


def test_the_request_id_is_put_in_front():
    result = human_format(record(request_id="abc123"))

    assert "<cyan>abc123</cyan>" in result


def test_the_story_is_appended():
    result = human_format(record(user="22085a", events=[{"event": "queued"}]))

    assert "user=22085a" in result
    assert "queued" in result


def test_braces_in_a_value_cannot_break_the_template():
    """The result is a template loguru formats afterwards, so a stray brace
    would be read as a field reference and raise."""
    result = human_format(record(user="{not_a_field}"))

    assert "{{not_a_field}}" in result


def test_escape_doubles_braces():
    assert escape("a{b}c") == "a{{b}}c"


def test_summary_is_empty_when_nothing_happened():
    """An uneventful 200 should be scenery, not noise."""
    assert summary({}) == ""
