import { type FormEvent, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";

/**
 * Sign in. Shown by the shell whenever the API has no session for this browser.
 *
 * The two roles are stated on the page rather than discovered later: an analyst who
 * expects footage should know before opening a case why the panes will be blank.
 * On success the `me` query is replaced, and the shell renders whatever route the
 * person was on.
 */
export function LoginPage() {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => api.login(name, password),
    onSuccess: (me) => {
      client.setQueryData(["me"], me);
      void client.invalidateQueries();
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (name && password) login.mutate();
  }

  return (
    <main className="mx-auto grid min-h-dvh max-w-5xl grid-cols-1 items-center gap-10 px-4 py-10 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section className="flex flex-col gap-4">
        <span className="font-mono text-base font-medium tracking-wide">REWIND</span>
        <h1 className="text-2xl font-medium leading-tight sm:text-3xl">
          Evidence-backed incident reconstruction for multi-camera video.
        </h1>
        <p className="max-w-[60ch] text-sm text-text-muted">
          Three cameras, one shared clock. An incident opens a case; the case carries a synchronized replay, a
          timeline, an evidence graph with provenance on every node, ranked causes with their contradictions, and
          a report in which every claim cites what it rests on and every unseen interval is stated as such.
        </p>
        <dl className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm">
          <dt className="font-mono text-text-muted">analyst</dt>
          <dd>Reads every derived artefact: timeline, graph, hypotheses, report, metrics. Never a frame of footage.</dd>
          <dt className="font-mono text-text-muted">investigator</dt>
          <dd>Everything an analyst reads, plus the footage, and the changes: queue a run, move a case through review.</dd>
        </dl>
        <p className="text-xs text-text-muted">
          Decision support for a human investigation; never an autonomous disciplinary, legal or safety adjudicator.
          Every read of footage, graph or report is recorded.
        </p>
      </section>

      <form onSubmit={submit} className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-5" aria-labelledby="login">
        <h2 id="login" className="text-base font-medium">
          Sign in
        </h2>
        <label className="flex flex-col gap-1 text-sm">
          Account or email
          <input
            name="name"
            autoComplete="username"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-9 rounded-md border border-border bg-surface-raised px-2 font-mono text-sm text-text"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Password
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-9 rounded-md border border-border bg-surface-raised px-2 font-mono text-sm text-text"
          />
        </label>
        {login.isError && (
          <p role="alert" className="text-sm text-conflicting">
            {login.error.message}
          </p>
        )}
        <Button type="submit" disabled={!name || !password || login.isPending}>
          {login.isPending ? "Signing in" : "Sign in"}
        </Button>
        <p className="text-xs text-text-muted">
          An account is one the operator set in <span className="font-mono">REWIND_USERS</span> — the compose stack
          ships demo ones — or a Supabase one, signed in with its email. Either way the same form, and sessions last
          twelve hours.
        </p>
      </form>
    </main>
  );
}
