# ADR-0011: A login page, on a session cookie issued from the same accounts

- **Status:** Accepted
- **Date:** 2026-09-15
- **Amends:** `ADR-0009` (how the browser presents an account; the accounts, the roles
  and the boundary are unchanged)

## Context

`ADR-0009` made the browser's own HTTP Basic prompt the sign-in, for the property that
the browser resends cached credentials on `<video>` requests. It listed the costs: a
native dialog as the sign-in UI, no sign-out, and the role visible only after the
prompt. The owner asked whether there was a login screen for the two access levels.
There was not, and the costs were the reason.

## Decision

**`POST /session` checks a name and password against `REWIND_USERS` and sets an
`HttpOnly`, `SameSite=Lax` cookie** carrying a signed, expiring token
(`name:role:expiry:HMAC-SHA256`), scoped to `/api/v1`. Every endpoint accepts the
cookie or Basic; `DELETE /session` clears the cookie. The 401 no longer carries a
`WWW-Authenticate` challenge, so the browser never opens its own dialog over the UI's
login page; `curl -u` still works because it sends Basic unprompted.

The UI gates every route on `GET /me`: no session, the login page in place of the
route, which is where the person lands after signing in. The page states the two roles
and the responsible-use line. A **Sign out** button clears the cookie and drops what
that account saw from the query cache. A 401 from any later request (an expired
session) brings the login page back the same way.

The cookie is what keeps footage working: the browser sends it on every same-origin
request, `<video>` included, so nothing about ADR-0009's boundary or its `<video>`
reasoning changes; only the credential's carrier does.

## Alternatives considered

| Option | Why not |
|---|---|
| A login form that stores Basic credentials in the page and sets the header itself | `<video>` cannot set a header; credentials in `sessionStorage` are readable by any script on the page. |
| Signed token in the clip URL for `<video>` only | Tokens in URLs land in logs and referrers, the thing ADR-0009 avoided. |
| Sessions in a database table | A signed stateless token needs no storage and no cleanup; revocation is removing the account, which ends its sessions at the next request. |

## Consequences

**Gained.** A sign-in the design language covers, a sign-out, the role boundary
explained before a case is opened, and sessions that end on their own after twelve
hours.

**Lost.** The token is not revocable individually before it expires; removing or
re-roling the account is the revocation. Sessions are signed with
`REWIND_SESSION_SECRET`; unset, each API process signs with a random key, so a restart
signs everyone out and two replicas would not honour each other's cookies. The
compose stack runs one API process and needs nothing set.

**Unchanged.** Confidentiality still comes from TLS at the edge
(`docker-compose.prod.yml`); the cookie is no more secret on a plain connection than
Basic was. The cookie is not marked `Secure` because the API sits behind nginx on
plain HTTP inside the stack; the proxy is where TLS ends.

## Validation plan

- Contract test: wrong password 401; right password sets the cookie; the cookie
  authorises and carries the role (analyst 403 on footage); delete clears it.
- Unit test: a forged role, an altered expiry, another secret, and a removed or
  re-roled account all read as no session.
- Browser (`make ui-check` signs in through the page): wrong password shows the
  error inline; analyst lands on the deep link with footage restricted; sign-out
  returns the login page in place; investigator signs in and all three clips stream.

## Related

`ADR-0009` · `apps/api/auth.py` · `apps/web/src/pages/LoginPage.tsx` ·
`docs/10-security-and-privacy.md` §1.
