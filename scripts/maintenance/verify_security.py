"""Verify the database security posture.

Specification §M requires role-based access control before multi-user exposure.
RLS is enabled deny-by-default (ADR-0003), but "enabled" is a property that a
future migration can silently drop — adding a table without enabling RLS on it
produces no error and no warning, just an open table.

This check makes that failure loud. Run it locally and at every gate review:

    make verify-security

Exits non-zero if any application table is unprotected.
"""

from __future__ import annotations

from sqlalchemy import text

from packages.database.session import make_engine

#: Tables that legitimately have no RLS. Alembic's bookkeeping table contains no
#: application data and is not reachable through the REST API.
EXEMPT = {"alembic_version"}


def main() -> int:
    """Audit RLS and bucket visibility; return a non-zero exit code on any gap."""
    failures: list[str] = []

    with make_engine().connect() as cx:
        rows = cx.execute(
            text("""
                select c.relname, c.relrowsecurity, c.relforcerowsecurity
                from pg_class c
                join pg_namespace n on n.oid = c.relnamespace
                where n.nspname = 'public' and c.relkind = 'r'
                order by 1
            """)
        ).all()

        print("Row Level Security")
        for name, enabled, forced in rows:
            if name in EXEMPT:
                print(f"  {name:24s} exempt")
                continue
            if not enabled:
                failures.append(f"table {name!r} has RLS disabled")
                print(f"  {name:24s} DISABLED  <-- unprotected")
            elif not forced:
                # Without FORCE, the table owner bypasses RLS. Supabase's postgres
                # role owns these tables, so this matters.
                failures.append(f"table {name!r} has RLS enabled but not forced")
                print(f"  {name:24s} enabled, NOT forced")
            else:
                print(f"  {name:24s} on + forced")

        print("\nStorage buckets")
        buckets = cx.execute(text("select id, public from storage.buckets order by 1")).all()
        if not buckets:
            failures.append("no storage buckets exist")
            print("  none found")
        for bid, is_public in buckets:
            if is_public:
                failures.append(f"bucket {bid!r} is public")
                print(f"  {bid:22s} PUBLIC  <-- raw media should not be public")
            else:
                print(f"  {bid:22s} private")

    print()
    if failures:
        print(f"FAILED — {len(failures)} problem(s):")
        for f in failures:
            print(f"  - {f}")
        print("\nAdd RLS in a supabase/migrations/ file. Do not add it via Studio.")
        return 1

    print(
        f"OK — {len(rows) - len(EXEMPT & {r[0] for r in rows})} tables protected, "
        f"{len(buckets)} buckets private."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
