-- Run once by the compose database on first start. Mirrors supabase/migrations and CI
-- for the two things Alembic does not own: the vector extension, and the search_path
-- that resolves an unqualified `vector` column the way Supabase does.
create schema if not exists extensions;
create extension if not exists vector with schema extensions;
alter database rewind set search_path to "$user", public, extensions;
