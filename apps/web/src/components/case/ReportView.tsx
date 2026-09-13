import type { CaseReport, Claim } from "@/api/types";
import { EvidenceMark, RefChip, ScoreBar } from "@/components/Evidence";
import { type CaseEvidence, resolveRef, words } from "@/lib/evidence";

interface Props {
  data: CaseReport;
  evidence: CaseEvidence;
  selected: string | null;
  onSelect: (id: string) => void;
}

/**
 * The report as issued: observed facts, ranked causes, then what cannot be determined.
 * Every claim shows the ids it cites and the strength behind it, and every id opens in
 * the inspector.
 */
export function ReportView({ data, evidence, selected, onSelect }: Props) {
  const { report, hypotheses } = data;
  const chips = (ids: string[]) => (
    <span className="flex flex-wrap gap-1">
      {ids.map((id) => (
        <RefChip key={id} id={id} selected={id === selected} onSelect={onSelect} />
      ))}
    </span>
  );

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-1">
        <p className="text-base leading-relaxed">{report.summary}</p>
        <p className="font-mono text-xs text-text-muted">
          {report.report_id} · {report.generator_version} · {new Date(report.created_at).toLocaleString()}
        </p>
      </section>

      <section aria-labelledby="claims">
        <h2 id="claims" className="mb-2 text-sm font-medium">
          Claims
        </h2>
        <ol className="divide-y divide-border rounded-lg border border-border">
          {report.claims.map((claim) => {
            const strength = claimStrength(claim, evidence);
            return (
              <li key={claim.claim_id} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-start sm:gap-3">
                <span className="pt-0.5">
                  <EvidenceMark level={claim.evidence_level} label={false} />
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <p>{claim.text}</p>
                  {claim.evidence_refs.length > 0 && chips(claim.evidence_refs)}
                </div>
                <span className="flex shrink-0 flex-col items-start gap-0.5 sm:items-end">
                  {strength ? (
                    <>
                      <span className="text-xs text-text-muted">{strength.name}</span>
                      <ScoreBar value={strength.value} />
                    </>
                  ) : (
                    <span className="text-xs text-text-muted">no measure</span>
                  )}
                </span>
              </li>
            );
          })}
        </ol>
      </section>

      <section aria-labelledby="causes">
        <h2 id="causes" className="mb-2 text-sm font-medium">
          Ranked causes
        </h2>
        <ol className="flex flex-col gap-2">
          {hypotheses.map((h, i) => (
            <li key={h.hypothesis_id} className="flex flex-col gap-2 rounded-lg border border-border p-3">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="tabular text-xs text-text-muted">#{i + 1}</span>
                <EvidenceMark level={h.evidence_level} />
                <ScoreBar value={h.score} />
                <RefChip id={h.hypothesis_id} selected={h.hypothesis_id === selected} onSelect={onSelect} />
              </div>
              <p>{h.description}</p>
              <dl className="grid grid-cols-[minmax(0,1fr)] gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
                {Object.entries(h.components).map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-text-muted capitalize">{words(k)}</dt>
                    <dd>
                      <ScoreBar value={v} />
                    </dd>
                  </div>
                ))}
              </dl>
              <div className="flex flex-col gap-1 text-xs">
                <span className="text-text-muted">Supported by</span>
                {chips(h.support_refs)}
                {h.contradiction_refs.length > 0 && (
                  <>
                    <span className="mt-1 text-text-muted">Contradicted by</span>
                    {chips(h.contradiction_refs)}
                  </>
                )}
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="limitations">
        <h2 id="limitations" className="mb-2 text-sm font-medium">
          Limitations
        </h2>
        <p className="text-text-muted">{report.limitations}</p>
        {report.gaps.length > 0 && <div className="mt-2">{chips(report.gaps)}</div>}
      </section>
    </div>
  );
}

/**
 * The measure behind a claim, shown beside it: a ranked cause's score, else the
 * confidence of the first event it cites. "Cannot determine" claims have none, and say so.
 */
function claimStrength(claim: Claim, evidence: CaseEvidence): { name: string; value: number } | null {
  const resolved = claim.evidence_refs.map((id) => resolveRef(id, evidence));
  for (const r of resolved) if (r.kind === "hypothesis") return { name: "score", value: r.hypothesis.score };
  for (const r of resolved) {
    if (r.kind === "event") return { name: "confidence", value: r.event.confidence };
    if (r.kind === "node" && r.node.node_type === "event") return { name: "confidence", value: r.node.confidence };
  }
  return null;
}
