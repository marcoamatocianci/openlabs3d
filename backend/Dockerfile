# Two images from one source tree:
#   web     FastAPI (Uvicorn). No Blender: it never renders, so it stays small and starts fast.
#   worker  the CAD worker (python -m app.cad_worker) with Blender for previews.
# compose.yaml builds both (target: web / target: worker).
FROM python:3.12-slim AS web
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app/backend
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --uid 10001 --create-home app && mkdir -p /app/data && chown app:app /app/data
COPY --chown=app:app . .
USER app
EXPOSE 8000
# Migrations run before the server accepts requests; the worker waits for this container to be healthy.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers --timeout-graceful-shutdown 20"]

FROM web AS worker
USER root
# Debian's Blender runs on the system Python 3, which needs its own numpy for studio_scene.py.
RUN apt-get update && apt-get install -y --no-install-recommends blender python3-numpy && rm -rf /var/lib/apt/lists/*
USER app
ENV BLENDER_BIN=blender CAD_WORKER_HEARTBEAT=/tmp/cad-worker-heartbeat
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os,sys,time; sys.exit(time.time()-os.path.getmtime(os.environ['CAD_WORKER_HEARTBEAT'])>900)"
CMD ["python", "-m", "app.cad_worker"]
