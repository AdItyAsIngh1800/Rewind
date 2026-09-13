import type { ReactNode } from "react";
import type { EvidenceGraph, Timeline } from "@/api/types";
import { clock } from "@/lib/format";
import { nodeLevel, ticks, words } from "@/lib/evidence";
import { cn } from "@/lib/utils";

interface Props {
  timeline: Timeline;
  graph?: EvidenceGraph;
  triggerAt?: number;
  selected: string | null;
  onSelect: (id: string) => void;
}

/**
 * The rewind window as lanes on one clock: events, the intervals nobody saw or could
 * not decide, and every camera's tracks. The event table below carries the same events
 * as text, so nothing on the lanes is available only to a pointer.
 *
 * Selecting only opens the inspector for now; seeking the three cameras to the moment
 * arrives with the replay (E8.2).
 */
export function TimelineView({ timeline, graph, triggerAt, selected, onSelect }: Props) {
  const { events, segments } = timeline;
  const times = [...events.map((e) => e.timestamp_s), ...segments.flatMap((s) => [s.start_time_s, s.end_time_s])];
  if (times.length === 0) {
    return <p className="rounded-lg border border-border p-6 text-text-muted">No events or tracks in this window.</p>;
  }
  const start = timeline.start_s ?? Math.min(...times);
  const end = timeline.end_s ?? Math.max(...times);
  const pct = (t: number) => `${(Math.min(Math.max((t - start) / (end - start || 1), 0), 1) * 100).toFixed(3)}%`;
  const span = (a: number, b: number) => ({ left: pct(a), width: `calc(${pct(b)} - ${pct(a)})` });
  const trigger = triggerAt === undefined ? undefined : pct(triggerAt);

  const uncertain = (graph?.nodes ?? []).filter((n) => n.interval_s && (n.node_type === "gap" || n.node_type === "conflict"));
  const cameras = [...new Set(segments.map((s) => s.camera_id))].sort();
  const sortedEvents = [...events].sort((a, b) => a.timestamp_s - b.timestamp_s);
  const refused = timeline.identity_links.filter((l) => l.decision === "unknown");

  return (
    <div className="flex flex-col gap-6">
      <div className="overflow-x-auto rounded-lg border border-border bg-surface">
        <div className="min-w-[44rem] p-3">
          <Lane label={`${clock(start)}–${clock(end)}`}>
            {ticks(start, end).map((t) => (
              <span key={t} className="tabular absolute top-1 -translate-x-1/2 text-xs text-text-dim" style={{ left: pct(t) }}>
                {clock(t)}
              </span>
            ))}
          </Lane>
          <Lane label="Events" trigger={trigger}>
            {sortedEvents.map((e) => (
              <button
                key={e.event_id}
                type="button"
                title={`${words(e.event_type)} at ${clock(e.timestamp_s)}`}
                aria-label={`${words(e.event_type)} at ${clock(e.timestamp_s)}`}
                aria-pressed={e.event_id === selected}
                onClick={() => onSelect(e.event_id)}
                className={cn(
                  "absolute top-1.5 h-4 w-1.5 -translate-x-1/2 rounded-sm bg-text-muted hover:bg-text",
                  e.event_id === selected && "w-2.5 bg-text ring-2 ring-focus ring-offset-1",
                )}
                style={{ left: pct(e.timestamp_s) }}
              />
            ))}
          </Lane>
          <Lane label="Unseen / undecided" trigger={trigger}>
            {uncertain.map((n) => (
              <button
                key={n.node_id}
                type="button"
                title={n.label}
                aria-label={n.label}
                aria-pressed={n.node_id === selected}
                onClick={() => onSelect(n.node_id)}
                className={cn(
                  "absolute top-1.5 h-4 rounded-sm border border-border",
                  `ev-${nodeLevel(n)}`,
                  n.node_id === selected && "ring-2 ring-focus",
                )}
                style={span(n.interval_s![0], n.interval_s![1])}
              />
            ))}
          </Lane>
          {cameras.map((camera) => (
            <div key={camera} className="mt-2">
              <p className="py-1 text-xs font-medium">{camera}</p>
              {segments
                .filter((s) => s.camera_id === camera)
                .sort((a, b) => a.start_time_s - b.start_time_s)
                .map((s) => (
                  <Lane key={s.segment_id} label={`${s.local_track_id} · ${s.entity_class}`} trigger={trigger}>
                    <button
                      type="button"
                      aria-label={`${s.local_track_id}, ${s.entity_class}, seen ${clock(s.start_time_s)} to ${clock(s.end_time_s)}`}
                      aria-pressed={s.segment_id === selected}
                      onClick={() => onSelect(s.segment_id)}
                      className={cn(
                        "absolute top-2 h-3 rounded-sm bg-border hover:bg-text-muted",
                        s.segment_id === selected && "bg-text ring-2 ring-focus",
                      )}
                      style={span(s.start_time_s, s.end_time_s)}
                    />
                  </Lane>
                ))}
            </div>
          ))}
        </div>
      </div>

      <section aria-labelledby="events">
        <h2 id="events" className="mb-2 text-sm font-medium">
          Events in the window
        </h2>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-text-muted">
              <tr className="border-b border-border">
                <th className="px-3 py-2 font-normal">Time</th>
                <th className="px-3 py-2 font-normal">Event</th>
                <th className="px-3 py-2 font-normal">Camera</th>
                <th className="px-3 py-2 font-normal">Zone</th>
                <th className="px-3 py-2 font-normal">Entities</th>
                <th className="px-3 py-2 text-right font-normal">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {sortedEvents.map((e) => (
                <tr
                  key={e.event_id}
                  className={cn("border-b border-border last:border-b-0", e.event_id === selected && "bg-surface-raised")}
                >
                  <td className="tabular px-3 py-1.5">{clock(e.timestamp_s)}</td>
                  <td className="px-3 py-1.5">
                    <button type="button" onClick={() => onSelect(e.event_id)} className="text-left hover:underline">
                      {words(e.event_type)}
                    </button>
                  </td>
                  <td className="px-3 py-1.5 font-mono text-xs">{e.camera_id ?? "merged"}</td>
                  <td className="px-3 py-1.5">{e.zone_id ?? ""}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{e.entity_ids.join(", ")}</td>
                  <td className="tabular px-3 py-1.5 text-right">{e.confidence.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {refused.length > 0 && (
        <section aria-labelledby="refused">
          <h2 id="refused" className="mb-1 text-sm font-medium">
            Identity comparisons left undecided
          </h2>
          <p className="mb-2 text-sm text-text-muted">
            Pairs of tracks the system would not call the same entity. Each is why two lanes stay apart.
          </p>
          <ul className="flex flex-col gap-1 text-sm">
            {refused.map((l) => (
              <li key={l.link_id}>
                <button type="button" onClick={() => onSelect(l.link_id)} className="text-left hover:underline">
                  <span className="font-mono text-xs">
                    {l.segment_a} ↔ {l.segment_b}
                  </span>{" "}
                  <span className="tabular text-xs text-text-muted">
                    score {l.score.toFixed(2)}, threshold {l.threshold.toFixed(2)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** One row: a label, then a track area positioned in percent of the window. */
function Lane({ label, trigger, children }: { label: string; trigger?: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[10rem_minmax(0,1fr)] items-center">
      <div className="truncate pr-2 text-xs text-text-muted" title={label}>
        {label}
      </div>
      <div className="relative h-7">
        {trigger && <div aria-hidden className="absolute inset-y-0 w-px bg-text/40" style={{ left: trigger }} />}
        {children}
      </div>
    </div>
  );
}
