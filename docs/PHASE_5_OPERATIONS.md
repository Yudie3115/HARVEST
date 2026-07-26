# Phase 5 calibration and operational hardening

Phase 5 is evidence-driven. Production starts with `CATALOGUE_MODE=manual`. Neither value is
changed automatically.

`CHAT_MIN_TOP_SCORE` ships with a conservative interim default (`0.30`) rather than unset.
Live chat retrieval no longer filters candidate chunks by raw per-chunk embedding score before
synthesis — that discarded valid paraphrase/synonym matches whose cosine similarity landed just
under the old cutoff, even when the top-scoring chunk was clearly relevant. Relevance is now
gated once, on the *top* score across the full (unfiltered) top-k, via `CHAT_MIN_TOP_SCORE`.
Replace the interim `0.30` with an evidence-based value once the calibration report below has
enough reviewed samples.

## Calibration evidence

The application records operational rows in `system_metrics` for:

- live-chat retrieval top score and outcome (`synthesized`, `no_hits`, or
  `below_min_top_score`);
- catalogue match attempts and whether an approved entry was served;
- helpful and rejected-match feedback;
- candidate grounding/LLM scores and threshold outcome;
- administrator approve/reject decisions; and
- worker completion, retry, and permanent failure outcomes.

Telemetry deliberately excludes question/answer text, session identifiers, IP addresses, phone
numbers, access tokens, access codes, and exception messages.

`CATALOGUE_MATCH_OBSERVATION_THRESHOLD` controls how far below the serving threshold vector
results are retained for calibration. It defaults to `0.0`; only hits at or above
`CATALOGUE_MATCH_THRESHOLD` can be served.

Fetch a 30-day report with an administrator JWT:

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/admin/catalogue/calibration?days=30"
```

Use reviewed examples—not percentiles alone—to choose deployment values. After changing a
threshold or rate limit, restart the API and worker, mark the change time, and compare the next
window. Keep automatic catalogue publication off until the report has at least
`CATALOGUE_AUTO_MIN_REVIEWED_SAMPLES` decisions and the reviewed false-publication risk is
acceptable. The report only marks evidence availability; it never enables auto mode.

## Staging drills

Back up staging PostgreSQL, use non-production access codes, and capture the calibration report
before and after each drill.

1. **Worker retry:** stop the translation service or use an invalid staging endpoint, approve a
   pending entry, and verify `publishing → publish_failed`, a pending retry job with increasing
   `available_at`, and retained completed translations. Restore translation and verify approval.
2. **Vector outage:** stop Qdrant, approve an entry, verify it remains non-public and retries.
   Restore Qdrant and verify the stable entry UUID is upserted once.
3. **Revoke/reactivate:** redeem a code, revoke it, verify protected calls return
   `access_revoked`, reactivate it, and verify the same browser token works again.
4. **Month reset:** set a staging code and singleton counter to the previous UTC month at their
   limits. Submit one message and verify both reset before incrementing.
5. **Global circuit breaker:** set `GLOBAL_MONTHLY_MESSAGE_LIMIT` to the current singleton usage,
   verify live chat returns `global_limit_reached`, then restore the setting. Catalogue and library
   browsing must remain available.
6. **Permanent failure alert:** allow a job to reach `CATALOGUE_JOB_MAX_ATTEMPTS`; verify the
   calibration report shows a failed job and worker telemetry shows `failed`.

Run the focused automated coverage after every drill-related code change:

```bash
poetry run pytest \
  tests/test_access_service.py \
  tests/test_admin_access_routes.py \
  tests/test_catalogue_service.py \
  tests/test_catalogue_routes.py \
  tests/test_admin_catalogue_routes.py \
  tests/test_chat_service.py \
  tests/test_operational_metrics.py \
  tests/test_session_routes.py -v --tb=short
```
