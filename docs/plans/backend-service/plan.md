# Implementation Plan: Backend runtime service (API, freshness, realtime)

**Date**: 2026-11-08 | **Spec**: [`SPEC.md`](../../../SPEC.md) FR-39, FR-47, NFR-11a, NFR-15, SI-08, SI-09, DP-01..DP-07
**Skill applied**: `backend-design` (boundaries → contracts → failure behavior → simplest viable design)
**Status**: plan approved by task scope; implementation and verification follow in this change set

## Summary

The repository currently ends at a published artifact: `pipeline.run` crawls and writes `web/public/data/*.json`, and GitHub Actions commits it. There is no running backend, so nothing can report data age, trigger a refresh, or push an update to a browser.

This plan adds one backend runtime, `backend/`, that:

1. serves the published dashboard snapshot over HTTP with an explicit freshness contract;
2. keeps the snapshot current from a **background scheduler** (auto-refresh when `generated_at` is older than the stale window, or when the manifest is missing);
3. pushes changes to any connected frontend over **Server-Sent Events**, so a Vercel-hosted page updates without a reload or a cache-busting build;
4. exposes a `CRON_SECRET`-protected refresh endpoint for Vercel Cron or an external scheduler.

Published data stays pipeline-owned and immutable from the backend's point of view. No financial value is computed, rewritten, or invented by the service (CR-07).

## Technical Context

**Language/Version**: Python 3.14, standard library only (no new dependency, no `package.json`)
**Primary dependencies**: existing `PyYAML` only through `pipeline.util`; backend imports `pipeline.util.utc_now_iso`, which is stdlib-only
**Data source of truth**: `web/public/data/manifest.json` + the JSON files and checksums it lists
**Existing consumers**: none yet (`web/` contains only `public/data/`); the contract is written for the future Vite/React app in the SPEC
**Target platform**: local Windows/Linux process, container or VM; persists across deploys
**Constraint**: Vercel serverless functions cannot host a daemon, an SSE stream, or a 30-minute crawl, so the runtime is a standalone service rather than `api/*.ts`

## Constitution Check

No `constitution.md` exists. Repository constraints apply:

- Verified source data and provenance are never rewritten by the backend — **PASS**.
- Existing pipeline, acceptance, and SQLite contracts are untouched — **PASS**.
- Missing or corrupt data is reported as `degraded`/`unavailable`, never silently replaced — **PASS** (NFR-15).
- No credential is echoed in a response, log line, or error detail — **PASS** (NFR-08).
- No fabricated market or financial values in code or tests — **PASS** (CR-07); tests use synthetic fixture snapshots.

## Use cases and boundaries

| Use case | Actor | Contract |
|---|---|---|
| Is the dashboard data current? | Frontend / ops | `GET /api/health` → snapshot version, `data_as_of`, age, stale flag, checksum status, refresh job state, SSE subscriber count |
| Load the snapshot | Frontend | `GET /api/manifest`, `GET /api/data/<dataset>`; no-stale caching, `ETag` revalidation, checksum verified before serving |
| Show the newest numbers immediately | Frontend | `GET /api/latest` (freshness + manifest + overview + decision) and `GET /api/events` (SSE) |
| Refresh on schedule or on demand | Scheduler / Vercel Cron / ops | `GET|POST /api/refresh` with `Authorization: Bearer $CRON_SECRET` (or `X-Cron-Secret`) |
| Recover from a missing or corrupt snapshot | Scheduler | auto-trigger refresh; `/api/health` returns `503 unavailable` only when no manifest exists |

**Ownership boundary**: the backend owns *serving, freshness evaluation, refresh orchestration, and notification*. The pipeline owns *crawling, verification, computation, and snapshot writing*. The backend never writes `web/public/data`.

## API contract

| Route | Success | Failure behavior |
|---|---|---|
| `GET /api/health` | `200` `status` = `ok` \| `degraded` | `503` `unavailable` when `manifest.json` is missing/unreadable |
| `GET /api/manifest` | `200` raw manifest bytes, `ETag`, `X-AICOR-Snapshot` | `304` on `If-None-Match` match; `503` when unavailable |
| `GET /api/latest` | `200` `{freshness, manifest, overview?, decision?}` | `503` when unavailable; missing optional files are omitted, never faked |
| `GET /api/data/<key>` | `200` file bytes, `ETag`, `X-AICOR-Snapshot` | `404` unknown key or unsafe name; `502 checksum_mismatch`; `503` unreadable |
| `GET /api/events` | `200 text/event-stream`; events `ready`, `snapshot`, `refresh`, `refresh_finished`, `scheduler_error` | heartbeat comment `: keep-alive` every `AICOR_SSE_HEARTBEAT_SECONDS` |
| `GET\|POST /api/refresh` | `202` accepted, `409` already running | `401` bad/missing secret; `503 refresh_disabled` when `CRON_SECRET` unset |

All responses are `Cache-Control: no-store` except `manifest`/dataset responses, which use `no-cache, must-revalidate` plus `ETag` so a browser revalidates instead of showing a stale snapshot (FR-39, NFR-15).

CORS is an explicit allowlist (`AICOR_ALLOWED_ORIGINS`, default loopback dev origins). The Vercel deployment origin is added by configuration, not by trusting every `Origin`.

## Key decisions and trade-offs

1. **Standalone Python service instead of Vercel functions.** A daemon, an open SSE stream, and a 30-minute crawl exceed serverless limits (NFR-03). The frontend on Vercel calls the service origin; deployment stays independent of Vercel builds.
2. **SSE instead of WebSocket.** The stream is server→client, read-only, and reconnects automatically with `retry`. No handshake, no message protocol, no auth token in the URL. Polling remains possible for clients without `EventSource`.
3. **Refresh through the existing pipeline entrypoint.** Local mode runs `python -m pipeline.run --mode full` as a subprocess; GitHub mode calls `workflow_dispatch` (SI-09) when `GITHUB_TOKEN_DISPATCH` and `AICOR_GITHUB_REPOSITORY` exist. Both go through one single-flight guard, so overlapping crawls are impossible (DP-03).
4. **Trust the manifest, verify the bytes.** A dataset is served only after its SHA-256 matches the manifest checksum (CR-11 style). A mismatch is a `502`, not a silent serve of unverified numbers.
5. **Staleness is a timestamp question, not a market-calendar question.** `generated_at` + configurable window is deterministic and testable; FR-47 scheduling stays in the scheduler/CI.
6. **No new persistence layer.** The JSON snapshot is already the consumer contract and the SQLite file is the pipeline's handoff (FR-46). Adding a database would duplicate state and break reproducibility.

## Implementation steps

### Step 1 — Snapshot and freshness layer (`backend/snapshot.py`)

- **Requirements**: FR-39, NFR-15, CR-11
- Load `manifest.json`, expose version/run/`data_as_of`/`generated_at`, map dataset keys to safe relative paths, verify checksums with a stat-keyed cache, and compute age/stale/integrity problems without raising.

### Step 2 — Realtime broker (`backend/events.py`)

- **Requirements**: FR-39
- Thread-safe in-process pub/sub with bounded per-subscriber queues (drop oldest on overflow) so one slow client cannot block a refresh or exhaust memory.

### Step 3 — Refresh orchestration (`backend/runner.py`)

- **Requirements**: FR-47, SI-09, DP-03, DP-05, NFR-11a
- Single-flight `RefreshRunner` with injectable dispatcher; local subprocess dispatcher with timeout and output tail; GitHub `workflow_dispatch` dispatcher with token only in an `Authorization` header; sanitized failure details; `refresh`/`refresh_finished` events.

### Step 4 — Freshness scheduler (`backend/scheduler.py`)

- **Requirements**: FR-47, FR-39
- Daemon thread that ticks every `AICOR_REFRESH_INTERVAL_SECONDS`, publishes `snapshot` when the manifest signature changes, and triggers `missing-snapshot` / `stale-snapshot` refreshes unless one is already running.

### Step 5 — HTTP/SSE server (`backend/server.py`, `backend/__main__.py`)

- **Requirements**: NFR-11a, SI-08, DP-05
- `ThreadingHTTPServer` with the routes above, CORS allowlist, constant-time secret comparison, `ETag`/`304`, checksum-verified dataset serving, SSE heartbeats, request logging without payloads.

### Step 6 — Operator surface

- `.env.example` with names only (DP-06), `README.md` run/integration section, this plan.

## Project structure

```text
backend/
  __init__.py
  settings.py       # env-driven config, secrets excluded from public_dict
  snapshot.py       # manifest loading, dataset resolution, checksum verification, freshness
  events.py         # bounded SSE pub/sub broker
  runner.py         # single-flight refresh, local subprocess / GitHub dispatch
  scheduler.py      # background freshness loop
  server.py         # HTTP + SSE handler, routes, CORS, auth
  __main__.py       # `python -m backend`
tests/
  test_backend_snapshot.py
  test_backend_runner.py
  test_backend_scheduler.py
  test_backend_server.py
docs/plans/backend-service/plan.md
.env.example
```

## Testing strategy

- **appType**: long-running HTTP service over a static JSON contract.
- **Critical journeys**:
  1. Health reports fresh → `ok`, stale → `degraded`, missing → `503 unavailable`.
  2. Manifest/dataset `ETag` revalidation and `304`; tampered dataset → `502`, never served.
  3. Refresh endpoint rejects missing/wrong secret, accepts the configured secret, returns `409` while a job runs, `503` when disabled.
  4. SSE delivers `ready` on connect and a `snapshot` event published by the scheduler/broker.
  5. Scheduler triggers on stale/missing only, waits while a refresh runs, and publishes on manifest change.
  6. Runner is single-flight, records failures without leaking a token, and builds a correct `workflow_dispatch` request.
- **primaryValidationStack**: pytest with fixture snapshots in `tmp_path`, `http.client`/`urllib` against a real loopback server on port 0, plus a live smoke run against `web/public/data`.
- **Test data**: synthetic manifests/files only; no production financial value is asserted.
- **Known gaps**: no deploy target exists in this workspace, so Vercel edge/CORS is documented, not exercised live. GitHub `workflow_dispatch` and the real crawl are verified (see Execution results); the local-mode crawler needs a real `SEC_USER_AGENT` on this machine.

## Task breakdown

### Phase 1: Foundations

- [x] T001 [Plan:1] Implement snapshot loading, dataset resolution, checksum verification, freshness payload.
- [x] T002 [Plan:2] Implement the bounded event broker.
- [x] T003 [Plan:3] Implement single-flight refresh with local and GitHub dispatchers.
- [x] T004 [Plan:4] Implement the freshness scheduler.

### Phase 2: Service surface

- [x] T005 [Plan:5] Implement HTTP + SSE routes, CORS, `ETag`, refresh auth, and `python -m backend`.
- [x] T006 [Plan:6] Add `.env.example` and the README operator section.

### Phase 3: Verification

- [x] T007 [Plan:Testing] Add tests for snapshot, runner, scheduler, and server behavior.
- [x] T008 [Plan:Testing] Run the full pytest suite, then a live loopback smoke test against the real snapshot.

## Requirement mapping

| Requirement | Description | Plan items | Evidence |
|---|---|---|---|
| FR-39 | Show last update time and data age | 1, 4, 5 | `/api/health`, `/api/latest`, SSE `ready` |
| FR-47 | Scheduled collection, manual trigger | 3, 4, 5 | scheduler loop, `/api/refresh`, `workflow_dispatch` |
| NFR-11a | Protect health/trigger with `CRON_SECRET`, least-privilege token | 3, 5 | refresh auth tests, dispatcher tests |
| NFR-15 | Keep old data, report sync failure instead of empty | 1, 3, 5 | freshness problems, `502`/`503`, failure state in health |
| SI-08 | Vercel function/cron health checks | 5, 6 | documented frontend wiring, CORS config |
| SI-09 | Vercel/server triggers GitHub `workflow_dispatch` | 3 | GitHub dispatcher + tests |
| DP-03/DP-05 | Concurrency guard, freshness-triggered refresh | 3, 4 | single-flight `409`, scheduler decisions |
| DP-06 | Env names documented, no real values | 6 | `.env.example` |
| CR-07 | No fabricated values | 1, 5 | checksum-verified serving, synthetic-only tests |

## Complexity tracking

No new runtime dependency, no schema migration, no new database. One process, one lock, one queue per subscriber.

## Execution results

- Implementation: `backend/` (8 modules, standard library only), `.env.example`, README operator section.
- `python -m pytest tests/test_backend_*.py -q`: **44 passed**.
- `python -m pytest -q` (full repository suite): **146 passed**, 24 pre-existing statistical warnings.
- Live smoke run (`python -m backend --port 8765 --no-auto-refresh`) against the published snapshot `v20261106.5`:
  - `/api/health` → `200`, `degraded` (data is 61 672 s old, past the 21 600 s window), `checksum_ok=true`, 11 files.
  - `/api/manifest` → `200` 2 468 bytes + `ETag`; revalidation → `304` with an empty body.
  - `/api/data/financials` → `200` 1 278 057 bytes with `X-AICOR-Snapshot: v20261106.5`; revalidation → `304`.
  - `/api/data/%2E%2E%2Fmanifest.json` → `404 unknown_dataset`.
  - `/api/refresh` without `CRON_SECRET` → `503 refresh_disabled` (endpoint is closed, not open); with the wrong secret → `401 unauthorized`.
- Live refresh path (`CRON_SECRET` set, pipeline command replaced by a no-op so no source was crawled):
  - `POST /api/refresh?reason=smoke-test` → `202` job `job_5bf9db42bebc`.
  - SSE subscriber received `ready` → `refresh` → `refresh_finished`; `/api/health` then reported `succeeded`.
  - Background scheduler with `--refresh-interval 1` and stale data decided `triggered` / `stale-snapshot` and the job reached `succeeded` with no manual call.
- GitHub verification (real, against `tienspz/7_FINAL_DAFBE`):
  - Push: `a5b99ec..9b7bf48` to `main`; push run `42451269146` completed **success** (unit tests, crawl, acceptance, raw archive, fingerprint, data commit steps all succeeded).
  - `workflow_dispatch` through the backend: started `python -m backend` with `GITHUB_TOKEN_DISPATCH` + `AICOR_GITHUB_REPOSITORY`, then `POST /api/refresh?reason=github-dispatch-verification` → `202` job `job_ce6a05032d88`; the job reached `succeeded` with detail `workflow_dispatch accepted` and exit `204`. Run `42451335920` (`event=workflow_dispatch`) completed **success**; its log reports `snapshot_version v20261106.7`, `facts 4677`, `prices 5964`, `79 test results`, `quality_mode=label_low`, and the acceptance step passed.
  - Forced sync: dispatch run `42451727221` with `force_commit=true` completed **success** and pushed `e341029` (`chore(data): refresh snapshot v20261106.7`); local `git pull --rebase` moved `9b7bf48..e341029`.
- Post-sync smoke against the pulled data: `/api/health` → `ok`, `v20261106.7`, `generated_at 2026-11-08T05:43:45Z`, age 229 s, `stale=false`, `checksum_ok=true`, 11 files; `/api/manifest` returned an `ETag`; SSE `ready` reported `v20261106.7`.
- Not exercised: the local-mode crawl dispatcher end to end (this machine has no `SEC_USER_AGENT`; the real crawl ran in the Actions runner via `workflow_dispatch` instead), and any Vercel deployment (no frontend project exists in this workspace).
