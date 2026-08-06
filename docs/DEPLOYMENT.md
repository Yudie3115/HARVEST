# Deployment Guide

Production deployment on a DigitalOcean droplet running Dokku.

**Read the order of these steps carefully.** The stateful services (PostgreSQL,
Qdrant, MinIO, Prefect) must exist *before* the first `git push`, because the API
applies database migrations on startup and will crashloop without a reachable
database. Provisioning is step 3; deploying is step 6.

---

## Architecture on the droplet

Two things run side by side on one droplet, and it is important to understand the
split:

| Managed by | What |
|---|---|
| **Dokku** | `postharvest-api` (FastAPI) and `postharvest-chat` (frontend) |
| **Docker Compose** | PostgreSQL, Qdrant, MinIO, Prefect server + worker |

This is deliberate — Dokku handles the stateless web apps and their TLS
certificates; Compose owns the stateful services and their volumes.

The consequence, and the single most common source of deployment failure:
**Dokku deploys one app per git remote and never reads `docker-compose.yml`.**
Pushing to `dokku-api` deploys the API alone. Nothing else in the compose file is
created implicitly. The two worlds only talk to each other because we explicitly
attach the Dokku apps to the Compose network in step 4.

---

## Prerequisites

- A DigitalOcean droplet (Ubuntu 22.04) — see [Droplet sizing](#droplet-sizing)
- A domain name with DNS you control
- SSH access to the droplet
- A Meta developer account (for WhatsApp — optional, deploy without it initially)

---

## 1. Install Dokku on the droplet

```bash
# On the droplet
wget -NP . https://dokku.com/install/v0.34.4/bootstrap.sh
sudo DOKKU_TAG=v0.34.4 bash bootstrap.sh

# Add your SSH public key
cat ~/.ssh/id_rsa.pub | ssh root@your-droplet-ip "sudo dokku ssh-keys:add admin"

# Set the global domain (replace with your domain)
dokku domains:set-global yourdomain.com
```

Install the Let's Encrypt plugin:

```bash
sudo dokku plugin:install https://github.com/dokku/dokku-letsencrypt.git
dokku letsencrypt:set --global email your@email.com
```

---

## 2. Create the two Dokku apps

```bash
# On the droplet
dokku apps:create postharvest-api
dokku apps:create postharvest-chat
```

### Point each app at its Dockerfile

This repo has **no `Dockerfile` at the root** — both live under `docker/`. Dokku
scans the repo root to choose a builder, finds no Dockerfile, and falls back to
buildpacks. It then sees both `requirements.txt` and `poetry.lock` and aborts:

```
!  Error: Multiple Python package manager files were found.
!  requirements.txt (pip)
!  poetry.lock (Poetry)
```

The fix is `builder-dockerfile:set`. Note that
`docker-options:add <app> build '--file ...'` does **not** work for this — those
options are passed to `docker build` only *after* Dokku has already chosen a
builder, so it never reaches the Dockerfile path:

```bash
dokku builder-dockerfile:set postharvest-api  dockerfile-path docker/api.Dockerfile
dokku builder-dockerfile:set postharvest-chat dockerfile-path docker/frontend.Dockerfile

# Optional but explicit — pins each app away from buildpack detection
dokku builder:set postharvest-api  selected dockerfile
dokku builder:set postharvest-chat selected dockerfile
```

`docker/api.Dockerfile` is multi-stage. Dokku builds the **last** stage and has no
`--target` option, which is why `api` is deliberately the final stage in that file.
Do not reorder the stages without accounting for this — Compose selects stages by
name and is unaffected, but Dokku is not.

The frontend needs its API URL baked in at build time (Vite env vars are
compile-time, not runtime):

```bash
dokku docker-options:add postharvest-chat build '--build-arg VITE_API_URL=https://api.yourdomain.com'
```

---

## 3. Provision the stateful services (before the first deploy)

```bash
# On the droplet
git clone <repo-url> /opt/postharvest
cd /opt/postharvest
cp .env.example .env        # fill in credentials

docker compose up -d postgres qdrant minio prefect-server
```

Confirm all four are healthy before continuing:

```bash
docker compose ps
```

### Prefect worker

The crawl worker is not managed by Dokku, but it **is** a Compose service — do not
run it by hand. `docker-compose.yml` builds it from the same
`docker/api.Dockerfile` (target `prefect-worker`), registers the flow deployments,
and then starts the worker:

```bash
docker compose up -d prefect-worker
```

This deliberately avoids installing Python, Poetry, or the project dependencies on
the droplet host. Nothing in this guide requires Poetry on the server — the image
already contains everything, and a host-level `poetry install` would pull the full
development dependency set (Scrapy, Playwright, Streamlit and more) that the
deployed services do not use.

For one-off commands, use the image rather than the host:

```bash
docker compose run --rm prefect-worker python -m scripts.catalogue_worker
docker compose exec postgres psql -U scraper -d postharvest_scraper
```

### Find the Compose network name

Compose prefixes its network with the project (directory) name. Cloned into
`/opt/postharvest`, the network defined as `scraper-network` becomes
`postharvest_scraper-network`. **Verify rather than assume** — you need this exact
string in the next step:

```bash
docker network ls | grep scraper
```

---

## 4. Connect the Dokku apps to the Compose network

This is the step that makes `postgres`, `qdrant` and `minio` resolvable from
inside the Dokku containers. Without it, every service hostname fails to resolve
and the API dies during startup migrations.

**Do step 3 first.** Attaching an app to a network that does not exist fails the
deploy before the container ever starts:

```
Error response from daemon: failed to set up container networking:
network <name> not found
```

Substitute the exact name printed by `docker network ls | grep scraper` in step 3.
It is derived from the directory you cloned into, so it differs between machines —
do not copy a name from this guide or from a colleague:

```bash
dokku network:set postharvest-api attach-post-create postharvest_scraper-network
```

### Do not use `docker-options` for this

`dokku docker-options:add <app> deploy '--network <name>'` looks equivalent and is
not. Docker attaches a container to exactly one network at creation, so `--network`
**replaces** Dokku's default bridge rather than adding to it. The result is an app
that looks completely healthy — it reaches `postgres` and `qdrant`, runs its
migrations, logs `API ready` — while nginx has no route to it, so every request
returns:

```
502 Bad Gateway
```

In a browser this usually surfaces as a misleading CORS error, because nginx's 502
page carries no `Access-Control-Allow-Origin` header:

```
Response to preflight request doesn't pass access control check:
No 'Access-Control-Allow-Origin' header is present on the requested resource
```

`network:set` attaches an *additional* interface, so the container keeps its
default-bridge address for nginx and gains one on the Compose network for the
backing services.

Use `attach-post-create`, not `attach-post-deploy`: post-create attaches the
network before the container starts, so DNS for `postgres` resolves in time for the
startup migrations. `attach-post-deploy` attaches afterwards and races with them.

If you already applied the `docker-options` form, remove it — it appends rather
than replaces, so it will keep overriding the network:

```bash
dokku docker-options:report postharvest-api
dokku docker-options:remove postharvest-api deploy '--network <name>'
dokku ps:restart postharvest-api
```

---

## 5. Configure environment variables

### Service endpoints — the most common mistake

Use **Compose service names**, never `localhost`. Inside a container, `localhost`
is that container itself, so `localhost:5433` reaches nothing and the API
crashloops with no traceback, dying silently a few seconds after logging
`Applying database migrations (alembic upgrade head)...`.

Note also that the port changes. `docker-compose.yml` publishes PostgreSQL on host
port **5433** to avoid colliding with a local PostgreSQL install, but on the
internal network you talk to the container's real port **5432**.

| Service | Wrong (host view) | Correct (container view) |
|---|---|---|
| PostgreSQL | `localhost:5433` | `postgres:5432` |
| Qdrant | `http://localhost:6333` | `http://qdrant:6333` |
| MinIO | `localhost:9000` | `minio:9000` |
| Prefect | `http://localhost:4200/api` | `http://prefect-server:4200/api` |

`prefect-server` is the Compose *service* name — not the container name
(`postharvest-prefect`). Service names are what the network resolves.

### API app

```bash
dokku config:set postharvest-api \
  DATABASE_URL=postgresql://scraper:ph_scraper_pass@postgres:5432/postharvest_scraper \
  QDRANT_URL=http://qdrant:6333 \
  MINIO_ENDPOINT=minio:9000 \
  PREFECT_API_URL=http://prefect-server:4200/api \
  VECTOR_DB_PROVIDER=qdrant \
  OPENAI_API_KEY=sk-... \
  SUNBIRD_API_KEY=... \
  API_CORS_ORIGINS='["https://chat.yourdomain.com"]' \
  ENVIRONMENT=production \
  LOG_LEVEL=INFO
```

Admin credentials are covered in [section 9](#9-admin-panel); WhatsApp variables
are optional and can be added later without a rebuild.

---

## 6. Add git remotes and deploy

On your local machine:

```bash
git remote add dokku-api  dokku@your-droplet-ip:postharvest-api
git remote add dokku-chat dokku@your-droplet-ip:postharvest-chat

git push dokku-api main
git push dokku-chat main
```

The API image is roughly **2.8 GB** and takes several minutes to build. Ensure the
droplet has headroom — Docker needs space for the new image while the old one is
still present.

Verify:

```bash
curl https://api.yourdomain.com/health
# {"status":"ok","version":"1.0.0"}
```

---

## 7. Database migrations

**No manual step is required.** The API runs `alembic upgrade head` automatically
on startup (`src/storage/migrations.py`, called from the lifespan handler in
`src/api/main.py`). A successful boot logs:

```
Applying database migrations (alembic upgrade head)...
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
Database schema is up to date
```

That middle line is the useful signal — it is the first thing that requires a live
database connection. If you see the first line but not the second, the container
cannot reach PostgreSQL.

> Earlier versions of this guide instructed you to run
> `dokku run postharvest-api poetry run python scripts/init_db.py`. That no longer
> applies: migrations are automatic, and Poetry is not installed in the image
> (it is built from `requirements.api.txt` with pip).

---

## 8. Domains and SSL

```bash
dokku domains:add postharvest-api  api.yourdomain.com
dokku domains:add postharvest-chat chat.yourdomain.com

# Run after the first successful deploy so the app is reachable for validation
dokku letsencrypt:enable postharvest-api
dokku letsencrypt:enable postharvest-chat
dokku letsencrypt:cron-job --add
```

DNS records at your registrar:

```
A  api.yourdomain.com   →  your-droplet-ip
A  chat.yourdomain.com  →  your-droplet-ip
```

---

## 9. Admin panel

The admin panel is part of the `postharvest-chat` frontend — no separate app or
container. It lives at `https://chat.yourdomain.com/admin`.

Generate real credentials. `ADMIN_JWT_SECRET` signs admin tokens and
`ADMIN_PASSWORD` is compared directly against the login form, so both must be
strong:

```bash
openssl rand -hex 32   # ADMIN_JWT_SECRET
openssl rand -base64 24  # ADMIN_PASSWORD
```

```bash
dokku config:set postharvest-api \
  ADMIN_USERNAME=admin \
  ADMIN_PASSWORD=<strong-password> \
  ADMIN_JWT_SECRET=<openssl rand -hex 32 output>

dokku ps:restart postharvest-api
```

> **No frontend rebuild needed.** `ADMIN_*` variables are backend-only; the
> frontend receives a JWT from the API at login.

### Rotating credentials

```bash
dokku config:set postharvest-api ADMIN_PASSWORD=<new-password>
dokku ps:restart postharvest-api
```

Active sessions stay valid until their 8-hour JWT expires. Rotating
`ADMIN_JWT_SECRET` invalidates all sessions immediately.

---

## 10. WhatsApp setup (Meta Cloud API)

### Create a Meta app

1. [developers.facebook.com](https://developers.facebook.com) → Create App → Business
2. Add the **WhatsApp** product
3. Under WhatsApp → API Setup, note your **Phone Number ID** and generate a **Permanent Token**
4. Set them in Dokku (no rebuild required — env vars are injected at container start):

```bash
dokku config:set postharvest-api \
  WHATSAPP_PHONE_NUMBER_ID=your-phone-number-id \
  WHATSAPP_TOKEN=your-permanent-token \
  WHATSAPP_VERIFY_TOKEN=your-chosen-verify-token \
  WHATSAPP_APP_SECRET=your-app-secret
```

### Register the webhook

Meta developer portal → WhatsApp → Configuration → Webhook:

- **Callback URL**: `https://api.yourdomain.com/webhook/whatsapp`
- **Verify token**: your `WHATSAPP_VERIFY_TOKEN`
- **Subscribed fields**: `messages`

Meta calls `GET /webhook/whatsapp` to confirm the token.

---

## Troubleshooting

### `Multiple Python package manager files were found`

Dokku fell back to buildpacks. `builder-dockerfile:set` was not applied — see
step 2. `docker-options:add ... build '--file ...'` does not fix this.

### Container restarts repeatedly, no traceback in the logs

The last line you see is `Applying database migrations...` and then the process
vanishes within a few seconds:

```
Healthcheck succeeded name='port listening check'
!  Failure in name='default': container has restarted 2 times
```

The API cannot reach PostgreSQL. In almost every case the endpoints are still set
to `localhost` — check `dokku config:show postharvest-api` against the table in
step 5, and confirm the app is attached to the Compose network (step 4).

A silent death with no Python traceback is the signature of a connection refused
during migrations, not of a crash inside the application.

### `ImportError: cannot import name 'command' from 'alembic'`

`alembic` is missing from `requirements.api.txt`, or `alembic.ini` and `alembic/`
were not copied into the image. Both are required by the startup migration and are
present in the current `docker/api.Dockerfile`.

### 502 Bad Gateway, or a CORS error, while the container is healthy

`dokku ps:report` shows `running`, `dokku ports:report` shows `http:80:8000`, and
the logs end with `All service clients initialised — API ready` — yet every request
returns 502, and the browser reports a missing `Access-Control-Allow-Origin` header.

The container is not on Dokku's default network. This is caused by attaching the
Compose network with `docker-options:add ... '--network ...'`, which replaces the
default bridge instead of adding to it. See step 4 — use `network:set
attach-post-create` and remove the `docker-options` entry.

The CORS message is a symptom, not the cause: nginx's own 502 page has no CORS
headers, so the browser blames CORS. `API_CORS_ORIGINS` is almost certainly fine.

### `network <name> not found` during deploy

The app is attached to a Docker network that does not exist on the host. Either the
Compose stack was never started (step 3), or the network name does not match — it
is prefixed with the directory the repo was cloned into, so it varies per machine.
Check with `docker network ls | grep scraper` and correct it per step 4, removing
the wrong value rather than adding alongside it.

### `dokku logs` says "App has not been deployed"

A failed deploy is rolled back, so there is no released container to read logs
from. Go to Docker directly using the container ID printed in the push output:

```bash
docker logs <container-id> 2>&1 | tail -50
```

### Build is very slow or times out downloading `torch`

`bert-score` depends on torch, and the default PyPI wheel bundles the entire CUDA
stack (~3.4 GB of `nvidia/` and `triton/`) which is useless on a CPU-only droplet.
`docker/api.Dockerfile` installs CPU-only torch first, from
`https://download.pytorch.org/whl/cpu`, which keeps the image at ~2.8 GB instead
of ~9.3 GB. If you see `Downloading nvidia_cublas...` in a build log, that line has
been removed or overridden and the CUDA build is being pulled again.

---

## Droplet sizing

Everything runs on a single droplet: two Dokku-managed containers plus four
Compose services and a Prefect worker.

| Service | Typical idle RAM |
|---|---|
| OS + system processes | ~400 MB |
| PostgreSQL 15 | ~350 MB |
| Qdrant | ~500 MB (grows with collection size) |
| MinIO | ~300 MB |
| Prefect server | ~500 MB |
| Prefect worker | ~400 MB |
| FastAPI API container | ~160 MB idle |
| nginx (frontend) | ~40 MB |
| **Total** | **~2.7 GB idle** |

During a crawl the Prefect worker climbs to ~600–800 MB, pushing peak usage to
~3.5 GB.

### Minimum viable

**2 vCPUs · 4 GB RAM · 80 GB SSD**

The smallest configuration that fits everything without constant swapping. Expect
it to feel tight — roughly 200–400 MB headroom at idle. Check `free -h` after your
first full crawl.

> Using **local embeddings** (`EMBEDDING_PROVIDER=local`) or **Ollama**
> (`LLM_PROVIDER=ollama`) instead of the OpenAI defaults adds at least 2 GB for the
> model — the minimum becomes **6 GB RAM**.

### Storage growth

| Item | Approximate size |
|---|---|
| OS + Docker images | ~12 GB (API image ~2.8 GB) |
| Qdrant vectors (per 10 k chunks) | ~60 MB |
| MinIO raw documents | budget 1 GB per ~500 PDFs |
| PostgreSQL metadata | < 1 GB for years of normal use |

Docker needs room for both the old and new image during a deploy, so keep at least
6 GB free. If the corpus grows into tens of thousands of documents, attach block
storage to MinIO before the disk fills.

---

## Ongoing operations

### Deploy an update

**The code lives in two places on the droplet, and a `git push` only updates one
of them.** Dokku builds its own image from the pushed commit; the Compose services
build from the clone at `/opt/postharvest`. Which you need depends on what changed:

| What changed | Push to Dokku | Update `/opt/postharvest` |
|---|---|---|
| API routes, frontend | Yes | No |
| `src/flows/`, `src/storage/`, `src/llm/` | Yes | **Yes** — the Prefect worker runs this code too |
| `docker/api.Dockerfile`, `requirements*.txt` | Yes | **Yes** — the worker shares the image |
| `docker-compose.yml`, service config | No | **Yes** |

Anything under `src/` that the crawl pipeline touches runs in *both* processes: the
API executes it for the admin reprocess action via background tasks, and the
Prefect worker executes it for scheduled crawls. Updating only one leaves the two
running different versions of the same code.

```bash
# Local machine — updates the Dokku apps
git push origin main
git push dokku-api main
git push dokku-chat main
```

```bash
# On the droplet — updates the Compose services
cd /opt/postharvest
git pull
docker compose up -d --build prefect-worker
```

Omit the `--build` and Compose reuses the old image, silently keeping the previous
code. Restarting the stateful services (`postgres`, `qdrant`, `minio`,
`prefect-server`) is not needed unless their configuration changed.

### Restart

```bash
dokku ps:restart postharvest-api
dokku ps:restart postharvest-chat
```

### Logs

```bash
dokku logs postharvest-api -t       # stream API logs
dokku logs postharvest-chat -t      # stream frontend logs
docker compose logs -f postgres     # DB logs (in /opt/postharvest)
```

### Database backup

```bash
docker exec postharvest-postgres pg_dump -U scraper postharvest_scraper \
  > backup-$(date +%Y%m%d).sql
```

Compose-managed PostgreSQL has no automated backups. Schedule the above via cron,
or migrate to the `dokku-postgres` plugin (below) for built-in backup tooling.

### Scale the API

```bash
dokku ps:scale postharvest-api web=2
```

---

## Alternative: dokku-postgres instead of Compose

If you would rather Dokku own the database — worthwhile for automated backups and
upgrade tooling:

```bash
sudo dokku plugin:install https://github.com/dokku/dokku-postgres.git postgres
dokku postgres:create postharvest-db
dokku postgres:link postharvest-db postharvest-api   # sets DATABASE_URL for you
```

`postgres:link` overwrites `DATABASE_URL` with a correct internal hostname, so
omit it from step 5. Qdrant and MinIO have no official plugins and still need
Compose or their own Dokku apps via `dokku git:from-image`.

Note that this starts from an **empty database**. Startup migrations build the
schema, but existing documents and chat history must be migrated separately.

---

## Environment variable reference

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | Use `postgres:5432`, not `localhost:5433` |
| `QDRANT_URL` | Yes | Use `http://qdrant:6333` |
| `MINIO_ENDPOINT` | Yes | Use `minio:9000` |
| `PREFECT_API_URL` | No | Use `http://prefect-server:4200/api` |
| `VECTOR_DB_PROVIDER` | No | `qdrant` (default) or `chroma` |
| `OPENAI_API_KEY` | Yes | LLM and embeddings |
| `API_CORS_ORIGINS` | Yes | JSON array, e.g. `["https://chat.yourdomain.com"]` |
| `ADMIN_USERNAME` | Yes | Admin panel login |
| `ADMIN_PASSWORD` | Yes | Compared directly — use a strong value |
| `ADMIN_JWT_SECRET` | Yes | Signs admin tokens — `openssl rand -hex 32` |
| `SUNBIRD_API_KEY` | No | Translation — disabled if empty |
| `EMBEDDING_PROVIDER` | No | `openai` (default) or `local` (needs +2 GB RAM) |
| `LLM_PROVIDER` | No | `openai` (default) or `ollama` |
| `BERTSCORE_ENABLED` | No | Answer scoring; `BERTSCORE_MODEL` selects the model |
| `CRAWL_UNVERIFY_SSL` | No | Comma-separated site names to skip TLS verification — set it in the Compose `.env`, see below |
| `WHATSAPP_TOKEN` | No | Webhook inactive if empty |
| `WHATSAPP_PHONE_NUMBER_ID` | No | WhatsApp |
| `WHATSAPP_VERIFY_TOKEN` | No | Any string you choose |
| `WHATSAPP_APP_SECRET` | Strongly recommended | Webhook signature verification |
| `ENVIRONMENT` | No | `development` or `production` |
| `LOG_LEVEL` | No | `INFO` (default) |
| `VITE_API_URL` | Yes (build arg) | Frontend only — set via `docker-options:add` at build time |

Defaults in `src/config/settings.py` are **local development values**
(`localhost:...`). They are correct for `make local` and wrong for every
containerised deployment, which is why each endpoint must be set explicitly above.

### Two environments, not one

`dokku config:set` configures the **API and frontend containers only**. The Prefect
worker — which runs every crawl — reads `/opt/postharvest/.env` through Compose's
`env_file`. The two are unrelated, and a setting present in one is invisible to the
other.

Anything the crawl pipeline reads must be in the Compose `.env`:

| Variable | Needed by | Symptom if only set in Dokku |
|---|---|---|
| `ENVIRONMENT` | worker (deployment names) | `{"detail":"Deployment not found"}` — the worker registers `*-development` while the API asks for `*-production` |
| `CRAWL_UNVERIFY_SSL` | worker (crawl HTTP client) | A site with an incomplete certificate chain fails with `CERTIFICATE_VERIFY_FAILED` even though the setting appears in `dokku config:show` |
| `OPENAI_API_KEY`, `DATABASE_URL`, `QDRANT_URL`, `MINIO_ENDPOINT` | both | Crawls fail while the API works normally |

After editing `/opt/postharvest/.env`:

```bash
docker compose up -d --force-recreate prefect-worker
```

Compose does not always recreate a container for an `env_file` change alone, so
`--force-recreate` is what actually applies it.

> **On `CRAWL_UNVERIFY_SSL`:** some source sites serve an incomplete certificate
> chain — the leaf without its intermediate CA. Browsers paper over this by
> fetching the missing intermediate via the certificate's AIA extension; Python
> HTTP clients do not, so the site loads fine in a browser and fails for the
> crawler. `www.ubos.org` is one such site. Listing a site here disables
> certificate verification for it entirely, which also removes protection against
> interception — acceptable for public documents, but do not add hosts casually.
