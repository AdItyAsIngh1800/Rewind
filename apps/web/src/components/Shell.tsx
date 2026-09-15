import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router";
import { api, ApiError, setOnUnauthorized } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { LoginPage } from "@/pages/LoginPage";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Cases" },
  { to: "/analytics", label: "Analytics" },
  { to: "/health", label: "System health" },
];

/**
 * Application chrome: a single-row header, who is signed in, and the routed page beneath.
 *
 * The session gates everything. Until `/me` answers, nothing under it mounts, so no
 * page query fires a 401 of its own; when one does later (the cookie expired), the
 * client's 401 hook clears `me` and the login page takes the place of the route the
 * person was on, which is where they return after signing in.
 */
export function Shell() {
  const client = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity, retry: false });
  const signOut = useMutation({
    mutationFn: api.logout,
    onSettled: () => {
      // Drop what this account saw before the next one signs in; resetting `me`
      // refetches it, gets the 401, and the login page replaces the route.
      client.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      void client.resetQueries({ queryKey: ["me"] });
    },
  });
  useEffect(() => {
    // Only a session that was valid is reset; `me`'s own 401 while signed out must
    // not reset itself into a loop.
    setOnUnauthorized(() => {
      if (client.getQueryData(["me"])) void client.resetQueries({ queryKey: ["me"] });
    });
  }, [client]);

  if (me.isPending) return <Skeleton className="m-4 h-12" />;
  if (me.isError) {
    if (me.error instanceof ApiError && me.error.status === 401) return <LoginPage />;
    return (
      <main className="mx-auto max-w-7xl px-4 py-10 text-sm">
        <p>The API is not reachable: {me.error.message}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={() => me.refetch()}>
          Retry
        </Button>
      </main>
    );
  }

  return (
    <div className="min-h-dvh">
      <header className="flex h-12 items-center gap-4 border-b border-border px-4 sm:gap-6">
        <span className="font-mono text-base font-medium tracking-wide">REWIND</span>
        <nav aria-label="Primary" className="flex gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-2 py-1.5 text-sm whitespace-nowrap text-text-muted transition-colors duration-(--motion-fast) hover:bg-surface-raised hover:text-text sm:px-3",
                  isActive && "bg-surface-raised font-medium text-text",
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <span className="ml-auto truncate text-xs text-text-muted" aria-label="Signed in as">
          <span className="hidden sm:inline">{me.data.name} · </span>
          {me.data.role}
        </span>
        <Button variant="ghost" size="sm" onClick={() => signOut.mutate()} disabled={signOut.isPending}>
          Sign out
        </Button>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-5">
        <Outlet />
      </main>
    </div>
  );
}
