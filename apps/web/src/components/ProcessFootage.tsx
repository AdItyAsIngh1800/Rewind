import { type FormEvent, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";

/**
 * Queue a run on footage the API knows about, from the browser.
 *
 * A native dialog: the browser traps focus and closes on Escape, which is all a
 * one-field form needs. Sources are listed by name with their latest run, so an
 * investigator sees what has already been processed before queueing it again; the
 * API's idempotency means a repeat returns the existing run rather than a second one,
 * and the result line says which happened.
 */
export function ProcessFootage({ onQueued }: { onQueued?: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const client = useQueryClient();
  const [caseRef, setCaseRef] = useState("");
  const [dataset, setDataset] = useState("v1");
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.listSources, enabled: false });
  const options = sources.data ?? [];
  // The first listed source until the investigator picks one; no state write during render.
  const selected = caseRef || options[0]?.case_ref || "";
  const chosen = options.find((s) => s.case_ref === selected);
  const queue = useMutation({
    mutationFn: () => api.createCase(selected, dataset),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["runs"] });
      void client.invalidateQueries({ queryKey: ["sources"] });
      onQueued?.();
    },
  });

  function open() {
    queue.reset();
    void sources.refetch();
    dialog.current?.showModal();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (selected) queue.mutate();
  }

  return (
    <>
      <Button size="sm" onClick={open}>
        Process footage
      </Button>
      <dialog
        ref={dialog}
        aria-labelledby="process-title"
        className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-lg border border-border bg-surface p-5 text-text backdrop:bg-ground/70"
      >
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div>
            <h2 id="process-title" className="text-base font-medium">
              Process footage
            </h2>
            <p className="text-sm text-text-muted">
              Queues one run over every clip of a case. About ten seconds on the host worker, about ninety in the
              container.
            </p>
          </div>

          <label className="flex flex-col gap-1 text-sm">
            Case
            <select
              value={selected}
              onChange={(e) => setCaseRef(e.target.value)}
              disabled={sources.isFetching && !sources.data}
              className="h-9 rounded-md border border-border bg-surface-raised px-2 font-mono text-sm text-text"
            >
              {options.map((s) => (
                <option key={s.case_ref} value={s.case_ref}>
                  {s.case_ref}
                </option>
              ))}
            </select>
            <span className="text-xs text-text-muted">
              {sources.isError
                ? `Could not list footage: ${sources.error.message}`
                : chosen
                  ? `${chosen.clips} clip${chosen.clips === 1 ? "" : "s"}${
                      chosen.latest_run_id ? `; last run ${chosen.latest_run_status} (${chosen.latest_run_id})` : "; never processed"
                    }`
                  : sources.isFetching
                    ? "Listing footage"
                    : "No footage under data/samples; run make fetch-data"}
            </span>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            Dataset version
            <input
              value={dataset}
              onChange={(e) => setDataset(e.target.value)}
              className="h-9 rounded-md border border-border bg-surface-raised px-2 font-mono text-sm text-text"
            />
            <span className="text-xs text-text-muted">Recorded on the run for reproducibility; v1 is the released dataset.</span>
          </label>

          {queue.isError && (
            <p role="alert" className="text-sm text-conflicting">
              Not queued: {queue.error.message}
            </p>
          )}
          {queue.data && (
            <p role="status" className="text-sm">
              {queue.data.created ? "Queued" : "Already processed as"}{" "}
              <span className="font-mono">{queue.data.run_id}</span>
              {queue.data.created && !queue.data.dispatched && "; the queue was unreachable, so it waits for a worker"}
              .
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => dialog.current?.close()}>
              {queue.data ? "Close" : "Cancel"}
            </Button>
            <Button type="submit" size="sm" disabled={!selected || queue.isPending}>
              {queue.isPending ? "Queueing" : "Queue run"}
            </Button>
          </div>
        </form>
      </dialog>
    </>
  );
}
