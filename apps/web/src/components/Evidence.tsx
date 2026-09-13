import { EVIDENCE_LABEL, type EvidenceLevel } from "@/api/types";
import { cn } from "@/lib/utils";

/**
 * An evidence state on the PS-8 channels: colour and pattern in the swatch, words
 * beside it. `label={false}` only where the adjacent text already carries the level's
 * required phrase, as every report claim does by contract.
 */
export function EvidenceMark({ level, label = true }: { level: EvidenceLevel; label?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium">
      <span aria-hidden className={cn("h-3 w-5 shrink-0 rounded-sm border border-border", `ev-${level}`)} />
      {label && EVIDENCE_LABEL[level]}
    </span>
  );
}

/** An evidence id the reader can follow into the inspector, shown verbatim because it is what the report cites. */
export function RefChip({
  id,
  selected,
  onSelect,
}: {
  id: string;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      aria-pressed={selected}
      className={cn(
        "rounded-sm border border-border px-1.5 py-0.5 text-left font-mono text-xs break-all text-text-muted transition-colors duration-(--motion-fast) hover:bg-surface-raised hover:text-text",
        selected && "border-text bg-surface-raised text-text",
      )}
    >
      {id}
    </button>
  );
}

/** A 0–1 value as a bar plus its digits. Monochrome: colour is reserved for evidence. */
export function ScoreBar({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden className="h-1.5 w-16 rounded-sm bg-border">
        <span className="block h-full rounded-sm bg-text" style={{ width: `${Math.round(value * 100)}%` }} />
      </span>
      <span className="tabular text-xs">{value.toFixed(2)}</span>
    </span>
  );
}
