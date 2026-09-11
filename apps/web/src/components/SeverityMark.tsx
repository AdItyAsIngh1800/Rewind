import type { Severity } from "@/api/types";
import { cn } from "@/lib/utils";

const RANK: Record<Severity, number> = { low: 1, medium: 2, high: 3, critical: 4 };

/**
 * Severity carried by weight, not hue. PS-8 reserves colour for evidence states, so a
 * red "critical" chip would read as conflicting evidence to anyone scanning the
 * encoding. Four bars filled to the rank, plus the word, survive greyscale as well.
 */
export function SeverityMark({ severity }: { severity: Severity }) {
  const rank = RANK[severity];
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden className="flex gap-px">
        {[1, 2, 3, 4].map((i) => (
          <span
            key={i}
            className={cn("h-3 w-1 rounded-sm", i <= rank ? "bg-text" : "bg-border")}
          />
        ))}
      </span>
      <span className={cn("capitalize", rank >= 3 && "font-medium")}>{severity}</span>
    </span>
  );
}
