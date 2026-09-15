# ADR-0009: The role boundary lives in the API, not in Supabase Auth

- **Status:** Accepted
- **Date:** 2026-09-15
- **Amends:** `ADR-0003` (which assigned the §M role boundary to Supabase Auth and RLS)

## Context

Specification §M asks for one boundary before any multi-user deployment: raw video
separated from derived metadata, with access to sensitive evidence logged. `ADR-0003`
planned to draw it with Supabase Auth and Row Level Security, and left the policies to
be designed in E10.3.

Two things have changed since. `ADR-0007` made the full stack run on its own Postgres
so that Gate 6 needs no third-party account; a boundary that needs Supabase Auth would
put that account back. And RLS never applied to the traffic that matters: the API
connects to Postgres as the schema's owner, so every request it serves runs with the
service role's rights whatever the caller's identity. RLS protects the database from
direct clients — anon-key reads return nothing, verified in `docs/09-deployment.md` —
but the investigator UI is not a direct client. The check has to live in the process
that serves the request.

The browser adds a constraint. Footage plays in `<video>` elements, which send whatever
credentials the browser holds for the origin and cannot be given a bearer token; a
token scheme would need the token in the clip URL, where it lands in logs and
referrers.

## Decision

**HTTP Basic authentication in FastAPI, with accounts from the environment.**
`REWIND_USERS` holds `name:password:role` entries; a dependency resolves credentials to
a principal and every endpoint but `/health` requires one. Two roles: `analyst` reads
every derived artefact (timeline, evidence graph, hypotheses, report, metrics);
`investigator` also streams footage and makes every change (create, status, reprocess).
Footage reads, evidence graph reads and report reads write a row to the append-only
`evidence_access_log` table PS-4 laid down, and emit the same fact as a structured log
event.

Basic is chosen for the property that matters here: the browser resends the cached
credentials on every same-origin request, `<video>` included, so the footage boundary
needs no second mechanism. The API is only reached through the UI's origin (nginx in
the compose stack, Vite's proxy in development), which is what makes that hold.

Supabase Auth and RLS are unchanged: RLS stays enabled deny-all, which is the correct
default for a database that only the API should reach. Nothing in this decision
prevents a hosted deployment from putting Supabase Auth in front of the same
dependency later.

## Alternatives considered

| Option | Why not |
|---|---|
| Supabase Auth JWTs verified by the API | Reinstates the account requirement `ADR-0007` removed; needs a login UI; footage needs a token-in-URL scheme. |
| Both, selected by configuration | Two code paths for one security boundary: twice the tests, twice the places a permission bug can hide. |
| Session cookie issued by a login endpoint | Works for `<video>` too, but is a login form, a signing key and a cookie policy to write and test, for what a browser already does with Basic. |
| Accounts in the database | User management is a charter non-goal (§4). Two accounts in an environment variable is the size of the need. |

## Consequences

**Gained.** The boundary §M asks for, enforced where requests are served, with an
audit trail that survives log rotation. Gate 6 still needs no account: the compose
stack ships two demo accounts and the README says to change them.

**Lost.** Basic sends the password on every request, so the API must sit behind TLS
anywhere but a laptop; `docs/10-security-and-privacy.md` says so. The browser's native
prompt is the sign-in UI — plain, and not something the design language covers. There
is no sign-out short of closing the browser.

**Limits.** Passwords cannot contain `:` or `,`; a deployment that needs more than a
handful of accounts has outgrown an environment variable and should revisit this ADR.
The role check is per process and stateless, so API replicas need no shared session
store.

## Validation plan

- Unauthenticated: 401 with a Basic challenge on every path but `/health`.
- Analyst: 200 on the report and evidence graph, 403 on footage and every change.
- Investigator: 200 on footage; the access row and the log line both name the account
  and the camera.
- The browser checks (`make ui-check`) run signed in and still scrub footage.
- Revisit if a second role is asked for, or if a hosted deployment needs single
  sign-on.

## Related

`ADR-0003` · `ADR-0007` · `apps/api/auth.py` · `docs/10-security-and-privacy.md` ·
specification §M · roadmap E10.3.
