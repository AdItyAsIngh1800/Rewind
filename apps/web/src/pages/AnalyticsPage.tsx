import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "@/api/client";
import { type Incident, type IncidentClass, INCIDENT_CLASS_LABEL } from "@/api/types";
import { SeverityMark } from "@/components/SeverityMark";
import { StatTile } from "@/components/StatTile";
import { StatusSelect } from "@/components/StatusSelect";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { clock } from "@/lib/format";

/** The API's inbox limit; analytics reads everything it will return. */
const LIMIT = 500;

const isOpen = (c: Incident) => c.status === "new" || c.status === "investigating";
const isReviewed = (c: Incident) => c.status === "resolved" || c.status === "dismissed";

/** Dismissed as a share of reviewed, or `null` before anything has been reviewed. */
function falseAlertRate(rows: Incident[]): number | null {
  const reviewed = rows.filter(isReviewed).length;
  return reviewed ? rows.filter((c) => c.status === "dismissed").length / reviewed : null;
}

/**
 * Analytics: which incident classes recur, how often review finds them false, and the
 * review queue that produces that number.
 *
 * The false-alert rate counts only reviewed incidents. An unreviewed incident is neither
 * a true nor a false alert yet, and counting it either way would make the rate depend on
 * how far behind review is.
 */
export function AnalyticsPage() {
  const cases = useQuery({ queryKey: ["cases", { limit: LIMIT }], queryFn: () => api.listCases({ limit: String(LIMIT) }) });

  if (cases.isPending) return <Skeleton className="h-96 w-full" />;
  if (cases.isError) {
    return (
      <div className="rounded-lg border border-border p-6 text-sm">
        <p>Could not load incidents: {cases.error.message}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={() => cases.refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  const rows = cases.data.cases;
  const rate = falseAlertRate(rows);
  const reviewed = rows.filter(isReviewed).length;
  const classes = Object.keys(INCIDENT_CLASS_LABEL) as IncidentClass[];
  // Open incidents first so the queue reads as work to do; the API's severity order holds within each.
  const queue = [...rows].sort((a, b) => Number(isOpen(b)) - Number(isOpen(a)));

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-medium">Analytics</h1>
        <p className="text-sm text-text-muted">
          Incident patterns across every run
          {cases.data.total > rows.length && `, the first ${rows.length} of ${cases.data.total}`}. Incidents carry
          run-relative time, so there is no calendar trend yet.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Incidents" value={String(cases.data.total)} detail={`across ${new Set(rows.map((c) => c.run_id)).size} runs`} />
        <StatTile label="Awaiting review" value={String(rows.filter(isOpen).length)} detail="new or investigating" />
        <StatTile label="Dismissed as false alerts" value={String(rows.filter((c) => c.status === "dismissed").length)} />
        <StatTile
          label="False-alert rate"
          value={rate === null ? null : rate.toFixed(2)}
          detail={reviewed ? `dismissed ÷ ${reviewed} reviewed` : "no incidents reviewed yet"}
        />
      </div>

      <section aria-labelledby="patterns" className="flex flex-col gap-2">
        <h2 id="patterns" className="text-sm font-medium">
          By incident class
        </h2>
        <div className="overflow-x-auto rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Class</TableHead>
                <TableHead className="text-right">Incidents</TableHead>
                <TableHead className="text-right">Runs</TableHead>
                <TableHead className="text-right">High or critical</TableHead>
                <TableHead className="text-right">Open</TableHead>
                <TableHead className="text-right">Resolved</TableHead>
                <TableHead className="text-right">Dismissed</TableHead>
                <TableHead className="text-right">False-alert rate</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {classes.map((cls) => {
                const of = rows.filter((c) => c.incident_class === cls);
                const r = falseAlertRate(of);
                return (
                  <TableRow key={cls}>
                    <TableCell>{INCIDENT_CLASS_LABEL[cls]}</TableCell>
                    <TableCell className="tabular text-right">{of.length}</TableCell>
                    <TableCell className="tabular text-right">{new Set(of.map((c) => c.run_id)).size}</TableCell>
                    <TableCell className="tabular text-right">
                      {of.filter((c) => c.severity === "high" || c.severity === "critical").length}
                    </TableCell>
                    <TableCell className="tabular text-right">{of.filter(isOpen).length}</TableCell>
                    <TableCell className="tabular text-right">{of.filter((c) => c.status === "resolved").length}</TableCell>
                    <TableCell className="tabular text-right">{of.filter((c) => c.status === "dismissed").length}</TableCell>
                    <TableCell className="tabular text-right">{r === null ? "—" : r.toFixed(2)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </section>

      <section aria-labelledby="review" className="flex flex-col gap-2">
        <div>
          <h2 id="review" className="text-sm font-medium">
            Review
          </h2>
          <p className="text-sm text-text-muted">
            Resolve an incident that happened, dismiss one that did not. The evidence and report are never changed.
          </p>
        </div>
        <div className="overflow-x-auto rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-36">Severity</TableHead>
                <TableHead>Incident</TableHead>
                <TableHead>Class</TableHead>
                <TableHead className="text-right">Detected</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {queue.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-text-muted">
                    No incidents yet.
                  </TableCell>
                </TableRow>
              )}
              {queue.map((c) => (
                <TableRow key={c.incident_id}>
                  <TableCell>
                    <SeverityMark severity={c.severity} />
                  </TableCell>
                  <TableCell>
                    <Link to={`/cases/${encodeURIComponent(c.incident_id)}`} className="font-mono hover:underline">
                      {c.incident_id}
                    </Link>
                  </TableCell>
                  <TableCell>{INCIDENT_CLASS_LABEL[c.incident_class]}</TableCell>
                  <TableCell className="tabular text-right">{clock(c.detected_at_s)}</TableCell>
                  <TableCell>
                    <StatusSelect incident={c} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>
    </div>
  );
}
