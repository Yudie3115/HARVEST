FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only torch first, from PyTorch's CPU index. bert-score pulls in
# torch, and the default PyPI wheel bundles the full CUDA stack (~3.4GB of
# nvidia/ + triton/) which is dead weight on a CPU-only host. Installing it
# up front means the requirements below find torch already satisfied.
# Kept above the COPY so a requirements change doesn't re-download it.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.api.txt ./
RUN pip install --no-cache-dir -r requirements.api.txt

COPY requirements.ingestion.txt ./
RUN pip install --no-cache-dir -r requirements.ingestion.txt

COPY src/ ./src/
COPY scripts/ ./scripts/

# The API applies pending migrations on startup (src/storage/migrations.py),
# which resolves alembic.ini and alembic/ relative to the repo root.
COPY alembic.ini ./
COPY alembic/ ./alembic/

EXPOSE 8000

FROM runtime AS prefect-worker

COPY requirements.orchestration.txt ./
RUN pip install --no-cache-dir -r requirements.orchestration.txt

CMD ["prefect", "worker", "start", "--pool", "postharvest-pool"]

# Keep `api` last: Dokku builds the final stage, so a plain `docker build`
# of this file produces the API image. docker-compose selects stages by name.
FROM runtime AS api

# Shell form so ${PORT} expands (Dokku injects it); `exec` so uvicorn becomes
# PID 1 and receives SIGTERM directly instead of it stopping at /bin/sh.
CMD exec uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
