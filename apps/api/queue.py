"""Dispatch processing runs to the worker queue.

Best-effort by design. The run is the durable record; the queue message is only a
nudge to a worker. If Redis is unreachable the run is still created and still
QUEUED, and the response says it was not dispatched, so nothing is lost and nothing
is misreported. A sweeper that re-dispatches QUEUED runs is the natural next step if
that ever happens in practice.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.constants import default_queue_name, health_check_key_suffix

from apps.worker.settings import worker_settings

log = logging.getLogger(__name__)

_pool: ArqRedis | None = None


async def _get_pool() -> ArqRedis:
    """Create the Redis pool on first use and reuse it afterwards."""
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(worker_settings.redis_url))
    return _pool


async def enqueue_run(run_id: str, case_ref: str) -> bool:
    """Ask a worker to process a run. Returns whether the message was sent.

    The job id is the run id, so enqueueing the same run twice produces one job.
    That is the queue-level twin of the registry's idempotency: the same submission
    yields one run and one job, however many times it arrives.
    """
    try:
        pool = await _get_pool()
        job = await pool.enqueue_job("process_case", run_id, case_ref, _job_id=run_id)
    except Exception as exc:
        log.warning("run %s created but not dispatched: %s", run_id, exc)
        return False
    if job is None:
        # ARQ returns None when a job with this id already exists: the run was
        # already dispatched by an earlier, identical submission.
        log.info("run %s already queued", run_id)
        return True
    return True


#: Seconds a metrics request waits on Redis. The pool retries a refused connection for
#: several seconds, and a health screen that hangs while the queue is down is worse than
#: one that says the queue is unreachable.
QUEUE_TIMEOUT_S = 1.0


@dataclass(frozen=True)
class QueueStats:
    """What Redis says about the job queue and the worker that drains it."""

    depth: int
    oldest_age_s: float | None
    worker_last_seen_s: float | None
    worker_retries: int | None
    dead_letter_jobs: int | None


def read_heartbeat(line: str, ttl_ms: int, interval_s: int) -> tuple[float, int, int]:
    """Return age, retries and failures from an ARQ worker's health-check value.

    ARQ rewrites the key every ``interval_s`` with a TTL of one interval plus a second,
    so the key's age is how much of that TTL has run down. The counters are since the
    worker started; ``j_failed`` counts jobs that exhausted their retries, which is what
    a dead-letter count means for a queue with no separate dead-letter list.
    """
    counters = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)}
    age = max(0.0, interval_s + 1 - ttl_ms / 1000)
    return age, counters.get("j_retried", 0), counters.get("j_failed", 0)


async def queue_stats() -> QueueStats | None:
    """Read queue depth, the oldest job's age and the worker heartbeat.

    ``None`` when Redis cannot be reached in time: the queue's state is then unknown,
    which is different from an empty queue and must not be reported as one.
    """
    key = default_queue_name + health_check_key_suffix
    try:
        async with asyncio.timeout(QUEUE_TIMEOUT_S):
            pool = await _get_pool()
            depth = await pool.zcard(default_queue_name)
            oldest = await pool.zrange(default_queue_name, 0, 0, withscores=True)
            beat = await pool.get(key)
            ttl_ms = await pool.pttl(key)
    except Exception as exc:
        log.warning("queue metrics unavailable: %s", exc)
        return None
    # ARQ scores each job by the epoch millisecond at which it becomes runnable.
    oldest_age = max(0.0, time.time() - float(oldest[0][1]) / 1000) if oldest else None
    if beat is None or ttl_ms < 0:
        return QueueStats(int(depth), oldest_age, None, None, None)
    age, retries, failed = read_heartbeat(
        beat.decode(), int(ttl_ms), worker_settings.heartbeat_interval_s
    )
    return QueueStats(int(depth), oldest_age, age, retries, failed)
