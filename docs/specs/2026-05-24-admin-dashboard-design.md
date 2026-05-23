# Admin Dashboard Migration — Design Spec

**Date:** 2026-05-24  
**Status:** Approved

---

## Overview

Migrate the Streamlit admin dashboard (`dashboard/app.py`) into the existing React frontend (`frontend/`). The Streamlit service is removed entirely after migration. The React admin lives at `/admin` on the same deployed frontend app (`postharvest-chat`), requiring no new Dokku app or Docker container.

---

## Architecture

### Routing

React Router is added to the existing frontend. Current routes are unchanged:

```
/              → existing chat UI (unchanged)
/admin         → redirects to /admin/overview if authenticated, else /admin/login
/admin/login   → login page (outside sidebar shell)
/admin/overview
/admin/documents
/admin/search
/admin/qa
/admin/config
/admin/add-document
```

### Authentication

- **Mechanism:** Single admin credential stored in env vars (`ADMIN_USERNAME`, `ADMIN_PASSWORD`). No database schema changes.
- **Token:** `POST /admin/login` exchanges credentials for a signed JWT (8-hour expiry). Secret is `ADMIN_JWT_SECRET`.
- **Storage:** JWT stored in `sessionStorage` (cleared on browser close).
- **Protection:** All admin API calls include `Authorization: Bearer <token>`. Any 401 response redirects to `/admin/login`. All `/admin/*` FastAPI routes validate the JWT via a shared dependency.

### New env vars

```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong-password>
ADMIN_JWT_SECRET=<openssl rand -hex 32>
```

---

## Backend — New FastAPI Routes

All routes under `/admin` prefix. A `require_admin` FastAPI dependency validates the JWT and is applied to every route except `/admin/login`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/admin/login` | Exchange credentials for JWT |
| `GET` | `/admin/stats` | Doc counts, processing rate, vector count |
| `GET` | `/admin/documents` | Paginated + filtered document list |
| `GET` | `/admin/health` | Connection status for all services |
| `GET` | `/admin/config` | Read-only current settings snapshot |
| `POST` | `/admin/crawl/full` | Trigger Prefect full crawl deployment |
| `POST` | `/admin/crawl/incremental` | Trigger Prefect incremental update |
| `POST` | `/admin/documents/ingest` | File or URL ingestion |

---

## Frontend — Component Library

**shadcn/ui** (CLI-copied Radix UI + Tailwind components) + **recharts** for the activity chart.

- shadcn/ui is installed into the existing `frontend/` project via its CLI
- Admin components use shadcn primitives: Card, Table, Badge, Button, Input, Select, Tabs, Dialog, Accordion, Progress, Alert
- The chat UI remains untouched — it uses inline styles and does not use shadcn

---

## UI Layout

### Shell (all `/admin/*` pages except login)

- **Persistent left sidebar** (220px), dark theme (`#09090b` / zinc palette)
- Sidebar sections:
  1. Logo + app name at top
  2. "Quick Actions" — **Run Full Crawl** (green) and **Incremental Update** buttons
  3. Navigation links with icons (Overview, Documents, Search, Knowledge Q&A, Configuration, Add Document). Documents link shows a count badge.
  4. Footer — admin username + logout button
- Main content area fills remaining width with 24px horizontal padding

### Login Page (`/admin/login`)

Split-panel layout, full viewport height:
- **Left panel** (45%): dark green (`#052e16`) branding strip — logo, app name, short description, service name pills
- **Right panel**: username + password form, Sign In button, "← Back to chat" link

---

## Pages

### Overview (`/admin/overview`)

- 4 stat cards in a row: Total Documents, Processed, Processing Rate (green), Vectors Indexed
- recharts AreaChart below: documents discovered per day over last 30 days
- Service health panel (right column): inline status dots for PostgreSQL, Qdrant, MinIO, LLM Service, Prefect, Sunbird AI. Status auto-loads on mount; a Refresh button re-fetches. No separate "Check Connections" tab.

### Documents (`/admin/documents`)

- shadcn DataTable with server-side pagination
- Filter controls: Site dropdown, Status dropdown, Sort (Discovered date / Relevance)
- Columns: Title, Site, Type, Status (Badge), Relevance score, Discovered timestamp
- Rows are expandable to show URL and full metadata

### Search (`/admin/search`)

- Text input for query
- Top-K slider (3–20)
- Language selector (Auto-detect + supported local languages), shown only when `translation_enabled=true`
- Results: expandable cards with chunk text, similarity score, topics, crops, document type

### Knowledge Q&A (`/admin/qa`)

- Textarea for question
- Collapsible "Search Filters" section: top-K slider, minimum similarity score slider
- Language selector (when translation enabled)
- "Ask" button
- Answer renders in a shadcn Alert with react-markdown
- Sources in Accordion items — each shows similarity progress bar, metadata, link to source

### Configuration (`/admin/config`)

- Read-only. Banner at top: *"Edit `.env` and restart services to change settings."*
- Settings grouped into sections: LLM (provider, model, temperature, max tokens), Crawl (max depth, rate limit, relevance threshold), Services (DB URL masked, Qdrant URL, MinIO endpoint, Prefect API URL)
- Values fetched from `GET /admin/config` on mount

### Add Document (`/admin/add-document`)

- shadcn Tabs: "Upload File" and "From URL"
- File tab: drag-and-drop zone (`react-dropzone`), optional Title and Source/site inputs, Add button
- URL tab: URL input, optional Title and Source/site inputs, Add button
- Inline result feedback: success (chunk count + relevance score), low-relevance rejection (with score), no-content rejection, error

---

## Removals

- `dashboard/` directory deleted entirely
- `streamlit` removed from `pyproject.toml` and `requirements.txt`
- No Streamlit entry in `docker-compose.yml` (it was run standalone; nothing to remove from compose)

---

## Documentation Changes

### `.env.example`

Add:
```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
ADMIN_JWT_SECRET=  # generate with: openssl rand -hex 32
```

### `DEPLOYMENT.md`

New **"Admin Panel"** section:
- Admin UI is at `/admin` on the `postharvest-chat` app — no new Dokku app needed
- Creating admin credentials: `dokku config:set postharvest-chat ADMIN_USERNAME=admin ADMIN_PASSWORD=... ADMIN_JWT_SECRET=...`
- Generate JWT secret: `openssl rand -hex 32`
- Frontend rebuild required after changing credentials (Vite bakes `VITE_*` vars at compile time; `ADMIN_*` vars are backend-only and injected at runtime via the API — no rebuild needed for credential changes)

### `QUICKSTART.md`

- Add `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_JWT_SECRET` to the local env var setup section
- Note: admin panel available at `http://localhost:5173/admin` after `docker compose up`

---

## Out of Scope

- Saving config changes at runtime (config tab is read-only)
- Multiple admin users (single credential in env)
- Admin activity logging / audit trail
- Role-based access control
