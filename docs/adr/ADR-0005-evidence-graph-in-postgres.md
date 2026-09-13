# ADR-0005: The evidence graph lives in Postgres, traversed in application code

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

E7.1 builds one evidence graph per incident: entities, events, zones, the
investigation window, and the gaps and conflicts the uncertainty engine names, joined
by temporal, spatial, identity and causal-candidate edges. The graph has to be stored,
served to the UI (`GET /cases/{id}/evidence`), and walked by the hypothesis ranker and
the report generator.

Measured size on the tune cases is tens of nodes and at most a few hundred edges per
incident. The `evidence_nodes` and `evidence_edges` tables have existed since the
initial migration (PS-4), each row carrying its provenance as JSONB.

The roadmap and the rejected-tools list (Part 4.4) already lean against a graph
database; this records the decision and what would reverse it.

## Decision

**Store the graph in the existing Postgres tables and traverse it in Python after
loading one incident's graph.** An incident's graph is always read whole, so every walk
the ranker and generator need runs over a few hundred in-memory rows. A recursive CTE
is added only when a query needs multi-hop traversal across incidents in the database.

## Alternatives considered

| Option | Why not |
|---|---|
| Neo4j or another graph database | A second database to run, migrate, back up and secure (spec §M), for graphs a Python dict walks in microseconds. Cypher would be a second query language in a solo project |
| Recursive CTEs for every traversal now | No query yet needs to walk more than one incident, and SQL traversal of a graph that is already in memory adds round trips, not capability |
| Graph as a JSONB blob on the incident | Loses per-node indexes (node type, source ref) and the foreign keys that stop an edge from pointing at a node that does not exist |

## Consequences

- One database, one migration path, one security model. Row-level security from
  ADR-0003 covers the graph with no extra work.
- Edges reference nodes by foreign key, so a dangling edge fails at write time rather
  than as a broken UI link.
- Cross-incident questions ("every incident where this person was near a robot") need
  a CTE or a join the day they are asked. Cheap to add, since the tables are already
  relational.

## Validation plan

Revisit if a single incident's graph exceeds ~10,000 nodes, or a cross-incident
traversal is needed that a CTE cannot answer within the 500 ms budget used for
observation queries (Gate 1). Checked at Gate 4 with the measured graph sizes.

## Related

Roadmap E7.1 · Part 4.3 (Neo4j recommended against) · ADR-0003 (Supabase).
