import { useEffect, useRef, useState } from "react";
import { Pause, Play, StepBack, StepForward } from "lucide-react";
import type { Replay } from "@/api/types";
import { Button } from "@/components/ui/button";
import { clock } from "@/lib/format";

interface Props {
  replay: Replay;
  /** Shared-timebase seconds to seek to when `seekKey` changes; `null` leaves the playhead. */
  seekTo: number | null;
  seekKey: string | null;
}

const RATES = [0.25, 0.5, 1, 2];

/** A clip time kept inside the clip; before metadata loads the duration is unknown. */
function within(video: HTMLVideoElement, t: number): number {
  return Math.min(Math.max(t, 0), Number.isFinite(video.duration) ? video.duration : t);
}

/**
 * Three camera panes on one shared clock.
 *
 * One pane leads. Its presented frames, read with `requestVideoFrameCallback`, set the
 * shared time, and each other pane is corrected toward that time plus its own offset
 * whenever it drifts by more than a frame. Correcting only past a frame keeps playback
 * smooth; seeking every pane on every frame would stutter all three. Paused, a seek
 * sets every pane directly.
 *
 * Clip time is shared time plus the camera's clock offset: ingestion subtracted the
 * offset to reach the shared clock, so the player adds it back.
 */
export function ReplayPanel({ replay, seekTo, seekKey }: Props) {
  const panes = replay.cameras;
  const videos = useRef<(HTMLVideoElement | null)[]>([]);
  const [time, setTime] = useState(replay.window_start_s);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(1);
  const [end, setEnd] = useState(replay.window_end_s);
  const [failed, setFailed] = useState<Record<string, boolean>>({});
  const lead = panes.findIndex((p) => p.media_url !== null && !failed[p.camera_id]);
  const frame = 1 / (panes[lead]?.fps ?? 10);

  function seek(shared: number) {
    const t = Math.min(Math.max(shared, 0), end);
    panes.forEach((p, i) => {
      const v = videos.current[i];
      if (v) v.currentTime = within(v, t + p.clock_offset_s);
    });
    setTime(t);
  }

  function toggle() {
    const leader = videos.current[lead];
    if (!leader) return;
    if (playing) {
      videos.current.forEach((v) => v?.pause());
      // Re-align every pane on the frame the leader stopped at.
      seek(leader.currentTime - (panes[lead]?.clock_offset_s ?? 0));
      setPlaying(false);
    } else {
      videos.current.forEach((v) => void v?.play().catch(() => setPlaying(false)));
      setPlaying(true);
    }
  }

  useEffect(() => {
    const leader = videos.current[lead];
    const offset = panes[lead]?.clock_offset_s ?? 0;
    if (!leader) return;
    let handle = 0;
    const onFrame: VideoFrameRequestCallback = (_now, meta) => {
      const shared = meta.mediaTime - offset;
      setTime(shared);
      if (!leader.paused) {
        panes.forEach((p, i) => {
          const v = videos.current[i];
          if (i === lead || !v) return;
          const target = shared + p.clock_offset_s;
          if (Math.abs(v.currentTime - target) > frame) v.currentTime = within(v, target);
        });
      }
      handle = leader.requestVideoFrameCallback(onFrame);
    };
    handle = leader.requestVideoFrameCallback(onFrame);
    return () => leader.cancelVideoFrameCallback(handle);
  }, [lead, panes, frame]);

  useEffect(() => {
    videos.current.forEach((v) => {
      if (v) v.playbackRate = rate;
    });
  }, [rate]);

  // A selection anywhere on the case page moves every camera to its moment.
  useEffect(() => {
    if (seekTo !== null) seek(seekTo);
    // `seek` reads the latest state on each call; re-running on its identity would seek every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seekKey, seekTo]);

  const pct = (t: number) => `${(Math.min(Math.max(t / (end || 1), 0), 1) * 100).toFixed(3)}%`;
  const step = (frames: number) => seek(time + frames * frame);

  return (
    <section aria-labelledby="replay" className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="replay" className="text-sm font-medium">
          Synchronized replay
        </h2>
        <p className="tabular text-xs text-text-muted">
          {clock(time)} · window {clock(replay.window_start_s)}–{clock(replay.window_end_s)} · detected{" "}
          {clock(replay.detected_at_s)}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {panes.map((p, i) => (
          <figure key={p.camera_id} className="flex min-w-0 flex-col gap-1">
            <div className="aspect-video max-w-full overflow-hidden rounded-md bg-ground">
              {p.media_url && !failed[p.camera_id] ? (
                <video
                  ref={(el) => {
                    videos.current[i] = el;
                  }}
                  src={p.media_url}
                  muted
                  playsInline
                  preload="auto"
                  aria-label={`${p.name} footage`}
                  className="size-full object-contain"
                  onLoadedMetadata={(e) => {
                    const v = e.currentTarget;
                    v.playbackRate = rate;
                    v.currentTime = within(v, time + p.clock_offset_s);
                    setEnd((current) => Math.max(current, v.duration - p.clock_offset_s));
                  }}
                  onEnded={i === lead ? () => setPlaying(false) : undefined}
                  onError={() => setFailed((f) => ({ ...f, [p.camera_id]: true }))}
                />
              ) : (
                <p className="flex size-full items-center justify-center p-3 text-center text-xs text-text-muted">
                  {p.media_url ? "Footage could not be loaded" : "No footage recorded for this run; reprocess it to replay"}
                </p>
              )}
            </div>
            <figcaption className="flex justify-between gap-2 text-xs text-text-muted">
              <span className="font-mono">{p.camera_id}</span>
              {p.clock_offset_s !== 0 && <span className="tabular">offset {p.clock_offset_s.toFixed(2)} s</span>}
            </figcaption>
          </figure>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={toggle} disabled={lead < 0} aria-label={playing ? "Pause" : "Play"}>
          {playing ? <Pause aria-hidden /> : <Play aria-hidden />}
        </Button>
        <Button variant="outline" size="sm" onClick={() => step(-1)} disabled={lead < 0 || playing} aria-label="Back one frame">
          <StepBack aria-hidden />
        </Button>
        <Button variant="outline" size="sm" onClick={() => step(1)} disabled={lead < 0 || playing} aria-label="Forward one frame">
          <StepForward aria-hidden />
        </Button>
        <div className="relative flex h-8 min-w-40 flex-1 items-center">
          {/* The rewind window as a band and the detection as a tick, behind the scrubber. */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-2 rounded-sm bg-surface-raised"
            style={{ left: pct(replay.window_start_s), width: `calc(${pct(replay.window_end_s)} - ${pct(replay.window_start_s)})` }}
          />
          <div aria-hidden className="pointer-events-none absolute inset-y-1 w-px bg-text/60" style={{ left: pct(replay.detected_at_s) }} />
          <input
            type="range"
            min={0}
            max={end}
            step={frame}
            value={time}
            disabled={lead < 0}
            onChange={(e) => seek(Number(e.target.value))}
            aria-label="Shared time"
            aria-valuetext={clock(time)}
            className="relative w-full accent-text"
          />
        </div>
        <label className="flex items-center gap-1 text-xs text-text-muted">
          Speed
          <select
            value={rate}
            onChange={(e) => setRate(Number(e.target.value))}
            className="h-8 rounded-md border border-border bg-surface px-2 text-sm text-text"
          >
            {RATES.map((r) => (
              <option key={r} value={r}>
                {r}×
              </option>
            ))}
          </select>
        </label>
        <Button variant="ghost" size="sm" onClick={() => seek(replay.detected_at_s)} disabled={lead < 0}>
          Go to detection
        </Button>
      </div>
    </section>
  );
}
