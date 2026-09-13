import type { ReactNode } from "react";
import { Check, X } from "lucide-react";

interface Props {
  label: string;
  /** Formatted value, or `null` when it is not measured; never a stand-in zero. */
  value: string | null;
  detail?: ReactNode;
  /** A charter floor this value is held to. */
  floor?: { met: boolean; text: string };
}

/**
 * One number and what it means. An unmeasured value shows a dash and its detail says
 * why. Colour is reserved for evidence (PS-8), so meeting or missing a floor is carried
 * by an icon and words.
 */
export function StatTile({ label, value, detail, floor }: Props) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-surface p-4">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="tabular text-2xl font-medium">{value ?? "—"}</span>
      {floor && (
        <span className="inline-flex items-center gap-1 text-xs">
          {floor.met ? <Check aria-hidden className="size-3.5" /> : <X aria-hidden className="size-3.5" />}
          {floor.met ? "Meets" : "Below"} {floor.text}
        </span>
      )}
      {detail && <span className="text-xs text-text-muted">{detail}</span>}
    </div>
  );
}
