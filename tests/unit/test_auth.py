"""Accounts from the environment, and the two wrong sign-ins a probe must not tell apart."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from apps.api.auth import Principal, Role, configured_users, current_user, log_evidence_access


def test_users_parse_from_name_password_role_entries() -> None:
    """Whitespace and a trailing comma are tolerated; a bad role or shape is not."""
    users = configured_users(" ana:pw:analyst , ivo:secret:investigator,")
    assert users["ana"].role is Role.ANALYST and users["ivo"].password == "secret"
    assert configured_users("") == {}
    with pytest.raises(ValueError, match="REWIND_USERS entry 'ana:pw:boss'"):
        configured_users("ana:pw:boss")
    with pytest.raises(ValueError, match="name:password:role"):
        configured_users("ana:pw")


def test_unknown_name_and_wrong_password_are_the_same_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A probe must not learn which names exist from the response."""
    monkeypatch.setenv("REWIND_USERS", "ana:pw:analyst")
    principal = current_user(HTTPBasicCredentials(username="ana", password="pw"))
    assert (principal.name, principal.role) == ("ana", Role.ANALYST)
    responses = []
    for username, password in (("ana", "wrong"), ("nobody", "pw")):
        with pytest.raises(HTTPException) as caught:
            current_user(HTTPBasicCredentials(username=username, password=password))
        responses.append((caught.value.status_code, caught.value.detail))
    assert responses[0] == responses[1] == (401, "sign in with a REWIND account")


def test_no_accounts_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unset REWIND_USERS is a configuration error, and the 401 names it."""
    monkeypatch.delenv("REWIND_USERS", raising=False)
    with pytest.raises(HTTPException, match="set REWIND_USERS"):
        current_user(HTTPBasicCredentials(username="ana", password="pw"))


def test_access_log_carries_who_what_and_which_camera(caplog: pytest.LogCaptureFixture) -> None:
    """The audit row, the structured fields and the sentence all say the same thing."""
    session = MagicMock()
    with caplog.at_level("INFO", logger="apps.api.auth"):
        log_evidence_access(
            session, Principal("ivo", Role.INVESTIGATOR), "footage", "INC-1", camera_id="CAM_B"
        )
    row = session.add.call_args.args[0]
    assert (row.actor, row.actor_role, row.resource_type, row.resource_ref) == (
        "ivo",
        "investigator",
        "footage",
        "CAM_B",
    )
    assert row.incident_id == "INC-1" and row.action == "read"
    session.commit.assert_called_once()
    record = caplog.records[-1]
    fields = (record.action, record.user, record.role, record.camera_id)  # type: ignore[attr-defined]
    assert fields == ("evidence.access", "ivo", "investigator", "CAM_B")
    assert record.getMessage() == (
        "evidence access: ivo (investigator) read footage of case INC-1 camera_id=CAM_B"
    )
