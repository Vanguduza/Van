"""P3-OBS-001 — structured logs, with the fields Gate 11 names and none of the secrets.

The redaction tests are the ones worth having. The reason secrets end up in logs
is never that somebody logged a password on purpose; it is that somebody logged a
dict they had not looked inside.
"""

from __future__ import annotations

import io
import json
import logging

import pytest

from van_gateway.observability.correlation import PREFIX, for_command, is_correlation_id
from van_gateway.observability.logging import (
    CONTEXT_FIELDS,
    REDACTED,
    JsonFormatter,
    configure,
    log_event,
)


@pytest.fixture
def captured() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    logger = logging.getLogger("van.test-logging")
    logger.handlers.clear()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def _lines(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_every_line_is_one_json_object_with_the_gate_11_fields(captured):
    logger, stream = captured
    log_event(logger, logging.INFO, "command accepted",
              correlation_id="corr_abc123456789", command_id="c1", result="accepted")
    line = _lines(stream)[0]
    for field in CONTEXT_FIELDS:
        assert field in line, field
    assert line["ts"].endswith("Z")
    assert line["service"] == "van-gateway"
    assert line["message"] == "command accepted"


def test_a_field_nobody_set_is_present_as_null_rather_than_absent(captured):
    """So an aggregator can rely on the shape, and "not set" is distinguishable
    from "this logger does not emit that field"."""
    logger, stream = captured
    log_event(logger, logging.INFO, "no context at all")
    line = _lines(stream)[0]
    assert all(line[field] is None for field in CONTEXT_FIELDS)


def test_a_secret_is_redacted_however_deeply_it_is_nested(captured):
    logger, stream = captured
    log_event(logger, logging.INFO, "dispatch", detail={
        "device_secret": "s3cret",
        "nested": {"api_key": "ak", "fine": 1, "deeper": [{"refresh_token": "rt"}]},
        "authorization": "Bearer abc",
        "harmless": "keep me",
    })
    detail = _lines(stream)[0]["detail"]
    assert detail["device_secret"] == REDACTED
    assert detail["nested"]["api_key"] == REDACTED
    assert detail["nested"]["deeper"][0]["refresh_token"] == REDACTED
    assert detail["authorization"] == REDACTED
    assert detail["nested"]["fine"] == 1
    assert detail["harmless"] == "keep me"
    assert "s3cret" not in stream.getvalue()
    assert "rt" not in json.dumps(detail)


def test_redaction_matches_by_substring_so_a_new_name_for_a_token_is_still_caught(captured):
    logger, stream = captured
    log_event(logger, logging.INFO, "x", detail={
        "hermes_bearer_token": "t", "x_van_internal_token": "t2", "signature_v2": "sig",
    })
    detail = _lines(stream)[0]["detail"]
    assert set(detail.values()) == {REDACTED}


def test_an_exception_reports_its_class_as_a_field_not_only_in_the_traceback(captured):
    logger, stream = captured
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed", extra={field: None for field in CONTEXT_FIELDS})
    line = _lines(stream)[0]
    assert line["error_class"] == "ValueError"
    assert "ValueError: boom" in line["traceback"]


def test_configure_is_idempotent():
    stream = io.StringIO()
    first = configure("INFO", stream)
    before = len(first.handlers)
    configure("INFO", stream)
    assert len(configure("DEBUG", stream).handlers) == before


# ------------------------------------------------------------------ correlation

def test_a_correlation_id_is_derived_from_the_command_and_is_therefore_stable():
    """P2-OBS-001 — derived rather than random, so a subsystem that forgot to
    propagate it can still be joined after the fact."""
    assert for_command("cmd-1") == for_command("cmd-1")
    assert for_command("cmd-1") != for_command("cmd-2")
    assert is_correlation_id(for_command("cmd-1"))
    assert for_command("cmd-1").startswith(PREFIX)
    assert len(for_command("cmd-1")) == len(PREFIX) + 12


def test_something_that_is_not_a_correlation_id_is_not_mistaken_for_one():
    for value in (None, "", "cmd-1", "corr_", "corr_NOTHEX123456", "corr_" + "a" * 13):
        assert not is_correlation_id(value), value
