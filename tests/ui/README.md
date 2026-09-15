# ui

Browser checks of the investigator UI (replay sync, evidence navigation), driven by
[agent-browser](https://github.com/vercel-labs/agent-browser) against a running API and
UI. They skip when either is down or agent-browser is not installed. Run with
`make ui-check`; the browser signs in as `REWIND_UI_USER` / `REWIND_UI_PASSWORD`
(default: the Makefile's demo investigator).
