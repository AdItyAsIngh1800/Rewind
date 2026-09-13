import type { EvidenceGraph, EvidenceNode, NodeType, Relation } from "@/api/types";
import { EVIDENCE_LABEL } from "@/api/types";
import { nodeLevel, nodeTime, words } from "@/lib/evidence";
import { cn } from "@/lib/utils";

interface Props {
  graph: EvidenceGraph;
  selected: string | null;
  onSelect: (id: string) => void;
}

// Columns follow how evidence is read: what nobody saw, who, what they did in time
// order, and where. A fixed layered layout instead of a force layout keeps a node in
// the same place every time the case is opened, which matters more to a reader
// comparing notes than a prettier arrangement. At the 20–40 nodes a case produces it
// fits on one screen without pan or zoom.
const COLUMNS: { title: string; types: NodeType[] }[] = [
  { title: "Unseen & undecided", types: ["gap", "conflict"] },
  { title: "Entities", types: ["entity"] },
  { title: "Events, in time order", types: ["event", "observation"] },
  { title: "Places & window", types: ["location", "interval"] },
];
const CARD_W = 220;
const CARD_H = 48;
const GAP_X = 72;
const GAP_Y = 10;
const HEAD = 28;

// Colour on an edge only where the relation is itself an evidence state. A candidate
// cause is drawn neutral: its level lives on the hypothesis, and colouring the edge
// would assert one.
interface EdgeStyle {
  stroke: string;
  dash?: string;
  width: number;
}
const EDGE_STYLE: Partial<Record<Relation, EdgeStyle>> = {
  candidate_cause_of: { stroke: "var(--text)", dash: "6 4", width: 2 },
  contradicts: { stroke: "var(--evidence-conflicting)", width: 2 },
  occludes: { stroke: "var(--evidence-unknown)", dash: "2 3", width: 2 },
};
const DEFAULT_EDGE: EdgeStyle = { stroke: "var(--border)", width: 1 };

const start = (n: EvidenceNode) => n.interval_s?.[0] ?? n.timestamp_s ?? Number.POSITIVE_INFINITY;

/** The evidence graph, every node selectable into the inspector. */
export function EvidenceGraphView({ graph, selected, onSelect }: Props) {
  if (graph.nodes.length === 0) {
    return <p className="rounded-lg border border-border p-6 text-text-muted">This case has no evidence graph.</p>;
  }
  const place = new Map<string, { x: number; y: number; col: number }>();
  const columns = COLUMNS.map((c, col) => {
    const nodes = graph.nodes
      .filter((n) => c.types.includes(n.node_type))
      .sort((a, b) => start(a) - start(b) || a.label.localeCompare(b.label));
    nodes.forEach((n, row) => place.set(n.node_id, { x: col * (CARD_W + GAP_X), y: HEAD + row * (CARD_H + GAP_Y), col }));
    return nodes;
  });
  const width = COLUMNS.length * CARD_W + (COLUMNS.length - 1) * GAP_X;
  const height = HEAD + Math.max(...columns.map((c) => c.length)) * (CARD_H + GAP_Y);
  // A report cites events by event id; the graph node for that event is its source.
  const active = selected ? graph.nodes.find((n) => n.node_id === selected || n.source_ref === selected)?.node_id : undefined;

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto rounded-lg border border-border bg-ground p-4">
        <div className="relative" style={{ width, height }}>
          <svg aria-hidden className="absolute inset-0" width={width} height={height}>
            {graph.edges.map((e) => {
              const a = place.get(e.from_node);
              const b = place.get(e.to_node);
              // Same-column edges are "precedes" between events; vertical order already says it.
              if (!a || !b || a.col === b.col) return null;
              const [l, r] = a.col < b.col ? [a, b] : [b, a];
              const x1 = l.x + CARD_W;
              const y1 = l.y + CARD_H / 2;
              const x2 = r.x;
              const y2 = r.y + CARD_H / 2;
              const style = EDGE_STYLE[e.relation] ?? DEFAULT_EDGE;
              const touches = active === undefined || e.from_node === active || e.to_node === active;
              return (
                <path
                  key={e.edge_id}
                  d={`M${x1},${y1} C${x1 + GAP_X / 2},${y1} ${x2 - GAP_X / 2},${y2} ${x2},${y2}`}
                  fill="none"
                  stroke={style.stroke}
                  strokeWidth={style.width}
                  strokeDasharray={style.dash}
                  opacity={touches ? 1 : 0.2}
                />
              );
            })}
          </svg>
          {COLUMNS.map((c, col) => (
            <p
              key={c.title}
              className="absolute top-0 text-xs font-medium text-text-muted"
              style={{ left: col * (CARD_W + GAP_X), width: CARD_W }}
            >
              {c.title}
            </p>
          ))}
          {graph.nodes.map((n) => {
            const p = place.get(n.node_id);
            if (!p) return null;
            const level = nodeLevel(n);
            const time = nodeTime(n);
            return (
              <button
                key={n.node_id}
                type="button"
                title={n.label}
                aria-pressed={n.node_id === active}
                onClick={() => onSelect(n.node_id)}
                className={cn(
                  "absolute flex items-stretch overflow-hidden rounded-md border border-border bg-surface text-left hover:bg-surface-raised",
                  n.node_id === active && "border-text ring-1 ring-text",
                )}
                style={{ left: p.x, top: p.y, width: CARD_W, height: CARD_H }}
              >
                <span aria-hidden className={cn("w-2 shrink-0", `ev-${level}`)} />
                <span className="flex min-w-0 flex-col justify-center px-2">
                  <span className="truncate text-xs font-medium">{n.label}</span>
                  <span className="truncate text-xs text-text-muted">
                    {level === "confirmed" ? words(n.node_type) : EVIDENCE_LABEL[level]}
                    {time && <span className="tabular"> · {time}</span>}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
      <ul aria-label="Edge legend" className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-text-muted">
        {[...(Object.entries(EDGE_STYLE) as [string, EdgeStyle][]), ["other relations", DEFAULT_EDGE] as [string, EdgeStyle]].map(([name, s]) => (
          <li key={name} className="flex items-center gap-2">
            <svg aria-hidden width="28" height="8">
              <line x1="0" y1="4" x2="28" y2="4" stroke={s.stroke} strokeWidth={s.width} strokeDasharray={s.dash} />
            </svg>
            {words(name)}
          </li>
        ))}
        <li>precedes: shown by vertical order</li>
      </ul>
    </div>
  );
}
