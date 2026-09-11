import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router";
import { api } from "@/api/client";
import { INCIDENT_CLASS_LABEL, SEVERITIES, STATUSES } from "@/api/types";
import { SeverityMark } from "@/components/SeverityMark";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { clock } from "@/lib/format";

const ANY = "any";

/**
 * Case inbox: every incident the pipeline has opened, filtered by severity and status.
 *
 * Filters live in the URL so a filtered view is a link an investigator can hand to a
 * colleague, and so browser back restores the previous view.
 */
export function InboxPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const severity = params.get("severity") ?? undefined;
  const status = params.get("status") ?? undefined;

  const cases = useQuery({
    queryKey: ["cases", { severity, status }],
    queryFn: () => api.listCases({ severity, status }),
  });

  function setFilter(key: "severity" | "status", value: string) {
    const next = new URLSearchParams(params);
    if (value === ANY) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-medium">Cases</h1>
          <p className="text-sm text-text-muted">
            {cases.data ? `${cases.data.total} incident${cases.data.total === 1 ? "" : "s"}` : " "}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <FilterSelect
            label="Severity"
            value={severity ?? ANY}
            options={SEVERITIES}
            onChange={(v) => setFilter("severity", v)}
          />
          <FilterSelect
            label="Status"
            value={status ?? ANY}
            options={STATUSES}
            onChange={(v) => setFilter("status", v)}
          />
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-36">Severity</TableHead>
              <TableHead>Incident</TableHead>
              <TableHead>Class</TableHead>
              <TableHead className="text-right">Detected</TableHead>
              <TableHead className="text-right">Window</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Run</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cases.isPending && <SkeletonRows />}
            {cases.isError && (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center">
                  <p className="text-conflicting">Could not load cases: {cases.error.message}</p>
                  <Button variant="outline" size="sm" className="mt-3" onClick={() => cases.refetch()}>
                    Retry
                  </Button>
                </TableCell>
              </TableRow>
            )}
            {cases.data?.cases.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-text-muted">
                  No incidents match these filters.
                </TableCell>
              </TableRow>
            )}
            {cases.data?.cases.map((c) => (
              <TableRow
                key={c.incident_id}
                tabIndex={0}
                role="link"
                aria-label={`Open case ${c.incident_id}`}
                className="cursor-pointer"
                onClick={() => navigate(`/cases/${c.incident_id}`)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    navigate(`/cases/${c.incident_id}`);
                  }
                }}
              >
                <TableCell>
                  <SeverityMark severity={c.severity} />
                </TableCell>
                <TableCell className="font-mono">{c.incident_id}</TableCell>
                <TableCell>{INCIDENT_CLASS_LABEL[c.incident_class]}</TableCell>
                <TableCell className="tabular text-right">{clock(c.detected_at_s)}</TableCell>
                <TableCell className="tabular text-right text-text-muted">
                  {clock(c.window_start_s)}-{clock(c.window_end_s)}
                </TableCell>
                <TableCell className="capitalize">{c.status}</TableCell>
                <TableCell className="font-mono text-text-muted">{c.run_id}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-text-muted">
      {label}
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-40" aria-label={`Filter by ${label.toLowerCase()}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any {label.toLowerCase()}</SelectItem>
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {o.charAt(0).toUpperCase() + o.slice(1)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}

/** Loading rows shaped like real rows, so the table does not jump when data lands. */
function SkeletonRows() {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <TableRow key={i}>
          {[36, 20, 48, 16, 24, 20, 28].map((w, j) => (
            <TableCell key={j}>
              <Skeleton className="h-4" style={{ width: `${w * 3}px` }} />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}
