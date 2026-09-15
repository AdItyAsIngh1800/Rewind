import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router";
import { api } from "@/api/client";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Cases" },
  { to: "/analytics", label: "Analytics" },
  { to: "/health", label: "System health" },
];

/** Application chrome: a single-row header, who is signed in, and the routed page beneath. */
export function Shell() {
  // The browser holds the credentials (HTTP Basic); the header shows the role they carry,
  // so an analyst knows why the replay offers no footage before opening a case.
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity });
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
        {me.data && (
          <span className="ml-auto truncate text-xs text-text-muted" aria-label="Signed in as">
            <span className="hidden sm:inline">{me.data.name} · </span>
            {me.data.role}
          </span>
        )}
      </header>
      <main className="mx-auto max-w-7xl px-4 py-5">
        <Outlet />
      </main>
    </div>
  );
}
