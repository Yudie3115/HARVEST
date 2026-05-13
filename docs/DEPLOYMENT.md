# Deployment Guide

Production deployment on a DigitalOcean droplet running Dokku.

---

## Prerequisites

- A DigitalOcean droplet (Ubuntu 22.04, 4 GB RAM minimum recommended)
- A domain name with DNS you control
- A Meta developer account (for WhatsApp — optional, can deploy without it initially)
- SSH access to the droplet

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

Point each app at its Dockerfile (both live in the same repo):

```bash
dokku docker-options:add postharvest-api build '--file docker/api.Dockerfile'
dokku docker-options:add postharvest-chat build '--file docker/frontend.Dockerfile'
```

The frontend Dockerfile needs the API URL baked in at build time (Vite env vars are compile-time):

```bash
dokku docker-options:add postharvest-chat build '--build-arg VITE_API_URL=https://api.yourdomain.com'
```

---

## 3. Configure environment variables

### API app

```bash
dokku config:set postharvest-api \
  DATABASE_URL=postgresql://scraper:ph_scraper_pass@localhost:5433/postharvest_scraper \
  OPENAI_API_KEY=sk-... \
  SUNBIRD_API_KEY=... \
  WHATSAPP_TOKEN=... \
  WHATSAPP_PHONE_NUMBER_ID=... \
  WHATSAPP_VERIFY_TOKEN=your-chosen-verify-token \
  WHATSAPP_APP_SECRET=your-app-secret \
  API_CORS_ORIGINS='["https://chat.yourdomain.com"]' \
  ENVIRONMENT=production \
  LOG_LEVEL=INFO
```

> **Database:** The Docker containers on the droplet can reach PostgreSQL at `localhost:5433` (or the internal Docker network address). Adjust if your DB runs elsewhere.

> **WhatsApp:** Leave `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` empty initially — the API will start fine without them, the WhatsApp webhook simply won't work until you add them.

---

## 4. Set up domains and SSL

```bash
# On the droplet
dokku domains:add postharvest-api api.yourdomain.com
dokku domains:add postharvest-chat chat.yourdomain.com

# Enable HTTPS (run after first deploy so the app is reachable)
dokku letsencrypt:enable postharvest-api
dokku letsencrypt:enable postharvest-chat

# Auto-renew
dokku letsencrypt:cron-job --add
```

Add DNS records at your registrar:

```
A  api.yourdomain.com   →  your-droplet-ip
A  chat.yourdomain.com  →  your-droplet-ip
```

---

## 5. Add git remotes (on your local machine)

```bash
git remote add dokku-api  dokku@your-droplet-ip:postharvest-api
git remote add dokku-chat dokku@your-droplet-ip:postharvest-chat
```

---

## 6. Deploy

```bash
# Deploy API
git push dokku-api main

# Deploy frontend
git push dokku-chat main
```

Each push triggers a Docker build and container restart. Check logs if a deploy fails:

```bash
# On the droplet
dokku logs postharvest-api --tail 50
dokku logs postharvest-chat --tail 50
```

Verify the API is healthy:

```bash
curl https://api.yourdomain.com/health
# {"status":"ok","version":"1.0.0"}
```

---

## 7. Run database migrations

After the first deploy, initialise the database schema on the droplet. The easiest way is to run the init script inside the API container:

```bash
# On the droplet
dokku run postharvest-api poetry run python scripts/init_db.py
```

---

## 8. WhatsApp setup (Meta Cloud API)

### Create a Meta app

1. Go to [developers.facebook.com](https://developers.facebook.com) → Create App → Business
2. Add the **WhatsApp** product
3. Under WhatsApp → API Setup, note your **Phone Number ID** and generate a **Permanent Token**
4. Set these in Dokku (re-deploy is not required — Dokku injects env vars at container start):

```bash
dokku config:set postharvest-api \
  WHATSAPP_PHONE_NUMBER_ID=your-phone-number-id \
  WHATSAPP_TOKEN=your-permanent-token
```

### Register the webhook

In the Meta developer portal → WhatsApp → Configuration → Webhook:

- **Callback URL**: `https://api.yourdomain.com/webhook/whatsapp`
- **Verify token**: the value you set for `WHATSAPP_VERIFY_TOKEN`
- **Subscribed fields**: `messages`

Click Verify — Meta will call the `GET /webhook/whatsapp` endpoint to confirm the token.

### Test it

Send a message to your WhatsApp Business number. The reply should arrive within a few seconds.

---

## 9. Infrastructure on the droplet

The knowledge pipeline (PostgreSQL, Qdrant, MinIO, Prefect) still runs via Docker Compose on the droplet alongside the Dokku apps. This is intentional — Dokku manages the API and frontend; Docker Compose manages the stateful services.

```bash
# On the droplet — clone the repo and start infrastructure
git clone <repo-url> /opt/postharvest
cd /opt/postharvest
cp .env.example .env   # fill in credentials
docker compose up -d postgres qdrant minio prefect-server

# Init the DB
poetry run python scripts/init_db.py

# Start the Prefect worker (run in screen or systemd)
poetry run prefect worker start --pool postharvest-pool
```

---

## Ongoing operations

### Deploy an update

```bash
# Local machine
git push dokku-api main
git push dokku-chat main
```

### Restart a service

```bash
dokku ps:restart postharvest-api
dokku ps:restart postharvest-chat
```

### View logs

```bash
dokku logs postharvest-api -t       # stream API logs
dokku logs postharvest-chat -t      # stream frontend logs
docker compose logs -f postgres     # DB logs
```

### Database backup

```bash
# On the droplet
docker exec postharvest-postgres pg_dump -U scraper postharvest_scraper \
  > backup-$(date +%Y%m%d).sql
```

### Scale the API (if needed)

```bash
dokku ps:scale postharvest-api web=2
```

---

## Environment variable reference

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `OPENAI_API_KEY` | Yes | For LLM and embeddings |
| `SUNBIRD_API_KEY` | No | Translation — disabled if empty |
| `WHATSAPP_TOKEN` | No | WhatsApp — webhook inactive if empty |
| `WHATSAPP_PHONE_NUMBER_ID` | No | WhatsApp |
| `WHATSAPP_VERIFY_TOKEN` | No | WhatsApp — any string you choose |
| `WHATSAPP_APP_SECRET` | Strongly recommended | WhatsApp — Meta App Secret for webhook signature verification |
| `API_CORS_ORIGINS` | Yes | JSON array of allowed origins, e.g. `["https://chat.yourdomain.com"]` |
| `QDRANT_URL` | Yes | Default `http://localhost:6333` |
| `MINIO_ENDPOINT` | Yes | Default `localhost:9000` |
| `ENVIRONMENT` | No | `development` or `production` |
| `LOG_LEVEL` | No | `INFO` (default) |
| `VITE_API_URL` | Yes (build arg) | Set via `dokku docker-options:add` at build time |
