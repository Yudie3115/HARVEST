"""
Check that local infrastructure services are reachable before starting the app.
"""
from __future__ import annotations

import socket
import sys
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.config.settings import settings


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def check_tcp(name: str, host: str, port: int, timeout: float = 2.0) -> CheckResult:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return CheckResult(name, True, f"{host}:{port}")
    except OSError as exc:
        return CheckResult(name, False, f"{host}:{port} is not reachable ({exc})")


def check_http(name: str, url: str, timeout: float = 3.0) -> CheckResult:
    try:
        request = Request(url, headers={"User-Agent": "postharvest-local-check/1.0"})
        with urlopen(request, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return CheckResult(name, True, url)
            return CheckResult(name, False, f"{url} returned HTTP {response.status}")
    except Exception as exc:
        return CheckResult(name, False, f"{url} is not reachable ({exc})")


def database_host_port() -> tuple[str, int]:
    parsed = urlparse(str(settings.database_url))
    return parsed.hostname or "localhost", parsed.port or 5432


def minio_health_url() -> str:
    scheme = "https" if settings.minio_secure else "http"
    return f"{scheme}://{settings.minio_endpoint}/minio/health/live"


def qdrant_collections_url() -> str:
    return f"{settings.qdrant_url.rstrip('/')}/collections"


def main() -> int:
    db_host, db_port = database_host_port()
    results = [
        check_tcp("PostgreSQL", db_host, db_port),
        check_http("MinIO", minio_health_url()),
    ]
    if settings.vector_db_provider == "qdrant":
        results.insert(1, check_http("Qdrant", qdrant_collections_url()))
    else:
        results.insert(
            1,
            CheckResult(
                "ChromaDB",
                True,
                f"persistent local store at {settings.chroma_path}",
            ),
        )

    print("Checking local services...")
    for result in results:
        prefix = "ok" if result.ok else "missing"
        print(f"  {prefix:7} {result.name}: {result.detail}")

    if all(result.ok for result in results):
        return 0

    print(
        "\nStart these services locally, update .env to point at them, "
        "or use `make start` for the Docker-backed stack."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
