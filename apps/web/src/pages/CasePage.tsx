import { useParams } from "react-router";

/** Placeholder until E8.2 delivers synchronized replay for a case. */
export function CasePage() {
  const { caseId } = useParams();
  return (
    <div>
      <h1 className="text-lg font-medium">
        Case <span className="font-mono">{caseId}</span>
      </h1>
      <p className="mt-2 text-text-muted">Replay, timeline and evidence arrive in E8.2 to E8.5.</p>
    </div>
  );
}
