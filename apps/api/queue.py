"""Dispatch processing runs to the worker queue.

Best-effort by design. The run is the durable record; the queue message is only a
nudge to a worker. If Redis is unreachable the run is still created and still
QUEUED, and the response says it was not dispatched, so nothing is lost and nothing
is misreported. A sweeper that re-dispatches QUEUED runs is the natural next step if
that ever happens in practice.
"""

from __future__ import annotations

import logging

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

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
