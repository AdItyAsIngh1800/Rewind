import type { ReactNode } from "react";
import { EvidenceMark, RefChip, ScoreBar } from "@/components/Evidence";
import { clock } from "@/lib/format";
import { type CaseEvidence, nodeLevel, nodeTime, resolveRef, words } from "@/lib/evidence";

/** Ids beyond this are summarised; an event can rest on hundreds of observations. */
const MAX_REFS = 8;

interface Props {
  refId: string | null;
  evidence: CaseEvidence;
  onSelect: (id: string) => void;
}

/**
 * What one piece of evidence rests on. Every view selects into this panel, so a claim,
 * a timeline marker and a graph node all answer "why?" the same way, and each id it
 * shows can be followed further. This is how a conclusion stays within two interactions
 * of its evidence.
 */
export function Inspector({ refId, evidence, onSelect }: Props) {
  if (!refId) {
    return (
      <Panel title="Inspector">
        <p className="text-sm text-text-muted">
          Select an evidence reference in the report, timeline or graph to see what it rests on.
        </p>
      </Panel>
    );
  }
  const refs = (ids: string[]) => <Refs ids={ids} evidence={evidence} selected={refId} onSelect={onSelect} />;
  const r = resolveRef(refId, evidence);

  switch (r.kind) {
    case "node":
      return (
        <Panel title={r.node.label} id={refId} kind={`${words(r.node.node_type)} node`}>
          <EvidenceMark level={nodeLevel(r.node)} />
          <Fields>
            {nodeTime(r.node) && <Field name="Time">{nodeTime(r.node)}</Field>}
            <Field name="Confidence">
              <ScoreBar value={r.node.confidence} />
            </Field>
            {r.node.source_ref && <Field name="Source">{refs([r.node.source_ref])}</Field>}
            <Field name="Produced by">
              {r.node.provenance.producer_service} {r.node.provenance.producer_version}
            </Field>
            {r.node.provenance.derived_from.length > 0 && (
              <Field name="Derived from">{refs(r.node.provenance.derived_from)}</Field>
            )}
          </Fields>
          {r.edges.length > 0 && (
            <div>
              <h3 className="mb-1 text-xs font-medium text-text-muted">Connections</h3>
              <ul className="flex flex-col gap-1 text-sm">
                {r.edges.map((e) => {
                  const outgoing = e.from_node === refId;
                  const other = outgoing ? e.to_node : e.from_node;
                  const label = evidence.graph?.nodes.find((n) => n.node_id === other)?.label ?? other;
                  return (
                    <li key={e.edge_id}>
                      <button
                        type="button"
                        onClick={() => onSelect(other)}
                        className="text-left hover:underline"
                      >
                        <span className="text-text-muted">
                          {outgoing ? "" : "← "}
                          {words(e.relation)}
                          {outgoing ? " → " : " "}
                        </span>
                        {label}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </Panel>
      );
    case "event":
      return (
        <Panel title={`${words(r.event.event_type)} at ${clock(r.event.timestamp_s)}`} id={refId} kind="event">
          <Fields>
            <Field name="Camera">{r.event.camera_id ?? "merged across cameras"}</Field>
            {r.event.zone_id && <Field name="Zone">{r.event.zone_id}</Field>}
            {r.event.entity_ids.length > 0 && <Field name="Entities">{r.event.entity_ids.join(", ")}</Field>}
            <Field name="Confidence">
              <ScoreBar value={r.event.confidence} />
            </Field>
            {r.node && <Field name="Graph node">{refs([r.node.node_id])}</Field>}
            <Field name="Observations">
              {r.event.evidence_refs.length > 0 ? refs(r.event.evidence_refs) : "telemetry, not video"}
            </Field>
          </Fields>
        </Panel>
      );
    case "hypothesis":
      return (
        <Panel title={r.hypothesis.description} id={refId} kind="ranked cause">
          <EvidenceMark level={r.hypothesis.evidence_level} />
          <Fields>
            <Field name="Score">
              <ScoreBar value={r.hypothesis.score} />
            </Field>
            {Object.entries(r.hypothesis.components).map(([k, v]) => (
              <Field key={k} name={words(k)}>
                <ScoreBar value={v} />
              </Field>
            ))}
            <Field name="Supported by">{refs(r.hypothesis.support_refs)}</Field>
            {r.hypothesis.contradiction_refs.length > 0 && (
              <Field name="Contradicted by">{refs(r.hypothesis.contradiction_refs)}</Field>
            )}
          </Fields>
        </Panel>
      );
    case "segment":
      return (
        <Panel title={`${r.segment.local_track_id} (${r.segment.entity_class})`} id={refId} kind="track segment">
          <Fields>
            <Field name="Camera">{r.segment.camera_id}</Field>
            <Field name="Seen">
              {clock(r.segment.start_time_s)}–{clock(r.segment.end_time_s)}
            </Field>
            <Field name="Observations">{r.segment.observation_ids.length}</Field>
            <Field name="Confidence">
              <ScoreBar value={r.segment.mean_confidence} />
            </Field>
          </Fields>
          {r.links.length > 0 && (
            <div>
              <h3 className="mb-1 text-xs font-medium text-text-muted">Cross-camera comparisons</h3>
              <ul className="flex flex-col gap-1.5 text-sm">
                {r.links.map((l) => (
                  <li key={l.link_id} className="flex flex-wrap items-center gap-2">
                    <RefChip
                      id={l.segment_a === refId ? l.segment_b : l.segment_a}
                      selected={false}
                      onSelect={onSelect}
                    />
                    <span className={l.decision === "linked" ? "" : "font-medium"}>
                      {l.decision === "linked" ? "linked" : "refused"}
                    </span>
                    <span className="tabular text-xs text-text-muted">
                      {l.score.toFixed(2)} / {l.threshold.toFixed(2)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>
      );
    case "link":
      return (
        <Panel
          title={r.link.decision === "linked" ? "Same entity across cameras" : "Identity left undecided"}
          id={refId}
          kind="identity comparison"
        >
          <Fields>
            <Field name="Segments">{refs([r.link.segment_a, r.link.segment_b])}</Field>
            <Field name="Score">
              <ScoreBar value={r.link.score} />
            </Field>
            <Field name="Threshold">
              <span className="tabular text-xs">{r.link.threshold.toFixed(2)}</span>
            </Field>
            {Object.entries(r.link.components).map(([k, v]) => (
              <Field key={k} name={words(k)}>
                <ScoreBar value={v} />
              </Field>
            ))}
          </Fields>
        </Panel>
      );
    case "missing":
      return (
        <Panel title="Not in this case" id={refId}>
          <p className="text-sm text-text-muted">
            This id is not in the case's evidence graph, the events of its window, its tracks or its ranked causes.
          </p>
        </Panel>
      );
  }
}

function Panel({ title, id, kind, children }: { title: string; id?: string; kind?: string; children: ReactNode }) {
  return (
    <aside aria-label="Evidence inspector" className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <div>
        {kind && <p className="text-xs text-text-muted capitalize">{kind}</p>}
        <h2 className="font-medium">{title}</h2>
        {id && <p className="font-mono text-xs break-all text-text-muted">{id}</p>}
      </div>
      {children}
    </aside>
  );
}

function Fields({ children }: { children: ReactNode }) {
  return <dl className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm">{children}</dl>;
}

function Field({ name, children }: { name: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-text-muted capitalize">{name}</dt>
      <dd className="min-w-0">{children}</dd>
    </>
  );
}

/** Ids as chips when they resolve inside the case, as plain text when they point outside it (observation rows, zone ids). */
function Refs({
  ids,
  evidence,
  selected,
  onSelect,
}: {
  ids: string[];
  evidence: CaseEvidence;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const shown = ids.slice(0, MAX_REFS);
  return (
    <span className="flex flex-wrap gap-1">
      {shown.map((id) =>
        resolveRef(id, evidence).kind === "missing" ? (
          <span key={id} className="font-mono text-xs break-all text-text-muted">
            {id}
          </span>
        ) : (
          <RefChip key={id} id={id} selected={id === selected} onSelect={onSelect} />
        ),
      )}
      {ids.length > MAX_REFS && <span className="text-xs text-text-muted">and {ids.length - MAX_REFS} more</span>}
    </span>
  );
}
