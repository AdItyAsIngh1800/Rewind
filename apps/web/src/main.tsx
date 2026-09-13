import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router";
import "./styles/globals.css";
import { Shell } from "./components/Shell";
import { InboxPage } from "./pages/InboxPage";
import { CasePage } from "./pages/CasePage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { HealthPage } from "./pages/HealthPage";

// Investigations do not change under the reader: a case is a fixed record of a run.
// A long stale time avoids refetch flicker when moving between inbox and case.
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, retry: 1 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<InboxPage />} />
            <Route path="cases/:caseId" element={<CasePage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="health" element={<HealthPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
