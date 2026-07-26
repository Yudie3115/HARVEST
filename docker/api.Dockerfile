FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.api.txt ./
RUN pip install --no-cache-dir -r requirements.api.txt

COPY requirements.ingestion.txt ./
RUN pip install --no-cache-dir -r requirements.ingestion.txt

COPY src/ ./src/
COPY scripts/ ./scripts/

EXPOSE 8000

FROM runtime AS api

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS prefect-worker

COPY requirements.orchestration.txt ./
RUN pip install --no-cache-dir -r requirements.orchestration.txt

CMD ["prefect", "worker", "start", "--pool", "postharvest-pool"]
