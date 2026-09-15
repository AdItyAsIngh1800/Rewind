"""Browser checks for the investigator UI (E9.4), driven by agent-browser.

The two interactions the roadmap names for browser tests: **replay sync** (three camera
panes on one clock) and **evidence navigation** (selecting evidence anywhere moves every
camera to its moment). They run in a real Chrome against a running UI and API, so they
skip unless both are up and ``agent-browser`` is installed; CI has neither the video nor
the servers.

    make api; make web          # or any UI serving C01 at REWIND_UI_URL
    make ui-check               # signs in as REWIND_UI_USER / REWIND_UI_PASSWORD

Expected seek times are computed from the API with the UI's own rule (``refTime`` in
``apps/web/src/lib/evidence.ts``): an event's stamp, a node's stamp or the start of its
interval, a segment's start, a hypothesis's first timed support. A check that
hard-coded the times would pass against a UI and API that agreed on the wrong answer.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

UI = os.environ.get("REWIND_UI_URL", "http://localhost:5199")
API = os.environ.get("REWIND_API_URL", "http://localhost:8000/api/v1")
CASE = os.environ.get("REWIND_UI_CASE", "INC-RUN-case_01-01")
SESSION = "rewind-ui-check"
#: An investigator: the checks scrub footage, which the analyst role cannot see.
USER = os.environ.get("REWIND_UI_USER", "investigator")
PASSWORD = os.environ.get("REWIND_UI_PASSWORD", "rewind")


def _get(path: str) -> Any:
    """Fetch one API resource as JSON, signed in as the investigator."""
    token = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    request = urllib.request.Request(f"{API}{path}", headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def _reachable() -> str | None:
    """Return why the checks cannot run, or None when they can."""
    if shutil.which("agent-browser") is None:
        return "agent-browser is not installed"
    try:
        urllib.request.urlopen(UI, timeout=2)
        _get(f"/cases/{CASE}/replay")
    except (urllib.error.URLError, OSError) as exc:
        return f"UI at {UI} or case {CASE} at {API} unreachable: {exc}"
    return None


pytestmark = pytest.mark.skipif(_reachable() is not None, reason=str(_reachable()))


def ab(*args: str, stdin: str | None = None) -> Any:
    """Run one agent-browser command in this suite's own session; return its data."""
    out = subprocess.run(
        ["agent-browser", "--session", SESSION, "--json", *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    body = json.loads(out.stdout.strip().splitlines()[-1])
    assert body["success"], f"agent-browser {' '.join(args)}: {body['error']}"
    return body["data"]


def js(script: str) -> Any:
    """Evaluate a script in the page and return its result."""
    return ab("eval", "--stdin", stdin=script)["result"]


class Case:
    """The case's evidence from the API, and the UI's rule for when a ref happened."""

    def __init__(self) -> None:
        """Load everything the case page loads."""
        self.replay = _get(f"/cases/{CASE}/replay")
        self.offsets = {c["camera_id"]: c["clock_offset_s"] for c in self.replay["cameras"]}
        timeline = _get(f"/cases/{CASE}/timeline")
        graph = _get(f"/cases/{CASE}/evidence")
        report = _get(f"/cases/{CASE}/report")
        self.report = report["report"]
        self.events = {e["event_id"]: e for e in timeline["events"]}
        self.segments = {s["segment_id"]: s for s in timeline["segments"]}
        self.nodes = {n["node_id"]: n for n in graph["nodes"]}
        self.hypotheses = {h["hypothesis_id"]: h for h in report["hypotheses"]}

    def time_of(self, ref: str, nested: bool = False) -> float | None:
        """Mirror ``refTime``: the shared-clock second a selection seeks to."""
        if ref in self.events:
            return float(self.events[ref]["timestamp_s"])
        if ref in self.nodes:
            node = self.nodes[ref]
            if node.get("timestamp_s") is not None:
                return float(node["timestamp_s"])
            interval = node.get("interval_s")
            return float(interval[0]) if interval else None
        if ref in self.segments:
            return float(self.segments[ref]["start_time_s"])
        if ref in self.hypotheses and not nested:
            for support in self.hypotheses[ref]["support_refs"]:
                t = self.time_of(support, nested=True)
                if t is not None:
                    return t
        return None


@pytest.fixture(scope="module")
def case() -> Iterator[Case]:
    """Load the case data once, sign the browser in, and close its session after the module."""
    ab("set", "credentials", USER, PASSWORD)
    yield Case()
    subprocess.run(
        ["agent-browser", "--session", SESSION, "close"], capture_output=True, check=False
    )


def open_case(view: str = "report") -> None:
    """Open the case page on a view and wait until all three panes have footage."""
    ab("open", f"{UI}/cases/{CASE}?view={view}")
    ab(
        "wait",
        "--fn",
        "(() => { const v = [...document.querySelectorAll('video')];"
        " return v.length === 3 && v.every(x => x.readyState >= 2 && !x.seeking); })()",
    )


def panes(case: Case) -> dict[str, float]:
    """Each pane's position on the shared clock: clip time minus its offset."""
    rows = js(
        "[...document.querySelectorAll('video')]"
        ".map(v => [v.getAttribute('aria-label'), v.currentTime])"
    )
    return {label.split()[0]: t - case.offsets[label.split()[0]] for label, t in rows}


def settle() -> None:
    """Wait until no pane is mid-seek."""
    ab("wait", "--fn", "[...document.querySelectorAll('video')].every(v => !v.seeking)")


def frame(case: Case) -> float:
    """One frame on the leading camera."""
    return 1.0 / float(case.replay["cameras"][0]["fps"])


def selected_ref() -> str | None:
    """Return the ``ref`` the page put in its URL."""
    url = ab("get", "url")["url"]
    return parse_qs(urlparse(url).query).get("ref", [None])[0]


def click_button(scope: str, text: str) -> None:
    """Click the first button in ``scope`` whose text or accessible name is ``text``."""
    clicked = js(
        f"(() => {{ const b = [...document.querySelectorAll({json.dumps(scope + ' button')})]"
        f".find(b => b.textContent.trim() === {json.dumps(text)}"
        f" || b.getAttribute('aria-label') === {json.dumps(text)});"
        " if (!b) return false; b.click(); return true; })()"
    )
    assert clicked, f"no button {text!r} in {scope}"


# -- replay sync ----------------------------------------------------------------------


def test_the_three_panes_open_together_at_the_window_start(case: Case) -> None:
    """Opening a case puts every camera at the start of the rewind window."""
    open_case()
    positions = panes(case)
    assert set(positions) == set(case.offsets)
    for camera, t in positions.items():
        assert abs(t - case.replay["window_start_s"]) <= frame(case), (camera, t)


def test_go_to_detection_seeks_every_pane_to_the_same_moment(case: Case) -> None:
    """The detection button moves all three cameras to the incident's moment."""
    open_case()
    ab("find", "role", "button", "click", "--name", "Go to detection")
    settle()
    for camera, t in panes(case).items():
        assert abs(t - case.replay["detected_at_s"]) <= frame(case), (camera, t)


def test_stepping_one_frame_moves_every_pane_by_one_frame(case: Case) -> None:
    """Frame stepping keeps the panes together, one frame at a time."""
    open_case()
    ab("find", "role", "button", "click", "--name", "Go to detection")
    settle()
    before = panes(case)
    ab("find", "role", "button", "click", "--name", "Forward one frame")
    settle()
    for camera, t in panes(case).items():
        assert abs(t - before[camera] - frame(case)) <= frame(case) / 2, (camera, t, before[camera])


def test_playing_keeps_the_panes_within_a_frame_of_each_other(case: Case) -> None:
    """After a second and a half of playback, no pane has drifted more than a frame."""
    open_case()
    ab("find", "role", "button", "click", "--name", "Play")
    ab("wait", "1500")
    ab("find", "role", "button", "click", "--name", "Pause")
    settle()
    positions = panes(case)
    assert max(positions.values()) - min(positions.values()) <= frame(case), positions
    assert min(positions.values()) > case.replay["window_start_s"] + 0.5, "playback did not advance"


# -- evidence navigation --------------------------------------------------------------


def assert_seeked_to(case: Case, ref: str) -> None:
    """Assert the URL selects ``ref`` and every camera is at its moment."""
    assert selected_ref() == ref
    expected = case.time_of(ref)
    assert expected is not None, f"{ref} has no time to seek to"
    settle()
    for camera, t in panes(case).items():
        assert abs(t - expected) <= frame(case), (ref, camera, t, expected)


def test_every_citation_in_the_report_seeks_the_cameras_to_its_moment(case: Case) -> None:
    """The walkthrough, automated: each claim's first citation moves all three cameras."""
    open_case("report")
    cited = [c["evidence_refs"][0] for c in case.report["claims"] if c["evidence_refs"]]
    assert cited
    for ref in cited:
        if case.time_of(ref) is None:
            continue
        click_button("#root", ref)
        assert_seeked_to(case, ref)


def test_clicking_a_timeline_event_seeks_the_cameras(case: Case) -> None:
    """The defining interaction (spec §G): an event on the timeline moves every camera."""
    open_case("timeline")
    # The last event lane button; which event it is does not matter, only that the
    # cameras land where that event happened.
    js(
        "(() => { const b = [...document.querySelectorAll('button[aria-pressed]')]"
        ".filter(b => b.getAttribute('aria-label')?.includes(' at '));"
        " b[b.length - 1].click(); })()"
    )
    ref = selected_ref()
    assert ref in case.events, f"timeline selected {ref!r}, not an event"
    assert_seeked_to(case, ref)


def test_clicking_a_graph_node_seeks_the_cameras(case: Case) -> None:
    """An event node in the evidence graph navigates to its source moment."""
    open_case("evidence")
    timed = [n for n in case.nodes if case.time_of(n) is not None and n.split("/")[-1][0] == "V"]
    assert timed, "the graph has no event node with a time"
    node = timed[0]
    clicked = js(
        "(() => { const b = [...document.querySelectorAll('button[aria-pressed]')]"
        f".find(b => b.textContent.includes({json.dumps(case.nodes[node]['label'])}));"
        " if (!b) return false; b.click(); return true; })()"
    )
    assert clicked, f"no graph node labelled {case.nodes[node]['label']!r}"
    assert_seeked_to(case, selected_ref() or "")
