# Access Control Design (Web + WhatsApp)

**Date:** 2026-07-20
**Status:** Approved
**Goal:** Gate the public chat (web and WhatsApp) behind admin-issued, shared access codes so that only vetted users can consume LLM tokens, while keeping redemption low-friction for the target audience (farmers, extension workers, researchers in Uganda, on a mix of low-end smartphones and WhatsApp).

---

## Overview

Today, `/chat`, `/chat/stream`, and the WhatsApp webhook are open to anyone, bounded only by a per-IP / per-phone hourly rate limit (`api_rate_limit_web`, `api_rate_limit_whatsapp`). There is no concept of an authorized user. This design adds:

1. **Access codes** — admin-issued, shared by a group (e.g. a partner org), each with a monthly message quota.
2. **Access grants** — a permanent binding of an identity (WhatsApp phone number, or a web browser) to a code, created at redemption time.
3. **Quota enforcement** — a cheap DB check before every LLM call, on both channels.
4. **A global monthly ceiling** — an independent circuit breaker across all codes combined.
5. **Admin UI** — code creation, usage visibility, revoke/reactivate, limit adjustment.

Existing per-IP/per-phone rate limiting, WhatsApp webhook signature verification, and dedup logic are unchanged — this sits in front of them as an earlier gate.

---

## Data model (`src/storage/models.py`)

### `AccessCode`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `code` | str, unique | Three-word human-typeable string (e.g. `mango-tractor-92`), admin-generated or admin-supplied |
| `label` | str | e.g. "NARO Extension Officers — Q3 batch" |
| `monthly_limit` | int | Messages per calendar month |
| `status` | enum(`active`, `revoked`) | |
| `usage_count` | int | Messages used in the current period |
| `period_start` | datetime | Start of the current billing month; reset lazily |
| `created_at` | datetime | |
| `created_by` | str | Admin username |

**Lazy monthly reset**: on each usage check, if `now` falls in a later calendar month than `period_start`, reset `usage_count` to 0 and set `period_start` to the first of the current month, before applying the increment. No scheduled job required.

### `AccessGrant`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `access_code_id` | FK → AccessCode | |
| `channel` | enum(`web`, `whatsapp`) | |
| `identifier` | str, unique per channel | Phone number (WhatsApp) or random opaque token (web) |
| `redeemed_at` | datetime | |

A grant is permanent once created — it is never re-verified against the original code string, only against the code's current `status`/quota. Revoking a code instantly cuts off every grant bound to it; there is no signed/cached token that can outlive that check, since every request re-resolves the grant from the database.

---

## Enforcement path (both channels)

Before running the RAG pipeline for any inbound message:

1. Look up the `AccessGrant` by identifier (phone number or web token).
   - No grant found → channel-specific "not onboarded" handling (see below); do not call the LLM.
2. Resolve the grant's `AccessCode`.
   - `status != active` → reply with a "no longer active, contact your organization" message; do not call the LLM.
   - Apply lazy monthly reset if needed, then check `usage_count < monthly_limit` → if exhausted, reply with a "quota used up for this month" message; do not call the LLM.
3. Check the **global ceiling** (see below) → if exceeded, reply with a "temporarily unavailable" message; do not call the LLM.
4. Increment `AccessCode.usage_count` and the global counter, then proceed to `process_chat` as today.

All of this is one or two indexed lookups — negligible cost next to an LLM call, which is the point: the expensive path is never reached for unauthorized or over-quota requests.

---

## WhatsApp flow (`src/api/routes/whatsapp.py`)

Added as a step before the existing RAG call, inside the webhook handler:

1. Inbound message from a phone number with no `AccessGrant` → treat the message as a **code attempt**, not a question:
   - Valid, active, has capacity → create the grant (channel=`whatsapp`), reply "You're in! Ask me anything about post-harvest handling."
   - Invalid code string → reply "That code wasn't recognized. Please check it and try again." Subject to attempt throttling (see Security).
   - Valid but revoked/exhausted → reply "This code is no longer active. Please contact [org] for a new one."
   - If this is the very first message ever seen from the number (not a failed code attempt), reply "Welcome! Please reply with your access code to get started." instead of treating it as a code guess.
2. Once bound, every subsequent message runs the quota check above, then the existing `process_chat` flow unchanged.

Existing dedup (`_is_duplicate`) and per-phone rate limiting (`_is_rate_limited`) remain in place, applied to all inbound messages including code attempts.

---

## Web flow

### Backend

New endpoint, `src/api/routes/access.py`:

- `POST /access/redeem {code}` → validates the code exactly as WhatsApp does, creates a `channel=web` grant with a randomly generated opaque token, returns it. No PII collected.

`/chat`, `/chat/stream`, and `/session/*` now require an `X-Access-Token` header, resolved to a grant via the same enforcement path.

### Frontend

- On load, check `localStorage` for a stored access token.
  - Absent → render a code-entry screen only (the chat UI itself is not shown to unauthenticated visitors). On successful `POST /access/redeem`, store the token and proceed to chat.
  - Present → send it as `X-Access-Token` on all API calls.
- If any API call returns a "revoked" or "quota exceeded" response, clear the stored token client-side and drop back to the code-entry screen with an explanatory message.

---

## Admin UI

New JWT-protected routes under `/admin` (reusing the existing `require_admin` dependency in `src/api/routes/admin.py`):

- `POST /admin/access-codes` — create a code (label, monthly limit; code string auto-generated as a three-word combination unless the admin supplies one).
- `GET /admin/access-codes` — list codes with status, current-period usage, and redemption count (distinct grants).
- `POST /admin/access-codes/{id}/revoke`
- `POST /admin/access-codes/{id}/reactivate`
- `PATCH /admin/access-codes/{id}` — adjust `monthly_limit` without issuing a new code.

New React admin page `frontend/src/admin/pages/AccessCodes.jsx`, added to the existing `/admin/*` router alongside `Documents.jsx`, `Config.jsx`, etc. Each code is a row: label, code, usage bar ("312 / 500 this month"), redemption count, active/revoked toggle.

---

## Security

- **Code format**: three-word combinations from a fixed word list (~4096³ ≈ 68 billion combinations) — human-typeable on a phone keyboard, shareable verbally, resistant to brute force.
- **Redemption attempt throttling**: max 5 failed code attempts per phone number (WhatsApp) or per IP (web `/access/redeem`) per hour, independent of the existing chat rate limits. Reuses the same in-memory sliding-window pattern already used for WhatsApp per-phone rate limiting (`_is_rate_limited` in `whatsapp.py`).
- **Global monthly ceiling**: one settings value, `global_monthly_message_limit`, tracked as a single counter incremented alongside every successful per-code usage increment. If total usage across all codes crosses it, both channels stop answering (a "temporarily unavailable, back next month" reply) regardless of individual code quotas remaining. This is an independent backstop against a leaked/over-shared code or a bug in per-code enforcement — same lazy-reset pattern as `AccessCode.usage_count`, stored as a single row (or a settings-adjacent table) rather than per-code.
- **CORS**: `api_cors_origins` currently defaults to `["*"]`. Tighten to the actual deployed frontend origin(s) now that there's a real access boundary worth protecting — an open CORS policy otherwise makes the redemption endpoint more exposed to scripted abuse from arbitrary origins than necessary.
- Existing per-IP (web) and per-phone (WhatsApp) hourly rate limits remain unchanged as an orthogonal guard against bursty traffic from a single bound identity — they are not a substitute for the quota system.

---

## Testing

- Unit tests for `AccessCode` quota logic: lazy monthly reset across a month boundary, exhausted/revoked/invalid code paths, global ceiling trip.
- Extend `tests/test_whatsapp_webhook.py`: unbound number → onboarding prompt → valid/invalid/exhausted code attempts → bound number → normal `process_chat` flow, following the existing test structure in that file and `tests/test_whatsapp_service.py`.
- New `tests/test_access_control.py` covering `POST /access/redeem` and grant/quota enforcement on `/chat`.
- Frontend: manual pass through gate → redeem → chat → simulate a revoked/exhausted response → confirm drop back to the code-entry screen.

---

## Out of scope (for this design)

- Per-individual codes / accounts (explicitly deferred — codes are shared per group by design).
- Token-cost-based quotas (message-count quotas are the unit; token cost varies by provider/model but message count is treated as an adequate proxy for now).
- Self-service signup (all codes are admin-issued).
