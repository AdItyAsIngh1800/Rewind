# ADR-0012: Supabase accounts beside the configured ones, through the same cookie

- **Status:** Accepted
- **Date:** 2026-09-15
- **Amends:** `ADR-0009` and `ADR-0011` (where an account may come from; the roles, the
  boundary and the cookie are unchanged)

## Context

`ADR-0009` put the accounts in `REWIND_USERS` because the charter's non-goals rule out
user management and an environment variable needed no schema, no table and no admin
screen. That holds for a demo stack the owner runs. It does not extend: a second person
who needs access needs the operator to edit an environment variable and restart the
API, and the password is in the process environment of whatever runs it.

Supabase is already the database (`ADR-0003`), so the project already has a GoTrue with
a sign-up flow, password reset, and an account list someone can administer without
touching a deployment. The owner asked for Supabase authentication alongside the
existing sign-in. The question was where it joins.

## Decision

**`POST /session` tries `REWIND_USERS` first and Supabase's password grant second, and
issues the same cookie either way.** A Supabase account signs in with its email in the
same one form. The session token gains an issuer field
(`name:role:issuer:expiry:HMAC-SHA256`) and nothing else changes: the role guard, the
403 on footage, the evidence access log and the UI all see a `Principal` and cannot
tell the two apart.

**The role comes from `app_metadata.rewind_role`, and only from there.** `user_metadata`
is writable by the account holder; reading a role from it would let anyone who can sign
up assign themselves `investigator`, which is the footage boundary this exists to hold.
An unset, unknown or malformed role is `analyst` — derived metadata, never footage — so
a misconfigured account fails closed.

**Basic stays local-only.** A password grant is a network round-trip to GoTrue and rate
limited there; on the per-request path a single replay's range requests would sign in
hundreds of times a minute. `curl` and the test suite use `REWIND_USERS`, which is what
`ADR-0009` said Basic was for.

**Local accounts win ties.** An operator locked out by a Supabase outage puts a name in
`REWIND_USERS` and gets in; no Supabase account can shadow one.

Supabase is optional: with `SUPABASE_URL` or `SUPABASE_ANON_KEY` unset — the test suite,
a local stack — the second leg returns nothing and the system is exactly `ADR-0011`.

## Alternatives considered

| Option | Why not |
|---|---|
| `@supabase/supabase-js` in the browser, its JWT verified by the API | Two session lifetimes to keep in step (its refresh token and our cookie), a second login control, an npm dependency, and JWT verification in FastAPI — for OAuth and magic links nobody has asked for. Recorded here as the upgrade path if they are. |
| Move all accounts to Supabase, drop `REWIND_USERS` | Loses the offline stack and the way in when Supabase is unreachable, and the test suite would need a live project. |
| A `profiles` table mapping Supabase user id to role | `packages/schemas/` is frozen; a new application table is a `SCHEMA_VERSION` bump and a migration to hold one string GoTrue already stores. |
| Supabase Auth on the per-request Basic path too | A round-trip and a rate limit on every request, including each `<video>` range request. |
| Let RLS decide the role | The API connects to Postgres as its owner, so RLS never sees these requests (`ADR-0009`); the check has to live in the process that serves them. |

## Consequences

**Gained.** Accounts that can be added, reset and disabled without a deployment, and
without this project growing a user-management screen the charter excludes.

**Lost.** A Supabase session cannot be revoked before it expires by editing
`REWIND_USERS`, because that list never held the name: deleting the account in Supabase
stops the next sign-in but not the outstanding twelve-hour cookie. Rotating
`REWIND_SESSION_SECRET` ends every session at once and is the fast revocation. A
GoTrue outage is reported to the person as a wrong password, deliberately — the
alternative is a 500 that reads as the API being down — and is distinguishable only in
the API's own logs.

**Unchanged.** Two roles, one boundary, one cookie, one login form. Confidentiality
still comes from TLS at the edge. `SUPABASE_ANON_KEY` is the key used, never the
service-role key, which stays server-side for the reasons `README.md` gives.

## Validation plan

- Unit test: each `app_metadata.rewind_role` value maps to the right role and an
  unknown or absent one to `analyst`; a role in `user_metadata` is ignored; an
  unconfigured Supabase, a refused password, an unreachable GoTrue and a `:` in the
  email each read as not signed in; a local account shadows a Supabase one of the same
  name; a Supabase session survives `REWIND_USERS` no longer naming it, and a tampered
  issuer field does not.
- Contract test: the existing `POST /session` suite still passes unchanged, which is
  the claim that nothing downstream can tell the two account sources apart.

## Related

`ADR-0003` · `ADR-0009` · `ADR-0011` · `apps/api/auth.py` ·
`apps/web/src/pages/LoginPage.tsx` · `docs/10-security-and-privacy.md` §1.
