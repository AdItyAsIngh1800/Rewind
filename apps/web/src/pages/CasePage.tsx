import type { ReactNode } from "react";
import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router";
import { api } from "@/api/client";
import { INCIDENT_CLASS_LABEL } from "@/api/types";
import { EvidenceGraphView } from "@/components/case/EvidenceGraphView";
import { Inspector } from "@/components/case/Inspector";
import { ReplayPanel } from "@/components/case/ReplayPanel";
import { ReportView } from "@/components/case/ReportView";
import { TimelineView } from "@/components/case/TimelineView";
import { SeverityMark } from "@/components/SeverityMark";
import { StatusSelect } from "@/components/StatusSelect";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { refTime } from "@/lib/evidence";
import { clock } from "@/lib/format";

const VIEWS = ["report", "timeline", "evidence"] as const;
type View = (typeof VIEWS)[number];

/**
 * One case: its header, three views of the same evidence, and the inspector they share.
 *
 * The open view and the selected evidence id live in the URL, like the inbox filters, so
 * "look at this node" is a link, and browser back walks back through what was inspected.
 * The report opens first because the conclusion is what an investigator came for; the
 * other views are how they check it. Whatever is selected, in any view, also seeks the
 * replay to its moment, so every piece of evidence is one click from its footage.
 */
export function CasePage() {
  const { caseId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const requested = params.get("view");
  const view: View = VIEWS.find((v) => v === requested) ?? "report";
  const selected = params.get("ref");

  const detail = useQuery({ queryKey: ["case", caseId], queryFn: () => api.getCase(caseId) });
  const timeline = useQuery({ queryKey: ["timeline", caseId], queryFn: () => api.getTimeline(caseId) });
  const graph = useQuery({ queryKey: ["evidence", caseId], queryFn: () => api.getEvidence(caseId) });
  const report = useQuery({ queryKey: ["report", caseId], queryFn: () => api.getReport(caseId) });
  const replay = useQuery({ queryKey: ["replay", caseId], queryFn: () => api.getReplay(caseId) });
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity });
  const evidence = { graph: graph.data, timeline: timeline.data, hypotheses: report.data?.hypotheses };
  const seekTo = selected ? refTime(selected, evidence) : null;

  function update(key: "view" | "ref", value: string | null) {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    setParams(next);
  }
  const select = (id: string) => update("ref", id === selected ? null : id);

  if (detail.isError) {
    return (
      <div className="flex flex-col gap-3">
        <BackLink />
        <p>Could not open case {caseId}: {detail.error.message}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      <header className="flex flex-col gap-2">
        {detail.data ? (
          <>
            <h1 className="text-lg font-medium">{INCIDENT_CLASS_LABEL[detail.data.incident.incident_class]}</h1>
            <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <Meta name="Severity">
                <SeverityMark severity={detail.data.incident.severity} />
              </Meta>
              <Meta name="Incident">
                <span className="font-mono">{detail.data.incident.incident_id}</span>
              </Meta>
              <Meta name="Detected">
                <span className="tabular">{clock(detail.data.incident.detected_at_s)}</span>
              </Meta>
              <Meta name="Window">
                <span className="tabular">
                  {clock(detail.data.incident.window_start_s)}–{clock(detail.data.incident.window_end_s)}
                </span>
              </Meta>
              <Meta name="Status">
                <StatusSelect incident={detail.data.incident} />
              </Meta>
              <Meta name="Run">
                <span className="font-mono text-text-muted">{detail.data.run.run_id}</span>
              </Meta>
            </dl>
          </>
        ) : (
          <>
            <Skeleton className="h-6 w-80" />
            <Skeleton className="h-9 w-full max-w-2xl" />
          </>
        )}
      </header>

      <Loaded query={replay} what="replay">
        {(data) => (
          <ReplayPanel replay={data} seekTo={seekTo} seekKey={selected} footage={me.data?.role === "investigator"} />
        )}
      </Loaded>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
        <Tabs value={view} onValueChange={(v) => update("view", v)} className="min-w-0">
          <TabsList>
            <TabsTrigger value="report">Report</TabsTrigger>
            <TabsTrigger value="timeline">Timeline</TabsTrigger>
            <TabsTrigger value="evidence">Evidence graph</TabsTrigger>
          </TabsList>
          <TabsContent value="report" className="pt-2">
            <Loaded query={report} what="report">
              {(data) => <ReportView data={data} evidence={evidence} selected={selected} onSelect={select} />}
            </Loaded>
          </TabsContent>
          <TabsContent value="timeline" className="pt-2">
            <Loaded query={timeline} what="timeline">
              {(data) => (
                <TimelineView
                  timeline={data}
                  graph={graph.data}
                  triggerAt={detail.data?.incident.detected_at_s}
                  selected={selected}
                  onSelect={select}
                />
              )}
            </Loaded>
          </TabsContent>
          <TabsContent value="evidence" className="pt-2">
            <Loaded query={graph} what="evidence graph">
              {(data) => <EvidenceGraphView graph={data} selected={selected} onSelect={select} />}
            </Loaded>
          </TabsContent>
        </Tabs>
        <div className="lg:sticky lg:top-4 lg:mt-11">
          <Inspector refId={selected} evidence={evidence} onSelect={select} />
        </div>
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/" className="inline-flex w-fit items-center gap-1 text-sm text-text-muted hover:text-text">
      <ArrowLeft aria-hidden className="size-4" />
      Cases
    </Link>
  );
}

function Meta({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs text-text-muted">{name}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** A view's loading, error and loaded states, so each tab fails on its own. */
function Loaded<T>({
  query,
  what,
  children,
}: {
  query: UseQueryResult<T>;
  what: string;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <Skeleton className="h-72 w-full" />;
  if (query.isError) {
    return (
      <div className="rounded-lg border border-border p-6 text-sm">
        <p>
          Could not load the {what}: {query.error.message}
        </p>
        <Button variant="outline" size="sm" className="mt-3" onClick={() => query.refetch()}>
          Retry
        </Button>
      </div>
    );
  }
  return <>{children(query.data)}</>;
}
