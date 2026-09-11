/** Seconds on the run's shared timebase as `mm:ss.s`, the form the timeline uses. */
export function clock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = (seconds - m * 60).toFixed(1).padStart(4, "0");
  return `${String(m).padStart(2, "0")}:${s}`;
}
