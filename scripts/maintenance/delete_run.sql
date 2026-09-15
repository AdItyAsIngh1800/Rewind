-- Delete one processing run and everything derived from it (docs/10-security-and-privacy.md).
--
--   psql "$DATABASE_URL" -v run=RUN-case_01 -f scripts/maintenance/delete_run.sql
--
-- Children first: the foreign keys do not cascade, deliberately, so nothing deletes a
-- run by accident. The evidence access log is not touched: who read the evidence is
-- kept after the evidence is gone, which is what an audit trail is for. The footage
-- itself is not in the database; see the document above for where it lives.
BEGIN;
DELETE FROM reports        WHERE incident_id IN (SELECT incident_id FROM incidents WHERE run_id = :'run');
DELETE FROM hypotheses     WHERE incident_id IN (SELECT incident_id FROM incidents WHERE run_id = :'run');
DELETE FROM evidence_edges WHERE incident_id IN (SELECT incident_id FROM incidents WHERE run_id = :'run');
DELETE FROM evidence_nodes WHERE incident_id IN (SELECT incident_id FROM incidents WHERE run_id = :'run');
DELETE FROM incidents      WHERE run_id = :'run';
DELETE FROM events         WHERE run_id = :'run';
DELETE FROM identity_links WHERE run_id = :'run';
DELETE FROM track_segments WHERE run_id = :'run';
DELETE FROM observations   WHERE run_id = :'run';
DELETE FROM processing_runs WHERE run_id = :'run';
COMMIT;
