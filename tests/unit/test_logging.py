"""Structured logging: one JSON object per record, for the project's loggers and libraries'."""

from __future__ import annotations

import json
import logging

import pytest

from services.observability.logging import adopt_logger, configure_logging


def test_json_format_renders_level_logger_timestamp_and_the_formatted_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A %-style call and an exception both arrive as parseable JSON lines."""
    configure_logging(fmt="json")
    log = logging.getLogger("rewind.test")
    log.info("run %s complete: %d frames", "RUN-1", 1350)
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("run failed")
    lines = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    first, second = lines[-2], lines[-1]
    assert first["event"] == "run RUN-1 complete: 1350 frames"
    assert first["level"] == "info" and first["logger"] == "rewind.test"
    assert first["timestamp"].endswith("Z")
    assert second["level"] == "error" and "ValueError: boom" in second["exception"]


def test_json_format_carries_extra_fields_as_keys(capsys: pytest.CaptureFixture[str]) -> None:
    """The evidence access log's user and case must be filterable, not buried in the text."""
    configure_logging(fmt="json")
    logging.getLogger("rewind.test").info(
        "evidence access", extra={"user": "ana", "case_id": "INC-1"}
    )
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (line["user"], line["case_id"]) == ("ana", "INC-1")


def test_json_format_takes_over_a_server_that_installed_its_own_handler(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Uvicorn's access log would otherwise print plain text into the JSON stream."""
    access = logging.getLogger("uvicorn.access")
    access.addHandler(logging.StreamHandler())
    access.propagate = False
    configure_logging(fmt="json")
    access.info("GET /api/v1/health 200")
    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["logger"] == "uvicorn.access" and record["event"] == "GET /api/v1/health 200"


def test_console_format_prints_the_bare_message(capsys: pytest.CaptureFixture[str]) -> None:
    """At a terminal the output stays pasteable."""
    configure_logging(fmt="console")
    logging.getLogger("rewind.test").info("plain %s", "text")
    assert capsys.readouterr().out.strip().splitlines()[-1] == "plain text"


def test_a_library_logger_created_after_configuration_is_adopted_in_json_mode(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ultralytics adds its own stdout handler on first import, after startup."""
    monkeypatch.setenv("REWIND_LOG_FORMAT", "json")
    configure_logging()
    late = logging.getLogger("late.library")
    late.addHandler(logging.StreamHandler())
    late.propagate = False
    adopt_logger("late.library")
    late.info("model loaded")
    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["logger"] == "late.library" and record["event"] == "model loaded"
