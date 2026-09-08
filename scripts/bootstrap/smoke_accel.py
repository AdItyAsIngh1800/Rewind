"""PS-2 accelerator smoke test.

Measures the real operating envelope of this machine before any ML decision is made
around it. Prints a markdown table suitable for pasting into docs/09-deployment.md.

Run:  uv run python scripts/bootstrap/smoke_accel.py
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import time

RESOLUTIONS = [(1280, 720)]
BATCHES = [1, 2, 4, 8]


def host_facts() -> dict[str, str]:
    def sysctl(key: str) -> str:
        try:
            return subprocess.check_output(["sysctl", "-n", key], text=True).strip()
        except Exception:
            return "unknown"

    mem = sysctl("hw.memsize")
    return {
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "chip": sysctl("machdep.cpu.brand_string"),
        "cores": sysctl("hw.ncpu"),
        "unified_memory_gb": f"{int(mem) / 1024**3:.0f}" if mem.isdigit() else "unknown",
    }


def torch_facts() -> tuple[object | None, dict[str, str]]:
    try:
        import torch
    except ImportError:
        return None, {"torch": "NOT INSTALLED — run `make dev`"}

    facts = {"torch": torch.__version__, "mps_available": str(torch.backends.mps.is_available())}
    if torch.backends.mps.is_available():
        # recommended_max_memory is the working-set ceiling Metal will honour before
        # it starts paging to disk. On unified memory this is the number that matters,
        # not a fixed VRAM figure.
        try:
            facts["mps_recommended_max_gb"] = f"{torch.mps.recommended_max_memory() / 1024**3:.1f}"
        except Exception:
            facts["mps_recommended_max_gb"] = "unavailable on this torch build"
    return torch, facts


def pick_device(torch) -> str:  # type: ignore[no-untyped-def]
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def mps_driver_gb(torch) -> float:  # type: ignore[no-untyped-def]
    """Total memory Metal has taken from the unified pool.

    `current_allocated_memory` only counts live tensors and reads ~0 between
    inference calls, which is useless for capacity planning. The driver figure is
    what actually competes with the OS, Docker and the browser for the 16 GB.
    """
    try:
        return float(torch.mps.driver_allocated_memory()) / 1024**3
    except Exception:
        return float("nan")


def bench_detector(torch, device: str, model_name: str) -> list[dict[str, object]]:  # type: ignore[no-untyped-def]
    """Benchmark the real workload: a compact detector over 720p frames."""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("! ultralytics not installed — skipping detector benchmark.")
        print("  Install with: uv sync --extra ml")
        return []

    model = YOLO(model_name)
    rows: list[dict[str, object]] = []

    for w, h in RESOLUTIONS:
        for batch in BATCHES:
            frames = [torch.randint(0, 255, (h, w, 3), dtype=torch.uint8).numpy() for _ in range(batch)]

            model.predict(frames, device=device, verbose=False)  # warm up
            if device == "mps":
                torch.mps.synchronize()
                torch.mps.empty_cache()

            t0 = time.perf_counter()
            reps = 5
            peak = 0.0
            for _ in range(reps):
                model.predict(frames, device=device, verbose=False)
                if device == "mps":
                    peak = max(peak, mps_driver_gb(torch))
            if device == "mps":
                torch.mps.synchronize()
            elapsed = time.perf_counter() - t0

            rows.append(
                {
                    "resolution": f"{w}x{h}",
                    "batch": batch,
                    "ms_per_frame": round(elapsed / (reps * batch) * 1000, 1),
                    "fps": round(reps * batch / elapsed, 1),
                    "driver_peak_gb": round(peak, 2),
                }
            )
            print(f"  {w}x{h} batch={batch}: {rows[-1]['fps']} FPS, {rows[-1]['ms_per_frame']} ms/frame")

    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="yolo11n.pt", help="detector checkpoint to benchmark")
    args = ap.parse_args()

    print("REWIND — accelerator smoke test\n")

    facts = host_facts()
    torch, tfacts = torch_facts()
    facts.update(tfacts)

    print("## Host\n")
    for k, v in facts.items():
        print(f"| {k} | {v} |")

    if torch is None:
        print("\nCannot benchmark without torch. Run `make dev` first.")
        return 1

    device = pick_device(torch)
    print(f"\n## Benchmark (device={device})\n")
    rows = bench_detector(torch, device, args.model)

    if rows:
        print("\n| Resolution | Batch | ms/frame | FPS | Driver peak (GB) |")
        print("|---|---|---|---|---|")
        for r in rows:
            print(
                f"| {r['resolution']} | {r['batch']} | {r['ms_per_frame']} | "
                f"{r['fps']} | {r['driver_peak_gb']} |"
            )
        print("\nPaste this table into docs/09-deployment.md and record the date.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
