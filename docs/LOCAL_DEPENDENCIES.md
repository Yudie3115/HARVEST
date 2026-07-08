# Local External Dependencies

Use this guide when you want to run the app with `make dev-local` or
`make local` without starting the project Docker Compose stack. The app still
needs PostgreSQL, Qdrant, and MinIO reachable from your machine.

## Expected Local Configuration

Set these values in `.env` unless your local services use different ports or
credentials:

```dotenv
DATABASE_URL=postgresql://scraper:ph_scraper_pass@localhost:5432/postharvest_scraper
QDRANT_URL=http://localhost:6333
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=postharvest-documents
MINIO_SECURE=false
```

After the services are running, verify them with:

```bash
make check-local-services
```

## PostgreSQL

Install PostgreSQL 15 or newer using your OS package manager.
Use the normal local PostgreSQL port, `5432`; the Docker Compose stack uses
host port `5433` only to avoid colliding with this local service.

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl enable --now postgresql
sudo -u postgres psql -c "CREATE USER scraper WITH PASSWORD 'ph_scraper_pass';"
sudo -u postgres createdb -O scraper postharvest_scraper
```

macOS with Homebrew:

```bash
brew install postgresql@15
brew services start postgresql@15
createuser scraper
createdb -O scraper postharvest_scraper
psql postgres -c "ALTER USER scraper WITH PASSWORD 'ph_scraper_pass';"
```

Then initialize the app schema:

```bash
make init-db
```

## Qdrant

Install Qdrant from your package manager if available, or download a release
archive from the official Qdrant releases page. Store data outside the repo if
you want to keep the checkout small:

```bash
mkdir -p ~/.local/share/postharvest/qdrant
cd ~/.local/share/postharvest/qdrant
qdrant
```

Verify:

```bash
curl http://localhost:6333/collections
```

The app uses `QDRANT_COLLECTION=postharvest_knowledge`; the collection is
created by the ingestion/vector storage code when documents are indexed.

## MinIO

Install the MinIO server binary and the `mc` client from the official MinIO
downloads. On Linux, a typical install looks like this:

```bash
mkdir -p ~/.local/bin
curl -L https://dl.min.io/server/minio/release/linux-amd64/minio -o ~/.local/bin/minio
curl -L https://dl.min.io/client/mc/release/linux-amd64/mc -o ~/.local/bin/mc
chmod +x ~/.local/bin/minio ~/.local/bin/mc
```

Start MinIO with the credentials used by `.env`:

```bash
mkdir -p ~/.local/share/postharvest/minio
export MINIO_ROOT_USER=minioadmin
export MINIO_ROOT_PASSWORD=minioadmin123
minio server ~/.local/share/postharvest/minio --console-address ":9001"
```

In another terminal, create the bucket:

```bash
mc alias set local http://localhost:9000 minioadmin minioadmin123
mc mb --ignore-existing local/postharvest-documents
```

Verify:

```bash
curl http://localhost:9000/minio/health/live
```

The MinIO console is available at `http://localhost:9001`.

## Run The App

Once all checks pass:

```bash
make dev-local
```

For later runs, use:

```bash
make local
```

## References

- Qdrant local quickstart: https://qdrant.tech/documentation/quickstart/
- MinIO documentation: https://docs.min.io/
- PostgreSQL downloads: https://www.postgresql.org/download/
