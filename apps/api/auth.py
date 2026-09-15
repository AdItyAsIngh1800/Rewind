"""Who is asking, and whether they may see raw footage (spec §M, E10.3).

One boundary, drawn where the specification draws it: **raw video is separated from
derived metadata**. An ``analyst`` reads everything the pipeline derived — timeline,
evidence graph, hypotheses, report — and never a frame of footage. An ``investigator``
also watches the footage and changes what the system does: opens cases, moves them
through review, reprocesses them. There is no third role; the charter's non-goals rule
out user management, and a second boundary nobody has asked for would be one more
place for a permission bug to hide.

Accounts come from ``REWIND_USERS`` (ADR-0009) or, when the deployment has them, from
Supabase Auth (ADR-0012); the two are tried in that order and are otherwise the same
thing to everything downstream, because both end as a ``Principal`` with one of the two
roles. Two ways to present them: HTTP Basic on the request, for ``curl`` and tests, and
a session cookie issued by ``POST /session`` from the same credentials, for the browser
(ADR-0011). Basic is local accounts only — a Supabase password grant is a round-trip to
GoTrue, and on the per-request path a video's range requests would sign in hundreds of
times a minute and meet its rate limit. The cookie is what lets the UI
have a login page and a sign-out while a ``<video>`` element, which cannot carry a
header, still fetches footage: the browser sends the cookie on every same-origin
request. Nothing here reaches the database: the API connects to Postgres as its owner,
so Row Level Security never saw these requests, and the check has to live in the
process that serves them.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from packages.database.models import EvidenceAccessLog
from supabase import AuthError, create_client

log = logging.getLogger(__name__)

#: ``name:password:role`` entries, comma-separated. Passwords cannot contain ``:`` or
#: ``,``; a deployment that needs them has outgrown an environment variable.
USERS_VAR = "REWIND_USERS"


class Role(StrEnum):
    """The two roles either side of the footage boundary."""

    ANALYST = "analyst"
    INVESTIGATOR = "investigator"


class Issuer(StrEnum):
    """Which set of accounts vouched for a principal.

    Carried in the session token because it decides what revoking means: a local
    account's session ends when its name leaves ``REWIND_USERS``, which is the only
    sign-out an operator has, while a Supabase session is revoked in Supabase and
    cannot be re-checked here without a round-trip on every request.
    """

    LOCAL = "local"
    SUPABASE = "supabase"


@dataclass(frozen=True)
class Principal:
    """An authenticated caller: the name the access log records and the role checked."""

    name: str
    role: Role
    issuer: Issuer = Issuer.LOCAL


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


_basic = HTTPBasic(realm="REWIND", auto_error=False)

#: Compared against when the name is unknown, so a wrong name and a wrong password take
#: the same time and a probe cannot enumerate accounts from the response latency.
_DECOY = User(password="no such user", role=Role.ANALYST)

SESSION_COOKIE = "rewind_session"
SESSION_TTL_S = 12 * 60 * 60
SECRET_VAR = "REWIND_SESSION_SECRET"
#: Signs sessions when no secret is configured: sessions then end when the process
#: does, and two API replicas would not honour each other's. Set the variable for both.
_PROCESS_SECRET = secrets.token_bytes(32)


def _secret() -> bytes:
    return os.environ.get(SECRET_VAR, "").encode() or _PROCESS_SECRET


def authenticate(name: str, password: str) -> Principal | None:
    """Check a name and password against the accounts; None for anything but a match."""
    users = configured_users()
    user = users.get(name, _DECOY)
    genuine = name in users
    matches = secrets.compare_digest(password.encode(), user.password.encode())
    return Principal(name=name, role=user.role) if genuine and matches else None


#: Where a Supabase account's role is read from. ``app_metadata`` and not
#: ``user_metadata``: the account holder can write the latter, and self-assigning
#: ``investigator`` is exactly the footage boundary this module exists to hold.
SUPABASE_ROLE_KEY = "rewind_role"
SUPABASE_URL_VAR = "SUPABASE_URL"
SUPABASE_KEY_VAR = "SUPABASE_ANON_KEY"


def supabase_sign_in(name: str, password: str) -> Principal | None:
    """Check a name and password against Supabase Auth; None for anything but a match.

    None also when the deployment has no Supabase configured, which is how the local
    compose stack and the test suite run with local accounts alone, and when Supabase
    is unreachable: a GoTrue outage should leave the login page saying the password was
    wrong, not returning a 500 that looks like the API itself is down.

    An unset, unknown or malformed role lands on ``analyst``, so a misconfigured
    account reads derived metadata and never footage — the boundary fails closed.
    """
    url, key = os.environ.get(SUPABASE_URL_VAR, ""), os.environ.get(SUPABASE_KEY_VAR, "")
    if not (url and key):
        return None
    try:
        answer = create_client(url, key).auth.sign_in_with_password(
            {"email": name, "password": password}
        )
    except AuthError:
        return None
    except Exception:
        log.exception("supabase sign-in could not be attempted for %s", name)
        return None
    if answer.user is None:
        return None
    email = answer.user.email or name
    if ":" in email:
        # The session token is colon-delimited, so a colon in the name would let the
        # holder of one account mint a token naming another with a different role.
        log.error("refusing supabase account %r: a ':' in the name forges session tokens", email)
        return None
    claimed = answer.user.app_metadata.get(SUPABASE_ROLE_KEY)
    if claimed is not None and claimed not in set(Role):
        log.warning(
            "supabase account %s claims unknown role %r; treating as analyst", email, claimed
        )
    role = Role(claimed) if claimed in set(Role) else Role.ANALYST
    return Principal(name=email, role=role, issuer=Issuer.SUPABASE)


def sign_in(name: str, password: str) -> Principal | None:
    """Resolve a name and password against either set of accounts, local first.

    The order is what makes a local account authoritative: an operator who needs to
    get in when Supabase is unreachable puts a name in ``REWIND_USERS``, and no
    Supabase account can shadow it.
    """
    return authenticate(name, password) or supabase_sign_in(name, password)


def issue_session(user: Principal) -> str:
    """Mint a signed, expiring session token for a principal.

    ``name:role:issuer:expiry:signature``; names cannot contain ``:`` (the accounts
    format forbids it, and ``supabase_sign_in`` refuses one that does), so the token
    splits unambiguously. HMAC over the first four fields means the token can be
    checked without storing anything.
    """
    expiry = int(time.time()) + SESSION_TTL_S
    payload = f"{user.name}:{user.role.value}:{user.issuer.value}:{expiry}"
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def read_session(token: str) -> Principal | None:
    """Return the principal a token names, or None if it is forged, expired or revoked.

    Revoked means the local account no longer exists with that role: removing a name
    from ``REWIND_USERS`` ends its sessions at the next request, which is the only
    sign-out an operator has. A Supabase session cannot be checked that way without a
    round-trip per request, so it stands on its signature until it expires; revoking
    one before then means deleting the account in Supabase and waiting out the twelve
    hours, or rotating ``REWIND_SESSION_SECRET``, which ends every session at once.
    """
    try:
        name, role, issued_by, expiry, signature = token.split(":")
        payload = f"{name}:{role}:{issued_by}:{expiry}"
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256)
        if not hmac.compare_digest(signature, expected.hexdigest()) or int(expiry) < time.time():
            return None
        issuer, claimed = Issuer(issued_by), Role(role)
    except ValueError:
        return None
    if issuer is Issuer.SUPABASE:
        return Principal(name=name, role=claimed, issuer=issuer)
    user = configured_users().get(name)
    if user is None or user.role.value != role:
        return None
    return Principal(name=name, role=user.role)


def current_user(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)],
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Principal:
    """Resolve the request's session cookie or Basic credentials to a principal, or 401.

    The 401 carries no ``WWW-Authenticate`` challenge on purpose: with one, the browser
    would open its own password dialog over the UI's login page. ``curl -u`` sends
    Basic without being challenged.
    """
    principal = read_session(session) if session else None
    if principal is None and credentials is not None:
        principal = authenticate(credentials.username, credentials.password)
    if principal is None:
        users = configured_users()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "sign in with a REWIND account" if users else f"no accounts: set {USERS_VAR}",
        )
    return principal


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
