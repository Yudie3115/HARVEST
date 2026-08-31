# Local External Dependencies

Use this guide when you want to run the app with `make dev-local` or
`make local` without starting the project Docker Compose stack. The app still
needs PostgreSQL and MinIO reachable from your machine. ChromaDB runs embedded
in the Python process by default for this workflow.

## Expected Local Configuration

Set these values in `.env` unless your local services use different ports or
credentials:

```dotenv
DATABASE_URL=postgresql://scraper:ph_scraper_pass@localhost:5432/postharvest_scraper
VECTOR_DB_PROVIDER=chroma
CHROMA_PATH=./data/chroma
CHROMA_COLLECTION=postharvest_knowledge
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

## Vector Database

### ChromaDB (default for local app development)

No separate ChromaDB service is required. The app uses the `chromadb` Python
package and persists vectors to `CHROMA_PATH`.

```dotenv
VECTOR_DB_PROVIDER=chroma
CHROMA_PATH=./data/chroma
CHROMA_COLLECTION=postharvest_knowledge
```

The collection is created by the ingestion/vector storage code when documents
are indexed.

### Qdrant (optional local alternative)

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

Then set:

```dotenv
VECTOR_DB_PROVIDER=qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=postharvest_knowledge
```

## MinIO

Install the MinIO server binary and the `mc` client from the official MinIO
downloads. On Linux, a typical install looks like this:

```bash
mkdir -p ~/.local/bin
curl -L https://dl.min.io/server/minio/release/linux-amd64/minio -o ~/.local/bin/minio
curl -L https://dl.min.io/client/mc/release/linux-amd64/mc -o ~/.local/bin/mc
chmod +x ~/.local/bin/minio ~/.local/bin/mc
```

### Run it once, on demand

```bash
mkdir -p ~/.local/share/postharvest/minio
export MINIO_ROOT_USER=minioadmin
export MINIO_ROOT_PASSWORD=minioadmin123
minio server ~/.local/share/postharvest/minio --console-address ":9001"
```

### Run it as a systemd user service (recommended — no re-exporting credentials, autostarts)

On distros with systemd (including WSL2 with `systemd=true` in `/etc/wsl.conf`),
run MinIO and the local Prefect server as `systemd --user` services so they
start automatically and the root credentials never need to be typed again.

Store the credentials once in an env file (not committed, not in your shell
history):

```bash
mkdir -p ~/.config/postharvest
cat > ~/.config/postharvest/minio.env <<'EOF'
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
EOF
chmod 600 ~/.config/postharvest/minio.env
```

Create `~/.config/systemd/user/postharvest-minio.service`:

```ini
[Unit]
Description=MinIO object storage (Post-Harvest Knowledge Scraper - local dev)
After=network.target

[Service]
Type=simple
EnvironmentFile=%h/.config/postharvest/minio.env
ExecStart=%h/.local/bin/minio server %h/.local/share/postharvest/minio --console-address :9001
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

And `~/.config/systemd/user/postharvest-prefect.service` (adjust the paths to
your checkout and venv):

```ini
[Unit]
Description=Prefect server (Post-Harvest Knowledge Scraper - local dev)
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/post-harvest-knowledge-scraper
ExecStart=/path/to/post-harvest-knowledge-scraper/.venv/bin/prefect server start --host 127.0.0.1 --port 4200
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

Enable both, and enable lingering so they also start on boot/WSL start even
before you log in interactively:

```bash
systemctl --user daemon-reload
systemctl --user enable --now postharvest-minio.service postharvest-prefect.service
sudo loginctl enable-linger "$USER"
```

If `enable-linger` fails with `Could not enable linger: No such device or
address` (a known WSL2 systemd-logind quirk), just retry the same command —
it typically succeeds on the second attempt.

Check status/logs the normal systemd way:

```bash
systemctl --user status postharvest-minio.service postharvest-prefect.service
journalctl --user -u postharvest-minio.service -f
```

In another terminal, create the bucket (only needed once):

```bash
mc alias set local http://localhost:9000 minioadmin minioadmin123
mc mb --ignore-existing local/postharvest-documents
```

Verify:

```bash
curl http://localhost:9000/minio/health/live
curl http://127.0.0.1:4200/api/health
```

The MinIO console is available at `http://localhost:9001`. The Prefect UI is
available at `http://localhost:4200`.

Ollama (if installed via its official Linux installer) and PostgreSQL
(installed via `apt`/`brew` above) already register their own system-level
systemd/launchd services and autostart — no extra setup needed for those two.
ChromaDB needs no service; it runs embedded in the API process and persists to
`CHROMA_PATH`.

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

- ChromaDB documentation: https://docs.trychroma.com/
- Qdrant local quickstart: https://qdrant.tech/documentation/quickstart/
- MinIO documentation: https://docs.min.io/
- PostgreSQL downloads: https://www.postgresql.org/download/
