# Implementation Plan: Backend frontend-readiness hardening

**Date**: 2026-11-08
**Status**: implemented and verified; frontend integration can start
**Scope**: close the code-level contract, reliability, performance, and deployment-artifact gaps that block a frontend from integrating against the daemon. Actual DNS/TLS/registry deployment, GitHub credentials, and a real SEC crawl remain operator inputs.

## 1. Why this change

The backend core is complete for local use: `166 passed, 2 skipped`, the Docker image is healthy, datasets are checksum-verified, and the HTTP/SSE surface is live-tested. The remaining gaps are not missing endpoints; they are integration hazards:

1. The same SSE event name (`snapshot`) has different payload shapes from the runner and the scheduler.
2. The frontend has no machine-readable HTTP/SSE contract or TypeScript types.
3. Large JSON responses are served uncompressed (`financials.json` is 1.28 MB; the full first load is about 3.4 MB).
4. A manifest with a missing/invalid `generated_at` is treated as healthy and never refreshed.
5. GitHub dispatch mode polls the workflow but never syncs the committed snapshot back into the daemon's data directory.
6. CORS does not send `Vary: Origin` when the request origin is absent or disallowed, which is unsafe for shared caches.
7. There are no checked-in deployment artifacts for TLS, SSE proxying, persistent data, or rate limiting.

This plan addresses 1-7 without changing the pipeline, the published JSON documents, or the ownership boundary: the backend still serves and orchestrates; the pipeline still owns data.

## 2. Baseline evidence before implementation

| Evidence | Result |
|---|---|
| `python -m pytest tests -q` | `166 passed, 2 skipped`, 24 pre-existing warnings |
| Docker daemon | available, server `29.6.1` |
| `SEC_USER_AGENT` / `GITHUB_TOKEN_DISPATCH` / `CRON_SECRET` | not set in this environment |
| SSE shapes | runner emits `{**freshness, changed}`; scheduler emits a 5-field subset; `ready` nests freshness under `snapshot` |
| Compression | `_send_bytes` sends identity bytes only |
| GitHub mode | dispatch + poll only; no `git pull`/artifact sync in `backend/` |
| Contract docs | prose route table only; no OpenAPI/JSON Schema/TypeScript types |
| Deployment | local Docker image only; no registry push, TLS, reverse proxy, or volume recipe |

## 3. Decisions

1. **Canonical SSE snapshot envelope.** Every `snapshot` event is `{"snapshot": <freshness>, "changed": <bool>}`. The runner and scheduler both use the same helper. `ready` already nests freshness under `snapshot`, so the frontend reads `payload.snapshot.*` consistently.
2. **`refresh_finished` carries `snapshot_changed`.** The refresh state gains `snapshot_changed: bool | null`. This lets a client that missed the `snapshot` event decide whether to refetch.
3. **Periodic snapshot state on SSE heartbeat.** Instead of sending only a comment every `AICOR_SSE_HEARTBEAT_SECONDS`, the server sends a `snapshot` event with the current freshness and `changed=false` when the queue times out. A slow client that missed a change recovers on the next heartbeat; the frontend must compare `snapshot.snapshot_version`, not rely only on `changed`.
4. **Application-level gzip with a weak ETag.** Compress JSON bodies above 1 KiB when the client accepts gzip. Use a weak ETag derived from the identity body (`W/"sha256"`), send `Vary: Accept-Encoding`, and compare `If-None-Match` with weak/strong-insensitive matching. Reverse proxies may also compress; the app-level behavior is correct without a proxy.
5. **Unknown `generated_at` is not fresh.** `freshness.stale` is true when the snapshot is available but the timestamp is missing/unparseable. `/api/health` becomes `degraded`; the scheduler triggers `missing-generated-at` instead of doing nothing.
6. **GitHub mode needs an explicit data-sync step.** Add optional `AICOR_POST_REFRESH_COMMAND`, run after a successful refresh and before the snapshot is reread. It is the operator's hook for `git pull`/artifact sync. If unset, GitHub mode remains dispatch-only and is documented as not updating the served snapshot; local mode with a persistent volume is the default production path.
7. **Deployment artifacts are checked in, not deployed.** Add `docker-compose.yml`, a reverse-proxy sample (nginx and Caddy), and a deployment README. Actual host, DNS, TLS certificate, registry, and secrets remain operator inputs.
8. **Contract docs are machine-readable where practical.** Add OpenAPI 3.1 for HTTP, a JSON Schema for SSE payloads, and TypeScript types. The existing prose contract and acceptance checks remain the source of truth for dataset documents.

## 4. Contracts

### 4.1 HTTP

No route changes. Add/confirm:

- `GET /api/health`: `200` with `status=ok|degraded`, `503` only when the manifest is unavailable.
- `GET /api/manifest`, `GET /api/data/<key>`: `ETag`, `If-None-Match`, `304`, `X-AICOR-Snapshot`, `Cache-Control: no-cache, must-revalidate`.
- `GET /api/latest`: `freshness`, `manifest`, optional `overview`, optional `decision`; `Cache-Control: no-store`.
- `GET /api/events`: SSE; `ready`, `snapshot`, `refresh`, `refresh_finished`, `scheduler_error`; heartbeat sends a periodic `snapshot`.
- `GET|POST /api/refresh`: `202`, `401`, `409`, `503`.
- Refresh authorization accepts `Authorization: Bearer <CRON_SECRET>` or
  `X-Cron-Secret`; the OpenAPI contract declares both alternatives.
- Error body: `{"error": "<code>", ...optional detail fields}`.

Compression/caching rules:

- Bodies >= 1024 bytes: gzip when `Accept-Encoding` allows it.
- Always send `Vary: Accept-Encoding` for responses that may be compressed.
- Always send `Vary: Origin` when the CORS allowlist is not `*`.
- ETag is weak: `W/"<sha256-of-identity-body>"`.
- `If-None-Match` accepts weak/strong forms and comma-separated values.

### 4.2 SSE

Wire format:

```text
retry: 3000

event: ready
data: {"snapshot": {...}, "refresh": {...}, "heartbeat_seconds": 15}

event: snapshot
data: {"snapshot": {...}, "changed": true}

event: refresh
data: {...RefreshState...}

event: refresh_finished
data: {...RefreshState..., "snapshot_changed": true}

event: scheduler_error
data: {"error": "ExceptionType"}
```

`Freshness` fields: `available`, `snapshot_version`, `data_as_of`, `generated_at`, `run_id`, `age_seconds`, `stale`, `stale_after_seconds`, `checksum_ok`, `file_count`, `problems`.

`RefreshState` fields: `status`, `job_id`, `reason`, `started_at`, `finished_at`, `detail`, `exit_code`, `target`, `log_path`, `run_id`, `snapshot_version`, `snapshot_changed`.

`changed` means “the producer observed a snapshot version different from its previous snapshot event”. The frontend should still compare `snapshot.snapshot_version` for idempotence.

### 4.3 Refresh sync

- `AICOR_POST_REFRESH_COMMAND` is parsed with `shlex.split` like `AICOR_PIPELINE_COMMAND`.
- It runs only after a successful dispatcher result, before the snapshot is reread.
- Non-zero exit/timeout marks the refresh `failed` with a bounded detail tail; no `snapshot` event is emitted.
- Unset means no-op.
- `/api/health` exposes `config.post_refresh_configured` so operators can see whether GitHub mode has a sync hook.

## 5. Implementation steps

### Phase 1 — Contract correctness

1. `backend/snapshot.py`
   - Add `snapshot_event(freshness, *, changed)` helper.
   - Make `freshness.stale` true when `available` and `age_seconds is None`.
2. `backend/runner.py`
   - Add `snapshot_changed` to `RefreshState`.
   - Read the pre-refresh snapshot version, run the dispatcher, optionally run the post-refresh command, then read the post-refresh snapshot; compute `changed` from the two versions.
   - Emit `snapshot_event(...)`.
   - Add `run_post_refresh_command(...)` and `build_post_refresh(config)`.
3. `backend/scheduler.py`
   - Emit `snapshot_event(snapshot.freshness(...), changed=...)`.
   - Trigger `missing-generated-at` when `age_seconds` is `None`.
4. `backend/server.py`
   - Use `snapshot_event(...)` for `ready` and periodic heartbeat snapshots.
   - Add gzip negotiation, weak ETag, `Vary: Accept-Encoding`, `Vary: Origin`, and weak `If-None-Match` matching.
   - Add `config.post_refresh_configured` to health.
5. `backend/settings.py`
   - Parse `AICOR_POST_REFRESH_COMMAND`.
6. `backend/__main__.py`
   - Wire the post-refresh command into the runner.
7. `backend/events.py`
   - No protocol change required; keep bounded queues. The periodic snapshot covers slow-consumer resync.

### Phase 2 — Contract artifacts

8. `docs/api/openapi.yaml` — HTTP routes, statuses, headers, schemas.
9. `docs/api/sse-events.schema.json` — SSE payload definitions.
10. `docs/api/types.ts` — TypeScript interfaces for the frontend.
11. `docs/api/README.md` — event table, caching, retry, consistency protocol, examples.
12. `tests/test_backend_contract_docs.py` — parse the OpenAPI YAML and SSE schema; assert required paths/definitions.

### Phase 3 — Deployment artifacts

13. `docker-compose.yml` — backend service, env file, named volumes for data/logs, healthcheck, restart policy.
14. `deploy/nginx.conf` — TLS placeholder, gzip, SSE proxy settings, rate/connection limits.
15. `deploy/Caddyfile` — TLS, gzip, SSE flush.
16. `deploy/README.md` — deployment checklist and smoke tests.
17. `.env.example` and `README.md` — document `AICOR_POST_REFRESH_COMMAND`, volume persistence, CORS, compression, and GitHub-mode sync caveat.

### Phase 4 — Verification

18. Unit/integration tests for every behavior above.
19. Full `python -m pytest tests -q`.
20. Docker build/run with a fake pipeline; verify health, gzip, ETag/304, SSE shape, periodic snapshot, graceful stop.
21. Live smoke against the real snapshot: health, manifest, latest, dataset, 304, gzip, SSE `ready`/`snapshot`.
22. Verify `AICOR_POST_REFRESH_COMMAND` with a local marker script; verify failure marks refresh failed.
23. Record evidence and update this plan's status.

## 6. Failure behavior

| Failure | Response/state |
|---|---|
| `Accept-Encoding: gzip` with a large body | `Content-Encoding: gzip`, weak ETag, `Vary: Accept-Encoding` |
| `If-None-Match` matches weak ETag | `304`, no body, same ETag |
| Missing/invalid `generated_at` | `freshness.stale=true`, health `degraded`, scheduler triggers `missing-generated-at` |
| Post-refresh command fails | refresh `failed`, detail tail, no `snapshot` event, old snapshot kept |
| GitHub run succeeds but no data sync | refresh `succeeded` with `snapshot_changed=false`; health shows `post_refresh_configured=false`; docs warn |
| SSE client misses an event | next heartbeat sends current `snapshot`; client compares version |
| CORS origin not allowed | no `Access-Control-Allow-Origin`; `Vary: Origin` still present |
| Compression + HEAD | `Content-Encoding` and compressed `Content-Length` mirror GET |

## 7. Test plan

- Snapshot: unknown timestamp -> stale; event helper shape.
- Runner: pre/post version change -> `snapshot_changed`; no change -> false; post-refresh failure -> failed; event shape.
- Scheduler: full freshness in `snapshot`; `missing-generated-at` triggers; event shape.
- Server: gzip on/off, weak ETag, 304 with gzip, `Vary: Accept-Encoding`, `Vary: Origin` with no/blocked origin, periodic snapshot, `ready` shape, `post_refresh_configured`.
- Settings: parse `AICOR_POST_REFRESH_COMMAND`.
- Main wiring: post-refresh command runs before snapshot reload.
- Docs: OpenAPI paths/schemas and SSE `$defs` exist.
- Full suite + Docker smoke + live loopback smoke.

## 8. Acceptance criteria

- All tests pass (`198 passed, 2 skipped`).
- No SSE event name has two payload shapes.
- `/api/latest` and large datasets are gzip-compressed when requested; 304 still works.
- A missing `generated_at` is visibly degraded and triggers a refresh.
- `AICOR_POST_REFRESH_COMMAND` runs after success and fails the refresh on error.
- `docs/api/openapi.yaml`, `docs/api/sse-events.schema.json`, and `docs/api/types.ts` are present and parse.
- `docker-compose.yml` starts the service with persistent data/logs and a healthy container.
- Deployment docs state exactly which inputs remain operator-provided (host, DNS, TLS, registry, `CRON_SECRET`, `AICOR_ALLOWED_ORIGINS`, `SEC_USER_AGENT` or GitHub token).

## 9. Verification results

- `python -m pytest tests -q`: `198 passed, 2 skipped`.
- Focused contract/deployment tests: `9 passed`; `python -m compileall -q backend`
  passed.
- Docker Compose config validation and image build passed. An isolated Compose
  project started with auto-refresh disabled; `/api/health` returned `ok` for
  snapshot `v20261106.9`.
- Live container checks passed: gzip body decoded, weak ETag present,
  `Vary: Accept-Encoding, Origin`, conditional request returned `304`, and SSE
  delivered `ready` followed by a periodic canonical `snapshot` event.
- Temporary Compose project, named volumes, and `.env` smoke-test file were
  removed. No real SEC crawl or GitHub dispatch was run because credentials are
  not configured.

## 10. External inputs / out of scope

- Actual production host, DNS, TLS certificate, and registry push.
- Real SEC crawl (needs `SEC_USER_AGENT`).
- Live GitHub dispatch (needs `GITHUB_TOKEN_DISPATCH` + `AICOR_GITHUB_REPOSITORY`).
- Vercel function (`api/health.ts`, `vercel.json`) remains descoped by the operator.
- Per-IP rate limiting is provided as reverse-proxy configuration, not application code.
- Full load testing at production scale is a follow-up; a loopback concurrency smoke test is included.
