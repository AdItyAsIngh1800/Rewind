# maintenance

Data compaction, retention enforcement and cleanup jobs.

`delete_run.sql` removes one run and everything derived from it, in foreign-key order;
the retention rules it implements are in `docs/10-security-and-privacy.md`.
