-- 0001: extensions, row level security and storage buckets.
--
-- SCOPE RULE (ADR-0003): this file handles only what Alembic cannot express.
-- It must never create or alter an application table. Tables come from
-- SQLAlchemy models via Alembic, and that direction is one-way.

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

-- Enabled now so that E7 semantic evidence retrieval needs no migration later.
-- Costs nothing unused.
create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- Row Level Security — deny by default
-- ---------------------------------------------------------------------------
--
-- RLS is enabled with NO policies attached. That denies every request except the
-- service role, which bypasses RLS. This is the correct safe default: the API and
-- worker connect as the service role and work normally, while a leaked anon key
-- reads nothing.
--
-- The investigator/admin policy set is designed in E10.3, when there are actual
-- users and actual roles to write policies against. Designing them now would be
-- speculative. Shipping without RLS enabled at all would not be.

do $$
declare
  t text;
  app_tables text[] := array[
    'cameras', 'processing_runs', 'observations', 'track_segments',
    'identity_links', 'events', 'incidents', 'evidence_nodes',
    'evidence_edges', 'hypotheses', 'reports', 'evidence_access_log'
  ];
begin
  foreach t in array app_tables loop
    if exists (
      select 1 from pg_tables where schemaname = 'public' and tablename = t
    ) then
      execute format('alter table public.%I enable row level security', t);
      execute format('alter table public.%I force row level security', t);
    else
      raise notice 'table %% not present yet — run alembic upgrade head first', t;
    end if;
  end loop;
end
$$;

-- ---------------------------------------------------------------------------
-- Storage buckets
-- ---------------------------------------------------------------------------
--
-- Two buckets, not one. Specification section M requires raw video access to be
-- separated from derived metadata, and section E2 requires evidence snapshots
-- referenced by a report to remain immutable. Those are different lifecycles, so
-- they get different buckets and different policies.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('case-media', 'case-media', false, 524288000,
   array['video/mp4', 'video/x-matroska']),
  ('evidence-snapshots', 'evidence-snapshots', false, 10485760,
   array['image/png', 'image/jpeg', 'image/webp'])
on conflict (id) do nothing;

-- Evidence snapshots are append-only for everyone except the service role.
-- A report that cites a frame must still resolve to that same frame when the
-- report is audited later; silently swapping the image would invalidate the
-- audit trail without leaving a trace.
drop policy if exists "evidence snapshots are immutable" on storage.objects;
create policy "evidence snapshots are immutable"
  on storage.objects
  for update
  to authenticated
  using (false);

drop policy if exists "evidence snapshots cannot be deleted" on storage.objects;
create policy "evidence snapshots cannot be deleted"
  on storage.objects
  for delete
  to authenticated
  using (bucket_id <> 'evidence-snapshots');
