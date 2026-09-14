"""ARQ worker settings; run with ``python -m apps.worker``.

Retries are bounded. A job that fails three times is left for a person to look at,
because a run that fails deterministically will fail forever and retrying it burns
the queue for nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from arq.connections import RedisSettings

from apps.worker.settings import worker_settings
from apps.worker.tasks import process_case


class WorkerSettings:
    """Settings ARQ reads by attribute name."""

    functions: ClassVar[list[Callable[..., Any]]] = [process_case]
    redis_settings = RedisSettings.from_dsn(worker_settings.redis_url)
    max_jobs = 1
    job_timeout = 3600
    max_tries = 3
    health_check_interval = worker_settings.heartbeat_interval_s
