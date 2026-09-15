"""Who is asking, and whether they may see raw footage (spec §M, E10.3).

One boundary, drawn where the specification draws it: **raw video is separated from
derived metadata**. An ``analyst`` reads everything the pipeline derived — timeline,
evidence graph, hypotheses, report — and never a frame of footage. An ``investigator``
also watches the footage and changes what the system does: opens cases, moves them
through review, reprocesses them. There is no third role; the charter's non-goals rule
out user management, and a second boundary nobody has asked for would be one more
place for a permission bug to hide.

Identity is HTTP Basic with users from ``REWIND_USERS`` (ADR-0009). The browser keeps
the credentials and resends them on every same-origin request, which is what lets a
``<video>`` element fetch footage with no token scheme in the URL. Nothing here reaches
the database: the API connects to Postgres as its owner, so Row Level Security never
saw these requests, and the check has to live in the process that serves them.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from packages.database.models import EvidenceAccessLog

log = logging.getLogger(__name__)

#: ``name:password:role`` entries, comma-separated. Passwords cannot contain ``:`` or
#: ``,``; a deployment that needs them has outgrown an environment variable.
USERS_VAR = "REWIND_USERS"


class Role(StrEnum):
    """The two roles either side of the footage boundary."""

    ANALYST = "analyst"
    INVESTIGATOR = "investigator"


@dataclass(frozen=True)
class Principal:
    """An authenticated caller: the name the access log records and the role checked."""

    name: str
    role: Role


@dataclass(frozen=True)
class User:
    """One configured account."""

    password: str
    role: Role


def configured_users(spec: str | None = None) -> dict[str, User]:
    """Parse the user list, from ``REWIND_USERS`` unless one is given.

    Raises ``ValueError`` on a malformed entry rather than skipping it: a typo that
    silently dropped the investigator account would look like a wrong password at the
    browser, and be found much later.
    """
    raw = os.environ.get(USERS_VAR, "") if spec is None else spec
    users: dict[str, User] = {}
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        try:
            name, password, role = entry.split(":")
            users[name] = User(password=password, role=Role(role))
        except ValueError as exc:
            raise ValueError(
                f"{USERS_VAR} entry {entry!r} is not name:password:role with a role in "
                f"{[r.value for r in Role]}"
            ) from exc
    return users


_basic = HTTPBasic(realm="REWIND")

#: Compared against when the name is unknown, so a wrong name and a wrong password take
#: the same time and a probe cannot enumerate accounts from the response latency.
_DECOY = User(password="no such user", role=Role.ANALYST)


def current_user(credentials: Annotated[HTTPBasicCredentials, Depends(_basic)]) -> Principal:
    """Resolve the request's credentials to a principal, or challenge with 401."""
    users = configured_users()
    user = users.get(credentials.username, _DECOY)
    genuine = credentials.username in users
    matches = secrets.compare_digest(credentials.password.encode(), user.password.encode())
    if not (genuine and matches):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "sign in with a REWIND account" if users else f"no accounts: set {USERS_VAR}",
            headers={"WWW-Authenticate": 'Basic realm="REWIND"'},
        )
    return Principal(name=credentials.username, role=user.role)


def current_investigator(user: Annotated[Principal, Depends(current_user)]) -> Principal:
    """Admit only investigators: the footage side of the boundary, and every change."""
    if user.role is not Role.INVESTIGATOR:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"{user.name} is an {user.role}; footage and changes need an investigator",
        )
    return user


AnyUser = Annotated[Principal, Depends(current_user)]
Investigator = Annotated[Principal, Depends(current_investigator)]


def log_evidence_access(
    session: Session, user: Principal, resource: str, case_id: str, **detail: str
) -> None:
    """Record who read which evidence (spec §M): one audit row and one log line.

    The row is the audit trail, in the append-only ``evidence_access_log`` PS-4 laid
    down, committed by the read it belongs to and outliving any log rotation. The line
    is the same fact in the operational stream (E10.2): with ``REWIND_LOG_FORMAT=json``
    its fields are keys an aggregator can filter on, and at a terminal the message says
    it in a sentence.
    """
    session.add(
        EvidenceAccessLog(
            access_id=f"acc-{secrets.token_hex(8)}",
            accessed_at=datetime.now(UTC),
            actor=user.name,
            actor_role=user.role.value,
            incident_id=case_id,
            resource_type=resource,
            resource_ref=detail.get("camera_id", case_id),
            action="read",
            request_context=dict(detail),
        )
    )
    session.commit()
    log.info(
        "evidence access: %s (%s) read %s of case %s%s",
        user.name,
        user.role.value,
        resource,
        case_id,
        "".join(f" {k}={v}" for k, v in detail.items()),
        extra={
            "action": "evidence.access",
            "user": user.name,
            "role": user.role.value,
            "resource": resource,
            "case_id": case_id,
            **detail,
        },
    )
