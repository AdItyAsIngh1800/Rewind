import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { type Incident, STATUS_LABEL, STATUSES } from "@/api/types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/**
 * Where a case's investigation stands, and the control that changes it. Dismissing is
 * how a false alert is recorded; the evidence and the report stay as issued. Every
 * query that lists cases refetches after a change, so the inbox, the case page and
 * analytics never disagree about a status.
 */
export function StatusSelect({ incident }: { incident: Incident }) {
  const client = useQueryClient();
  const update = useMutation({
    mutationFn: (status: Incident["status"]) => api.setCaseStatus(incident.incident_id, status),
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ["cases"] }),
        client.invalidateQueries({ queryKey: ["case", incident.incident_id] }),
      ]),
  });
  const value = update.isPending ? update.variables : incident.status;

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Select
        value={value}
        disabled={update.isPending}
        onValueChange={(v) => {
          const status = STATUSES.find((s) => s === v);
          if (status) update.mutate(status);
        }}
      >
        <SelectTrigger className="h-8 w-52" aria-label={`Status of ${incident.incident_id}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {STATUSES.map((s) => (
            <SelectItem key={s} value={s}>
              {STATUS_LABEL[s]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {update.isError && (
        <span role="alert" className="text-xs">
          Not saved: {update.error.message}
        </span>
      )}
    </span>
  );
}
