import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { CircleCheck, CircleX, Clock, LoaderCircle } from "lucide-react";
import { api } from "@/api/client";
import type { ProcessingRun } from "@/api/types";
import { StatTile } from "@/components/StatTile";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { duration } from "@/lib/format";

/** A health screen is watched, not read once; stale data here would be a false "all clear". */
const LIVE = { refetchInterval: 10_000, staleTime: 0 } as const;
const NO_RUN = "no completed run has recorded it";
const NO_TRAFFIC = "no requests in the last 5 minutes";

const fixed = (v: number | null, digits: number) => (v === null ? null : v.toFixed(digits));

/**
 * System health: the API, the worker and its queue, what the pipeline has produced, and
 * every run with its duration and failure. Values the system cannot measure yet show a
 * dash and say which phase measures them, never a zero that would read as idle.
 */
export function HealthPage() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const started = performance.now();
      const body = await api.getHealth();
      return { body, ms: performance.now() - started };
    },
    ...LIVE,
  });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: api.getMetrics, ...LIVE });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api.listRuns(50), ...LIVE });
  const m = metrics.data;
  const failed = runs.data?.runs.filter((r) => r.status === "failed").length;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-lg font-medium">System health</h1>
          <p className="text-sm text-text-muted">
            Refreshes every 10 s
            {metrics.dataUpdatedAt > 0 && ` · updated ${new Date(metrics.dataUpdatedAt).toLocaleTimeString()}`}
          </p>
        </div>
        {metrics.isError && (
          <p role="alert" className="text-sm">
            Could not load metrics: {metrics.error.message}
          </p>
        )}
      </div>

      <Group title="Services">
        <StatTile
          label="API"
          value={health.isError ? "Down" : health.data ? "Up" : null}
          detail={
            health.data
              ? `${health.data.body.api_version} · schema ${health.data.body.schema_version} · ${health.data.ms.toFixed(0)} ms`
              : health.error?.message
          }
        />
        <StatTile
          label="Worker"
          value={m?.worker_last_seen_s != null ? `${duration(m.worker_last_seen_s)} ago` : null}
          detail={
            !m ? undefined : m.worker_last_seen_s !== null ? "last heartbeat" : m.queue_depth === null ? "queue unreachable" : "no heartbeat: no worker running"
          }
        />
        <StatTile
          label="Queue depth"
          value={m?.queue_depth != null ? String(m.queue_depth) : null}
          detail={
            !m ? undefined : m.queue_depth === null ? "Redis unreachable" : m.queue_oldest_age_s !== null ? `oldest waiting ${duration(m.queue_oldest_age_s)}` : "nothing waiting"
          }
        />
        <StatTile
          label="Failed runs"
          value={failed === undefined ? null : String(failed)}
          detail={runs.data && `of the ${runs.data.runs.length} most recent runs`}
        />
      </Group>

      <Group title="Pipeline output">
        <StatTile
          label="Event rate"
          value={fixed(m?.event_generation_rate ?? null, 1)}
          detail={m && (m.event_generation_rate === null ? "no completed runs" : "events per minute of footage")}
        />
        <StatTile
          label="Incident rate"
          value={fixed(m?.incident_detection_rate ?? null, 2)}
          detail={m && (m.incident_detection_rate === null ? "no completed runs" : "incidents per minute of footage")}
        />
        <StatTile
          label="Report latency"
          value={m?.report_generation_latency_s != null ? duration(m.report_generation_latency_s) : null}
          detail={m && (m.report_generation_latency_s === null ? "no reports yet" : "run start to report issued, mean")}
        />
      </Group>

      <Group title="Evidence quality">
        <StatTile
          label="Evidence coverage"
          value={fixed(m?.evidence_coverage ?? null, 2)}
          floor={m?.evidence_coverage != null ? { met: m.evidence_coverage >= 0.95, text: "charter floor ≥ 0.95" } : undefined}
          detail={m && (m.evidence_coverage === null ? "no reports yet" : "claims citing evidence, all reports")}
        />
        <StatTile
          label="Unsupported-claim rate"
          value={fixed(m?.unsupported_claim_rate ?? null, 2)}
          floor={m?.unsupported_claim_rate != null ? { met: m.unsupported_claim_rate === 0, text: "charter floor 0.00" } : undefined}
          detail={m && (m.unsupported_claim_rate === null ? "no reports yet" : "claims citing evidence that does not exist")}
        />
      </Group>

      <Group title="Reliability">
        <StatTile
          label="Worker retries"
          value={m?.worker_retries != null ? String(m.worker_retries) : null}
          detail={m && (m.worker_retries === null ? "no worker heartbeat" : "since the worker started")}
        />
        <StatTile
          label="Dead-letter jobs"
          value={m?.dead_letter_jobs != null ? String(m.dead_letter_jobs) : null}
          detail={m && (m.dead_letter_jobs === null ? "no worker heartbeat" : "failed every retry, since the worker started")}
        />
        <StatTile
          label="Frames per second"
          value={fixed(m?.frames_per_second ?? null, 1)}
          detail={m && (m.frames_per_second === null ? NO_RUN : "through perception, recent runs")}
        />
        <StatTile
          label="Peak memory"
          value={m?.peak_memory_mb != null ? `${Math.round(m.peak_memory_mb)} MB` : null}
          detail={m && (m.peak_memory_mb === null ? NO_RUN : "highest of recent runs, process and accelerator")}
        />
        <StatTile
          label="API error rate"
          value={fixed(m?.api_error_rate ?? null, 3)}
          detail={m && (m.api_error_rate === null ? NO_TRAFFIC : "server errors, last 5 minutes")}
        />
        <StatTile
          label="API latency p95"
          value={m?.api_latency_p95_ms != null ? `${Math.round(m.api_latency_p95_ms)} ms` : null}
          detail={m && (m.api_latency_p95_ms === null ? NO_TRAFFIC : "last 5 minutes")}
        />
        <StatTile
          label="ID-switch rate"
          value={null}
          detail="not measurable live: it needs ground truth. Held-out benchmark: at most 1 switch per camera per case (EXP-0011)"
        />
      </Group>

      <section aria-labelledby="runs" className="flex flex-col gap-2">
        <h2 id="runs" className="text-sm font-medium">
          Processing runs
        </h2>
        <div className="overflow-x-auto rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Device</TableHead>
                <TableHead>Dataset · config</TableHead>
                <TableHead>Started</TableHead>
                <TableHead className="text-right">Duration</TableHead>
                <TableHead>Error</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.isPending && (
                <TableRow>
                  <TableCell colSpan={7}>
                    <Skeleton className="h-4 w-full" />
                  </TableCell>
                </TableRow>
              )}
              {runs.isError && (
                <TableRow>
                  <TableCell colSpan={7} className="py-6 text-center">
                    Could not load runs: {runs.error.message}
                    <Button variant="outline" size="sm" className="ml-3" onClick={() => runs.refetch()}>
                      Retry
                    </Button>
                  </TableCell>
                </TableRow>
              )}
              {runs.data?.runs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="py-6 text-center text-text-muted">
                    No runs yet. A case submitted with POST /cases appears here.
                  </TableCell>
                </TableRow>
              )}
              {runs.data?.runs.map((r) => (
                <TableRow key={r.run_id}>
                  <TableCell className="font-mono">{r.run_id}</TableCell>
                  <TableCell>
                    <RunStatus status={r.status} />
                  </TableCell>
                  <TableCell>{r.device}</TableCell>
                  <TableCell className="text-text-muted">
                    {r.dataset_version} · {r.config_version}
                  </TableCell>
                  <TableCell className="tabular">{r.started_at ? new Date(r.started_at).toLocaleString() : ""}</TableCell>
                  <TableCell className="tabular text-right">{runDuration(r)}</TableCell>
                  <TableCell className="max-w-64 truncate" title={r.error ?? undefined}>
                    {r.error}
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

function Group({ title, children }: { title: string; children: ReactNode }) {
  const id = title.toLowerCase().replaceAll(" ", "-");
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2">
      <h2 id={id} className="text-sm font-medium">
        {title}
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">{children}</div>
    </section>
  );
}

const RUN_ICON: Record<string, typeof CircleCheck> = {
  complete: CircleCheck,
  running: LoaderCircle,
  queued: Clock,
  failed: CircleX,
};

/** Run state on icon and word; colour stays reserved for evidence. */
function RunStatus({ status }: { status: string }) {
  const Icon = RUN_ICON[status] ?? Clock;
  return (
    <span className={status === "failed" ? "inline-flex items-center gap-1.5 font-medium" : "inline-flex items-center gap-1.5"}>
      <Icon aria-hidden className="size-4" />
      <span className="capitalize">{status}</span>
    </span>
  );
}

function runDuration(run: ProcessingRun): string {
  if (!run.started_at) return "";
  const start = Date.parse(run.started_at);
  if (run.finished_at) return duration((Date.parse(run.finished_at) - start) / 1000);
  return `running ${duration((Date.now() - start) / 1000)}`;
}
