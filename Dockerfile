# REWIND application image: the API, the worker and the migration step share it.
#
# CPU-only torch. The lockfile resolves CUDA wheels on Linux (gigabytes, and no GPU
# inside Docker on Apple silicon anyway), so the locked set is installed without them
# and the matching CPU wheels are added. Every other version is the lockfile's.
# Measured in Docker on an M4 (10 cores, 7.7 GB to the VM): 15.6 FPS, a 45 s three-camera
# case in 87 s. The same CPU wheel path on the macOS host runs at 63 FPS (EXP-0012).

FROM python:3.12-slim-bookworm

# ffprobe reads clip metadata during ingestion.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /bin/uv

WORKDIR /app
ENV VIRTUAL_ENV=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1

COPY pyproject.toml uv.lock ./
# No uv cache in the layer: it would hold a second copy of every wheel (1.7 GB).
RUN uv venv \
    && uv export --frozen --extra ml --no-dev --no-hashes --no-emit-project -o /tmp/locked.txt \
    && grep -vE '^(torch==|torchvision==|triton==|cuda-|nvidia-c|nvidia-n)' /tmp/locked.txt > /tmp/cpu.txt \
    && uv pip install --no-deps -r /tmp/cpu.txt \
    && uv pip install --no-deps --index-url https://download.pytorch.org/whl/cpu \
        torch==2.14.0+cpu torchvision==0.29.0+cpu \
    && rm /tmp/locked.txt /tmp/cpu.txt

COPY alembic.ini ./
COPY apps ./apps
COPY packages ./packages
COPY services ./services
COPY ml/configs ./ml/configs

# Ultralytics writes its settings under the home directory.
RUN useradd --create-home rewind
USER rewind

EXPOSE 8000
CMD ["python", "-m", "apps.api"]
