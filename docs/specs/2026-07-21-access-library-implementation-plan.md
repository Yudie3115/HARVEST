# Access-Controlled Chat, Knowledge Library & Q&A Catalogue Implementation Plan

**Date:** 2026-07-21  
**Status:** Proposed implementation plan  
**Supersedes for implementation:**
`2026-07-20-access-control-design.md` and
`2026-07-20-knowledge-library-design.md`  
**Goal:** Make trusted post-harvest knowledge freely browsable while reserving paid live-chat
capacity for users holding an administrator-issued access code.

The two source designs remain the product rationale. This document is the implementation contract
and resolves their overlapping authentication, quota, session, background-processing, and
publication concerns.

---

## 1. Product Boundary

The web experience is browse-first. Public users can search the library and catalogue without an
access code. An access grant is required only when a request will enter live chat.

| Capability | Public | Access grant required | Consumes message quota |
|---|---:|---:|---:|
| Browse document library | Yes | No | No |
| Browse Q&A catalogue | Yes | No | No |
| Match a question against the catalogue | Yes | No | No |
| View an existing catalogue answer | Yes | No | No |
| Create or read a chat session | No | Yes | No |
| Submit a live web chat question | No | Yes | Yes |
| Submit a live WhatsApp chat question | No | Yes | Yes |
| Redeem an access code | Yes | No | No |
| Admin operations | No | Admin JWT | No |

`POST /catalogue/match` still uses language detection, translation, embedding, and vector search.
It therefore retains a per-IP rate limit even though it does not consume a message quota.

### Web journey

1. `/` shows one question input and links to Documents and Catalogue.
2. The question is sent to `POST /catalogue/match`.
3. On a match, show the reusable answer and citations. The user can confirm that it answered the
   question, reject the match, or ask a follow-up.
4. On a miss, rejected match, or follow-up, check for a valid browser access token.
5. If absent or invalid, show the code-entry screen while retaining the pending question locally.
6. After redemption, create a grant-owned chat session and submit the retained question to live
   chat.

The access token is not cleared when a monthly quota is exhausted. The UI retains it and shows the
next reset period. It is cleared only when it is invalid or the user explicitly removes it. A
revoked token may also be retained behind a blocked-state screen so that reactivation works without
requiring another redemption.

### WhatsApp journey

1. For a phone number without an active grant, a message matching the three-word code format is
   treated as a redemption attempt; any other message receives the welcome/code prompt.
2. A well-formed but unknown code receives the invalid-code response and counts toward redemption
   throttling.
3. A successful redemption binds the phone to the code and creates or associates its WhatsApp chat
   session.
4. Subsequent questions reserve quota and enter the existing RAG pipeline.
5. A phone bound to a revoked or obsolete code may redeem a replacement code. Grant history is
   retained, but only one grant per channel and identifier is active at a time.

---

## 2. Database and Migration Foundation

Use Alembic for all schema changes. `Base.metadata.create_all()` remains useful for empty local
databases but is not the production migration mechanism. Add an Alembic configuration and one
reviewable migration for the schema below before implementing routes.

All timestamps are timezone-aware. Calendar-month quotas use UTC for storage and reset boundaries;
the API may display the reset time in Africa/Kampala.

Add a required `access_hash_secret` deployment setting, distinct from the admin JWT secret, for
code and low-entropy identifier HMACs. Rotating it requires a deliberate grant/code migration, so
secret rotation must be documented before production rollout.

### `AccessCode`

| Column | Type | Constraints / notes |
|---|---|---|
| `id` | UUID | Primary key |
| `code_hash` | String(64) | Unique keyed HMAC-SHA-256 digest of the normalized code |
| `code_ciphertext` | Text, nullable | Optional reversible value only if admins must redisplay codes; otherwise show once at creation |
| `label` | String(200) | Required, admin-facing |
| `organization_name` | String(200), nullable | User-facing owner name |
| `contact_message` | Text, nullable | User-facing replacement-code instructions |
| `monthly_limit` | Integer | Required, greater than or equal to zero |
| `status` | Enum | `active`, `revoked` |
| `usage_count` | Integer | Required, default 0 |
| `period_start` | DateTime(timezone=True) | First instant of the current UTC month |
| `created_at` | DateTime(timezone=True) | Server default `now()` |
| `created_by` | String(100) | Admin username |

Codes use three dictionary words, for example `mango-river-granary`. Normalize by trimming,
lowercasing, and collapsing surrounding separator whitespace before hashing. Generated codes use a
cryptographically secure random generator and a versioned word list. A 4096-word list provides
approximately 36 bits of entropy across three words. A keyed digest prevents an offline dictionary
attack if only the database is exposed. Codes are shown in full at creation; persistent redisplay is
optional and requires application-level encryption rather than plaintext storage.

### `AccessGrant`

| Column | Type | Constraints / notes |
|---|---|---|
| `id` | UUID | Primary key |
| `access_code_id` | UUID | FK to `access_codes.id`, indexed |
| `channel` | Enum | `web`, `whatsapp` |
| `identifier_hash` | String(64) | SHA-256 for web tokens; keyed HMAC-SHA-256 for normalized phones |
| `status` | Enum | `active`, `replaced` |
| `redeemed_at` | DateTime(timezone=True) | Server default `now()` |
| `replaced_at` | DateTime(timezone=True), nullable | Set during rebinding |

Add a partial unique index on `(channel, identifier_hash)` where `status = 'active'`. Rebinding a
phone marks the previous grant `replaced` and creates a new active grant in the same transaction.
Web token redemption always creates a new opaque 256-bit token. Only its hash is stored.

### `ChatSession` change

Add nullable `access_grant_id`, indexed, with an FK to `access_grants.id`. It is nullable only to
preserve existing rows during migration. Every new web or WhatsApp session must set it. After old
session retention is resolved, a later migration may make it non-null.

Possession of a valid grant is not sufficient to access arbitrary sessions. Every create, history,
chat, and stream operation verifies that `ChatSession.access_grant_id` equals the resolved grant ID.

### `Document` publication fields

Add `publicly_visible` (Boolean, required, default false), `published_at`, and `published_by`.
Existing documents remain private during migration. Trusted domains may be bulk-approved through a
reviewed migration or admin operation, but relevance scoring alone never changes publication state.

### `GlobalUsageCounter`

| Column | Type | Constraints / notes |
|---|---|---|
| `id` | SmallInteger | Singleton primary key, fixed value `1` |
| `usage_count` | Integer | Required, default 0 |
| `period_start` | DateTime(timezone=True) | Current UTC month |

This table is intentionally separate from application settings so quota mutation is transactional.

### `CatalogueEntry`

Use the model from the knowledge-library design with these changes:

- Statuses are `pending`, `publishing`, `approved`, `publish_failed`, `rejected`, and `retracted`.
- Add `publish_error`, `publish_attempts`, and `updated_at`.
- Keep `embedding` in PostgreSQL for modest-volume deduplication; validate its dimension before
  storing it.
- `question_translations` and `answer_translations` contain the five non-English supported language
  codes. English remains in `question_en` and `answer_en`.
- Replace ambiguous `hit_count` with:
  - `served_count`: catalogue matches returned to users.
  - `helpful_count`: users who confirmed "this answers it".
  - `candidate_duplicate_count`: later chat candidates deduplicated into this entry.
- Use timezone-aware timestamps throughout.

### `BackgroundJob`

Add a small database-backed job/outbox table rather than relying on FastAPI `BackgroundTasks` for
catalogue publication:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `job_type` | String | Initially `score_and_catalogue` or `publish_catalogue` |
| `payload` | JSONB | IDs and immutable inputs needed by the job |
| `status` | Enum | `pending`, `running`, `completed`, `failed` |
| `attempts` | Integer | Retry counter |
| `available_at` | DateTime(timezone=True) | Supports backoff |
| `last_error` | Text, nullable | Sanitized failure detail |
| `created_at`, `updated_at` | DateTime(timezone=True) | Audit timestamps |

A lightweight worker can claim jobs with `SELECT ... FOR UPDATE SKIP LOCKED`. This provides durable
retry without introducing Redis or another queue in this release.

---

## 3. Access and Quota Service

Create `src/api/services/access_service.py`. Route handlers resolve identities and delegate all
authorization and quota mutation to this service.

### Grant resolution

- Web: read `X-Access-Token`, hash the high-entropy token with SHA-256, and resolve an active web
  grant.
- WhatsApp: normalize the sender phone number, compute a domain-separated HMAC using an application
  secret, and resolve an active WhatsApp grant.
- Resolve the associated access code on every protected request so revoke/reactivate takes effect
  immediately.
- Return structured errors rather than parsing human-readable messages.

### Atomic quota reservation

Quota reservation happens immediately before live RAG processing in one database transaction:

1. Lock the singleton global row.
2. Lock the access-code row.
3. Lazily reset either row if its `period_start` is before the current UTC month.
4. Reject if the code is inactive, its limit is exhausted, or the global limit is exhausted.
5. Increment both counters and commit.
6. Start RAG processing.

All code paths acquire locks in global-then-code order to prevent deadlocks. Conditional `UPDATE`
statements with affected-row checks are also acceptable if both counters remain in one transaction.

A reserved message is charged even if embedding, retrieval, translation, or the LLM later fails.
This makes cost enforcement predictable and prevents repeated failing requests from bypassing the
ceiling. Catalogue matches, session creation/history, code redemption, invalid requests, and
requests rejected before reservation do not consume quota.

### Error contract

Protected JSON endpoints return an HTTP status and stable body:

```json
{
  "error": {
    "code": "quota_exhausted",
    "message": "This group's messages have been used for this month.",
    "period_resets_at": "2026-08-01T00:00:00Z"
  }
}
```

| Code | HTTP status | Meaning |
|---|---:|---|
| `access_required` | 401 | Token absent |
| `access_invalid` | 401 | Token unknown or replaced |
| `access_revoked` | 403 | Grant exists but its code is revoked |
| `session_forbidden` | 403 | Session belongs to another grant |
| `quota_exhausted` | 429 | Code monthly limit reached |
| `global_limit_reached` | 503 | System-wide circuit breaker reached |
| `redemption_rate_limited` | 429 | Too many invalid attempts |

Authorization must execute before a streaming response begins so authentication errors can use
normal HTTP statuses. Errors that occur after SSE begins use the same stable codes in an SSE error
event.

### Redemption throttling

Do not treat CORS as a security control. Restrict CORS to deployed browser origins, but apply
server-side throttling to all clients.

Use a database-backed failed-attempt counter keyed by a domain-separated HMAC of IP address or phone
number, with a one-hour window. A plain hash is insufficient for low-entropy identifiers. This works
across multiple API processes. Successful redemption clears the active window. Existing in-memory
chat limits can remain temporarily, but their per-process limitation should be documented and
monitored.

---

## 4. API Changes

### Access

- `POST /access/redeem` — redeem a code and return the one-time plaintext web token plus grant
  status.
- `GET /access/status` — return code status, current usage, limit, and reset time for the current
  token.
- `POST /admin/access-codes`
- `GET /admin/access-codes`
- `PATCH /admin/access-codes/{id}`
- `POST /admin/access-codes/{id}/revoke`
- `POST /admin/access-codes/{id}/reactivate`
- `PATCH /admin/documents/{id}/publication` — explicitly publish or unpublish a processed document.

`POST /session/new`, `GET /session/{id}/history`, `POST /chat`, and `POST /chat/stream` require a web
grant and enforce session ownership. `/chat/models` may remain public because it does not invoke a
model.

### Document library

- `GET /library/facets`
- `GET /library/documents`
- `GET /library/documents/{id}`

Every endpoint requires `Document.status == PROCESSED`, a classification score at or above
`relevance_threshold`, and `Document.publicly_visible == true`; relevance alone does not establish
publication permission.

The first release returns summaries, key practices, metadata, citations, and bounded excerpts.
It does not return assembled full document text. Uploaded `upload://` sources are excluded from the
public library unless explicitly marked public and given a valid public source URL. All Markdown
and outbound links are sanitized in the frontend.

Facet filters use PostgreSQL array operations and facet counts use `unnest()`/`GROUP BY`. Search and
pagination parameters have explicit maximum lengths and limits. The five-minute cache is
per-process and only an optimization; correctness cannot depend on it.

### Q&A catalogue

- `POST /catalogue/match` — rate-limited public semantic match; increments `served_count` only when
  a match is returned.
- `POST /catalogue/{id}/helpful` — rate-limited public confirmation; increments `helpful_count`.
- `GET /catalogue` — approved entries only.
- `GET /catalogue/{id}` — approved entries only.
- `GET /admin/catalogue/pending`
- `GET /admin/catalogue/approved`
- `POST /admin/catalogue/{id}/approve`
- `POST /admin/catalogue/{id}/reject`
- `POST /admin/catalogue/{id}/retract`
- `POST /admin/catalogue/{id}/retry-publish`

All public detail lookups return the same 404 for missing, pending, failed, rejected, or retracted
entries.

---

## 5. Catalogue Processing and Publication

### Candidate job

After a successful live answer is committed, enqueue one `score_and_catalogue` job containing the
assistant message ID and the source chunk IDs. The worker performs the entire dependent sequence:

1. Reload the assistant message, preceding user message, and referenced chunks.
2. Compute BERTScore and persist it on the assistant message.
3. Stop if scoring failed or F1 is below `catalogue_min_faithfulness`.
4. Ask the LLM for a bounded JSON result containing `worth_cataloguing_score` and
   `optimised_question`.
5. In manual mode, stop if the LLM score is below `catalogue_min_score`.
6. Embed the optimized question.
7. Compare against pending, publishing, and approved entries.
8. On a duplicate, increment `candidate_duplicate_count` and complete the job.
9. Otherwise create a pending entry in manual mode or create an entry and enqueue publication in
   auto mode.

BERTScore is treated as a grounding similarity signal, not proof of factual correctness. Manual is
the launch default. Auto mode must not be enabled until thresholds are calibrated against a reviewed
production sample.

### Idempotent publication

Publication is a retryable state machine, not an atomic database/vector/translation operation:

1. Atomically transition `pending` or `publish_failed` to `publishing`.
2. Translate the English question and answer into `lug`, `ach`, `nyn`, `teo`, and `lgg`. Reuse any
   already persisted translations on retry.
3. Validate that every required translation exists.
4. Upsert the English question embedding into the catalogue vector collection using the catalogue
   entry UUID as the stable vector ID.
5. Mark the entry `approved`, set `approved_at`, and clear `publish_error`.

On failure, retain completed work, mark `publish_failed`, record a sanitized error, and retry with
backoff. No entry is publicly visible unless its status is `approved`.

Retraction first marks the database row `retracted`, immediately removing it from SQL-backed browse
results. It then attempts vector deletion through a retryable job. The ask gate also resolves the
matched database row and confirms `approved`, so a delayed vector deletion cannot serve a retracted
answer.

Instantiate a separate `VectorDBClient(collection=settings.catalogue_collection_name)` during app
startup and ensure both document and catalogue collections exist. Add generic point deletion to the
vector abstraction instead of reusing the document-specific method name.

---

## 6. Chat Relevance Gate

Add `chat_min_top_score` independently of `chat_score_threshold`:

- `chat_score_threshold` controls which chunks are included as context.
- `chat_min_top_score` controls whether live synthesis happens at all.

Both streaming and non-streaming paths check the highest returned score before invoking the LLM.
The vector backends must guarantee descending score order, or the service must compute the maximum.
The no-results response points users to `/library` and `/catalogue`.

Do not choose a production default from intuition alone. Initially log top scores and outcomes with
the gate disabled, review false-positive and false-negative examples, then set the threshold through
deployment configuration. Tests use explicit values and cover empty results as well as below- and
above-threshold hits.

---

## 7. Frontend Changes

Top-level navigation becomes `Ask | Documents | Catalogue`. `/chat` remains an internal route used
after the ask gate falls through.

Add a shared access context that:

- stores the web token under one namespaced `localStorage` key;
- adds `X-Access-Token` to protected API calls only;
- fetches `/access/status` on startup and when returning from a suspended tab;
- preserves pending questions through redemption;
- distinguishes invalid, revoked, exhausted, and globally unavailable states;
- never exposes access tokens in URLs or logs.

When a catalogue follow-up starts live chat, create a normal grant-owned session and persist the
catalogue question and answer as initial history in a dedicated backend operation or explicit session
seed payload. Do not rely only on React navigation state, because refreshes would lose the context.
The seeded catalogue messages do not consume quota; the new follow-up does.

Admin pages add Access Codes and Catalogue. Code creation shows the generated code once with a copy
action. Catalogue review displays sources, grounding score, LLM score, publication state, and retry
errors separately.

---

## 8. Implementation Phases

### Phase 1 — Schema and access foundation

- Configure Alembic and create the migration.
- Add access models, global counter, session ownership, catalogue models, and background jobs.
- Implement code generation/normalization, token hashing, grant resolution, rebinding, and atomic
  quota reservation.
- Add structured error responses and access admin APIs.
- Gate and ownership-check session/chat endpoints and WhatsApp chat.

Exit criterion: unauthorized requests cannot create/read sessions or invoke RAG; concurrent tests
cannot exceed either quota.

### Phase 2 — Public document library

- Decide and implement the public-visibility rule.
- Add library schemas/routes and bounded excerpts.
- Build Documents navigation, facets, results, detail pages, empty states, and sanitization.

Exit criterion: only explicitly publishable processed documents appear through any public library
endpoint.

### Phase 3 — Manual Q&A catalogue

- Add the durable worker and combined score/candidate job.
- Add manual review, idempotent publication, retraction, and retry.
- Add catalogue browse/detail/helpful APIs and UI.
- Add the separate vector collection and status verification after vector matches.

Exit criterion: a successful chat can produce a pending candidate; approval safely publishes all
language variants; retraction immediately prevents serving it.

### Phase 4 — Ask gate and integrated UX

- Replace `/` with Ask.
- Add catalogue match/no-match/reject/follow-up states.
- Add access redemption at live-chat fallthrough and persist seeded follow-up history.
- Preserve `/chat` for the internal live-chat experience.

Exit criterion: public users browse and receive catalogue answers without a code, while every live
question is grant-owned and quota-controlled.

### Phase 5 — Calibration and operational hardening

- Collect top-score, catalogue-match, helpful, rejected-match, and reviewer outcome metrics.
- Calibrate `chat_min_top_score`, catalogue thresholds, and rate limits.
- Exercise worker retries, failed translations, vector outages, code revoke/reactivate, month reset,
  and the global circuit breaker in staging.
- Consider auto catalogue gating only after reviewed evidence supports it.

---

## 9. Verification Plan

### Backend automated tests

- Migration upgrade from the current schema and clean-database creation.
- Code normalization, hashing, collision retry, invalid-code behavior, and one-time display.
- Grant replacement and revoked/reactivated behavior.
- Session ownership across new, history, chat, and stream routes.
- Concurrent per-code and global quota reservation; UTC month rollover; deterministic lock order.
- Charged versus uncharged request paths, including provider failure after reservation.
- Redemption throttling across independent app instances sharing the database.
- Library facet counts, combined filters, pagination limits, publication exclusions, and uniform 404s.
- Candidate jobs in manual/auto configurations, failed scoring, deduplication, and retry idempotency.
- Partial translation failure, vector upsert failure, publish retry, and retract-before-vector-delete.
- Catalogue match status recheck, threshold boundaries, helpful counts, and rate limiting.
- Chat top-score gate in streaming and non-streaming paths.
- WhatsApp first-contact prompt, invalid attempts, redemption, rebinding, quota errors, and normal chat.

### Frontend verification

- Public Ask match and browse paths without a token.
- Miss → redemption → session creation → retained question submission.
- Follow-up seeded from a catalogue answer and retained after refresh.
- Invalid, revoked, exhausted, and global-ceiling states.
- Exhausted token works after simulated month rollover without re-redemption.
- Responsive library/catalogue/admin layouts and keyboard-accessible actions.
- Production build with `cd frontend && npm run build`.

### Operational checks

- Run the full backend suite with `make test`.
- Verify configured CORS origins without treating CORS as authorization.
- Confirm secrets, access tokens, phone numbers, and plaintext codes are absent from application logs.
- Confirm both vector collections and the job worker are healthy before enabling catalogue matching.
- Back up PostgreSQL before applying the production migration and document the downgrade limitations
  for enum and data-bearing schema changes.

---

## 10. Explicitly Deferred

- Individual user accounts or per-person quotas.
- Token-cost-based accounting.
- Redis or a dedicated task queue.
- Public serving of complete extracted source documents.
- Runtime admin switching of catalogue gating mode.
- Catalogue matching or browsing flows for WhatsApp.
- Automatic publication until manual-review data validates the quality thresholds.
