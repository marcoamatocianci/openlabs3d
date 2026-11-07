# Two images from one source tree:
#   web     FastAPI (Uvicorn). No Blender or CAD libraries: it never renders, so it stays small and starts fast.
#   worker  the CAD worker (python -m app.cad_worker) with Blender for previews and CadQuery for custom racks.
# compose.yaml builds both (target: web / target: worker). Source is copied last, so a code change rebuilds in seconds and never
# re-downloads Blender or CadQuery.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app/backend
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --uid 10001 --create-home app && mkdir -p /app/data && chown app:app /app/data

FROM base AS web
COPY --chown=app:app . .
USER app
EXPOSE 8000
# Migrations run before the server accepts requests; the worker waits for this container to be healthy.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers --timeout-graceful-shutdown 20"]

FROM base AS worker-libraries
# Debian's Blender runs on the system Python 3, which needs its own numpy for studio_scene.py.
RUN apt-get update && apt-get install -y --no-install-recommends blender python3-numpy && rm -rf /var/lib/apt/lists/*
COPY requirements-cad.txt .
# requirements-cad.txt lists what CadQuery really needs. casadi is imported by CadQuery but only its Sketch solver uses it, which
# racks do not: its solver plugins and headers are 250 MB nothing loads. One layer, so what is removed really leaves the image.
RUN pip install --no-cache-dir --no-deps -r requirements-cad.txt \
 && cd "$(python -c 'import os,casadi;print(os.path.dirname(casadi.__file__))')" \
 && rm -rf include cmake pkgconfig libcasadi_*.so* libhighs* liblacemodelica* libcoinmumps* libipopt* libbonmin* libsnopt* libqpOASES* libCbc* libOsi* libClp* libCgl* libCoin* libsuperscs* libblasfeo* libhpipm* libsleqp* libfatrop* libdaqp* libalpaqa* libtinyxml* libosqp* libqdldl*

FROM worker-libraries AS worker
COPY --chown=app:app . .
USER app
# Real racks of both styles: an image whose CAD libraries were pruned too far fails here, not for the first buyer.
RUN python -W ignore -m app.rack.smoke
ENV BLENDER_BIN=blender CAD_WORKER_HEARTBEAT=/tmp/cad-worker-heartbeat
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os,sys,time; sys.exit(time.time()-os.path.getmtime(os.environ['CAD_WORKER_HEARTBEAT'])>900)"
CMD ["python", "-m", "app.cad_worker"]
