/** Seconds on the run's shared timebase as `mm:ss.s`, the form the timeline uses. */
export function clock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = (seconds - m * 60).toFixed(1).padStart(4, "0");
  return `${String(m).padStart(2, "0")}:${s}`;
}

/** A wall-clock span as `42.1 s` or `3 m 05 s`. */
export function duration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const m = Math.floor(seconds / 60);
  return `${m} m ${String(Math.floor(seconds - m * 60)).padStart(2, "0")} s`;
}
