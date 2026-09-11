import { NavLink, Outlet } from "react-router";
import { cn } from "@/lib/utils";

// System health and analytics join this list in E8.6, once the real API serves them.
const NAV = [{ to: "/", label: "Cases" }];

/** Application chrome: a single-row header and the routed page beneath it. */
export function Shell() {
  return (
    <div className="min-h-dvh">
      <header className="flex h-12 items-center gap-6 border-b border-border px-4">
        <span className="font-mono text-base font-medium tracking-wide">REWIND</span>
        <nav aria-label="Primary" className="flex gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-1.5 text-sm text-text-muted transition-colors duration-(--motion-fast) hover:bg-surface-raised hover:text-text",
                  isActive && "bg-surface-raised font-medium text-text",
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-5">
        <Outlet />
      </main>
    </div>
  );
}
