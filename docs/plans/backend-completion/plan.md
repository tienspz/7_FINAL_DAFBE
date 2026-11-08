# Implementation Plan: Backend completion to 100%

**Date**: 2026-11-08 | **Spec**: [`SPEC.md`](../../../SPEC.md) FR-39, FR-47, NFR-11a, NFR-15, SI-08, SI-09, DP-01..DP-07
**Skill applied**: `backend-design` (ground in repository → contracts → failure behavior → simplest viable design → verification)
**Status**: complete; final hardening and Docker deployment verification recorded in §11

## 1. What "100%" means here

The existing `backend/` service (commit `9b7bf48`) already serves the snapshot, verifies checksums, exposes SSE, runs a freshness scheduler, and dispatches `workflow_dispatch`. Three kinds of gap remain:

1. **Spec-mandated artifacts that do not exist yet**: `.github/workflows/ci.yml` (DP-04). The Vercel-side `api/health.ts` + `vercel.json` (DP-02, DP-05, NFR-11a) were explicitly descoped by the operator in this session; the daemon's `CRON_SECRET`-protected `/api/refresh` remains the trigger surface.
2. **Runtime gaps that only appear under real operation**: the refresh job reports success before a GitHub crawl finishes; a successful refresh does not notify SSE clients that a new snapshot exists; no graceful `SIGTERM`; local pipeline output is buffered in memory with no log; no request timeout or SSE subscriber cap; manifest is re-read and re-parsed on every request.
3. **Unverified paths at planning time**: local crawl mode (no `SEC_USER_AGENT`), the Vercel function (descoped), and a container image (Docker daemon stopped). All three are resolved or explicitly descoped in §11.

Everything below is additive. The pipeline, its data, its acceptance thresholds, and the published JSON contracts are not modified by the backend (CR-07, NFR-15).

## 2. Current-state evidence

| Evidence | Result |
|---|---|
| `python -m pytest -q` | 146 passed, 24 pre-existing warnings |
| `python -m pytest tests/test_backend_*.py -q` | 44 passed |
| Live smoke on `v20261106.7` | `/api/health` `ok`, checksum OK, 11 files; manifest + dataset `ETag`; SSE `ready` |
| GitHub `workflow_dispatch` through `/api/refresh` | run `42451335920` success, crawl `v20261106.7` |
| Forced data sync | run `42451727221` success, commit `e341029`; local `main` synced |
| Local pipeline refresh through `/api/refresh` | **verified**: real crawl `v20261106.8`, then `v20261106.9` with SSE evidence (§11) |
| `ci.yml` | **present**; CI run `42456772904` success (§11) |
| `api/health.ts`, `vercel.json` | **descoped by operator** (Vercel not used) |
| Container build | **verified**: image built, ran non-root, `HEALTHCHECK` healthy (§11) |

## 3. Use cases and contract delta

Ownership stays: pipeline owns crawling/verification/writing; `backend/` owns serving, freshness, refresh orchestration, notification. There is no Vercel-side function in this scope.

| Use case | Actor | Current behavior | Required behavior |
|---|---|---|---|
| Frontend learns that new data exists after a refresh | Browser (SSE) | `refresh_finished` only; `snapshot` arrives on the next scheduler tick (≤ 15 min) or never with `--no-auto-refresh` | On a refresh that produced a new manifest signature, publish `snapshot` immediately and include `snapshot_version` in `refresh_finished` |
| Ops restarts the service (deploy/`SIGTERM`) | systemd/Docker | Python default termination; refresh child may be orphaned | `SIGTERM`/`SIGINT` → stop scheduler, stop accepting, terminate the pipeline child tree, exit 0 |
| Ops debugs a failed local crawl | Ops | 400-char stdout/stderr tail, rest discarded | full output streamed to `logs/backend-refresh-<job>.log`; health/detail exposes the path and the tail |
| Monitor probes the API | uptime checker | `GET` only | `HEAD` mirrors `GET` headers with no body; unsupported verbs return `405` + `Allow` |
| GitHub crawl completion | Scheduler/frontend | `succeeded` means "dispatch accepted" | poll the dispatched run to `completed`; report conclusion, run id, elapsed; failure is a failure |
| Many browsers connect | Browser | unbounded SSE subscribers/threads | cap via `AICOR_MAX_SSE_SUBSCRIBERS` (default 128), `503` beyond it |
| Dataset path is a symlink pointing outside the snapshot | Attacker/corrupt manifest | only checksum is checked | resolved path must stay inside `AICOR_DATA_DIR`; otherwise `502`/integrity problem |
| Frontend reads `/api/latest` | Browser | `overview`/`decision` are embedded without a checksum check | only documents whose bytes match the manifest checksum are embedded; a tampered document is omitted and `freshness.checksum_ok` is false |

## 4. Key decisions and trade-offs

1. **Daemon-only trigger surface (descoped Vercel function).** The operator does not use Vercel Functions; `CRON_SECRET`-protected `GET|POST /api/refresh` plus the in-process scheduler cover FR-47 and DP-05. This is an accepted scope decision, recorded rather than silently dropped.
2. **Poll the dispatched GitHub run instead of trusting `204`.** `workflow_dispatch` returns before the crawl runs. Polling gives the scheduler and the frontend a truthful terminal state. Bounded by `AICOR_REFRESH_TIMEOUT_SECONDS` (default 2100 s) and a 20 s poll interval; a timeout is `failed`, never `succeeded`. Cost: one extra API read per 20 s while a crawl runs, on a token that already has `actions:write`.
3. **Publish `snapshot` from the refresh runner, not only the scheduler.** The refresh is the event the client cares about; waiting up to one interval is a correctness gap, not a nicety. Signature-based comparison keeps it idempotent.
4. **Cache the parsed manifest keyed by `(st_mtime_ns, st_size)`.** The manifest is small but read on every request including datasets. Invalidation by stat keeps a pipeline write visible on the next request while removing repeated parse/JSON work. Integrity results keep the existing stat-keyed cache.
5. **Stream the pipeline output to a file.** Capturing 30 minutes of crawl logs in memory is a leak risk; a bounded tail still gives operators a useful failure detail.
6. **Symlink containment check.** Checksum equality alone does not prevent a manifest entry (or a checked-in symlink) from pointing outside the data directory.
7. **Dockerfile is written now, verified only if the daemon is available.** It is 20 lines and it is the artifact that makes "chạy ngầm" portable; an unverified build is reported as unverified rather than claimed.
8. **Verify every dataset read, including `/api/latest`.** `SnapshotStore.read_dataset` checks the manifest digest before returning bytes, so `overview`/`decision` embedded in `/api/latest` cannot bypass the integrity check. The `/api/data/*` route already returned `502`; the convenience endpoint now omits a tampered optional document instead of serving it.
9. **Escalate POSIX timeout kills to the process group.** `SIGTERM` is sent first; if the pipeline ignores it for 5 s, `SIGKILL` is sent to the same process group so grandchildren cannot survive a timeout.

## 5. Implementation steps

### Phase 1 — Contract correctness

- **Step 1.1 Snapshot cache + path containment** (`backend/snapshot.py`)
  - Cache `(manifest_bytes, parsed manifest, files, checksums, integrity)` by `(mtime_ns, size)`; keep per-file checksum cache.
  - `_check_file` and `read_dataset` resolve the path and reject anything outside `data_dir` (integrity problem / `None`).
  - `read_dataset` verifies the manifest checksum before returning bytes; `read_json` therefore refuses tampered documents too.
- **Step 1.2 HTTP semantics** (`backend/server.py`)
  - `HEAD` for `/`, `/api/health`, `/api/manifest`, `/api/latest`, `/api/data/*`, `/api/events`(headers only).
  - `405` + `Allow` for other verbs and wrong-verb routes; keep `OPTIONS`.
  - `self.timeout = 30` (socket timeout) and `AICOR_MAX_SSE_SUBSCRIBERS` cap with `503 sse_capacity`.
  - Health adds `service.started_at`/`uptime_seconds` and `events.capacity`; no secret in any payload.
- **Step 1.3 Refresh completion semantics** (`backend/runner.py`)
  - `RefreshRunner` takes `on_refresh_complete` (or `snapshot_version` supplier) and publishes `snapshot` when the manifest signature changed.
  - `refresh_finished` gains `snapshot_version` and `target`; `succeeded` for GitHub means the run actually completed.

### Phase 2 — Reliability for 24/7 operation

- **Step 2.1 Local dispatcher** (`backend/runner.py`)
  - Stream to `logs/backend-refresh-<job>.log` (created under `PROJECT_ROOT/logs`, already gitignored), keep a 400-char tail in `detail`, and expose `log_path`.
  - Start a new process group/session; on timeout or shutdown terminate the whole tree (`SIGTERM`, then `SIGKILL` to the group after 5 s on POSIX), then report `failed` with `timed_out`.
- **Step 2.2 GitHub dispatcher polling** (`backend/runner.py`)
  - After `204`, resolve the newest `workflow_dispatch` run created at/after the dispatch request (branch filter), poll `actions/runs/{id}` until `completed` or timeout; map `conclusion`.
  - Bounded retry (2 attempts, 1 s/2 s backoff) for network/5xx/429; never on 401/403/404.
- **Step 2.3 Graceful shutdown** (`backend/__main__.py`, `backend/scheduler.py`)
  - Install `SIGTERM`/`SIGINT`, call `server.shutdown()` from a helper thread, `scheduler.stop()`, `runner.stop()` (terminates an in-flight local child), `server.server_close()`; log one structured shutdown line.

### Phase 3 — Spec artifacts

- **Step 3.1 `.github/workflows/ci.yml`** (DP-04) — Python 3.14, `pip install -r requirements.txt`, `python -m compileall -q backend pipeline scripts`, `python -m pytest -q`; no data commit, no secrets required.
- **Step 3.2 Container** — `Dockerfile` (python:3.14-slim, non-root user, `HEALTHCHECK` on `/api/health`, `CMD ["python","-m","backend"]`), `.dockerignore`.
- **Step 3.3 Operator surface** — `.env.example` (new names only), README sections for `SIGTERM`, log path, SSE cap, refresh completion semantics.

### Phase 4 — Verification

1. Unit/integration tests for every new behavior (cache invalidation, HEAD, 405/Allow, SSE cap, symlink escape, post-refresh snapshot event, GitHub poll success/timeout, process-tree kill, graceful shutdown, health.ts auth/freshness/dispatch).
2. Full suite `python -m pytest -q` and `node --test`.
3. Local real crawl through `POST /api/refresh` in local mode with a real `SEC_USER_AGENT`; confirm a new snapshot version, checksum OK, SSE `snapshot` event, and acceptance report.
4. Live HTTP smoke on the resulting snapshot (health/manifest/dataset/SSE/401/503/409).
5. GitHub mode: dispatch through `/api/refresh` with `GITHUB_TOKEN_DISPATCH`, confirm polling reaches `completed`/`success` and the backend reports the run id.
6. Push and confirm `ci.yml` + `hourly-crawl.yml` runs are green; sync the data commit back.
7. Docker: build + run + health probe; `HEALTHCHECK` must reach `healthy`.

## 6. Failure behavior (delta)

| Failure | Response / state |
|---|---|
| Manifest rewritten during a request | next `load()` sees the new `(mtime, size)`, cache invalidated, new bytes/checksums used |
| Manifest entry resolves outside `data_dir` | integrity problem; dataset `404`/`502`, never served |
| Pipeline child exceeds timeout | whole tree terminated, refresh `failed`, `detail` includes `timed_out`, log path preserved |
| GitHub run ends `failure`/`cancelled` | refresh `failed` with conclusion + run id, no `snapshot` event |
| GitHub run never completes before timeout | refresh `failed` (`GitHub run did not complete within …s`), old snapshot kept |
| `/api/latest` optional document fails its checksum | document omitted; `freshness.checksum_ok=false` and the problem is listed; verified documents still served |
| POSIX pipeline ignores `SIGTERM` | after 5 s the process group is `SIGKILL`ed; refresh `failed` with `timed_out` |
| SSE capacity reached | `503 sse_capacity`, existing streams unaffected |
| `SIGTERM` during a refresh | scheduler stops, child tree terminated, process exits 0 (systemd/Docker restart-safe) |

## 7. Testing strategy

- **appType**: long-running HTTP service + one serverless function.
- **Critical journeys**: health states, ETag/304, checksum mismatch, unknown/unsafe/symlink dataset, refresh auth/single-flight, GitHub dispatch + run completion, SSE ready/snapshot/heartbeat, graceful shutdown.
- **primaryValidationStack**: pytest with fixture snapshots in `tmp_path` and a real loopback server on port 0; Node 26 `node --test` for the TS function; live loopback smoke; real crawl; GitHub Actions.
- **Test data**: synthetic manifests/files only; no financial value asserted; `SEC_USER_AGENT` comes from the environment, never committed.
- **Known gaps**: the Vercel-side `api/health.ts`/`vercel.json` are descoped by operator decision, so DP-02/DP-05/NFR-11a are met by the daemon only. Docker build/run and a real local crawl were verified.

## 8. Inputs required from the user

| Input | Why | If not provided |
|---|---|---|
| `SEC_USER_AGENT` = project name + real contact email | SEC blocks requests without it; the local crawl path cannot be exercised | provided in the earlier verification session; the final Docker verification used a fake pipeline, so set it before a real crawl |
| ~~Vercel project/URL~~ | descoped: operator does not use Vercel Functions | n/a (scope decision) |
| Docker Desktop running | verifies the container build/run | available; the final image was built and verified locally |
| Docker registry/repository + login | pushes the verified image to a registry for remote deployment | image stays local; the local build/run evidence remains valid |
| `CRON_SECRET`, `AICOR_ALLOWED_ORIGINS` | protects `/api/refresh` and allows the real frontend origin in production | refresh endpoint stays `503`/disabled and only loopback dev origins are allowed |

## 9. Risks and mitigations

- **GitHub polling adds latency to `succeeded`** → poll interval 20 s, timeout configurable; dispatch acceptance is still visible in `detail`.
- **Cache could hide a same-size, same-mtime rewrite** → mtime precision is `st_mtime_ns`; combined with size this is the same signal the scheduler already uses; a manifest rewrite that preserves both is not a realistic pipeline behavior.
- **Vercel Hobby cron limits** → daily schedule; README documents the plan limit and how to change it.
- **Vercel function bundle** → `includeFiles` for `web/public/data/**`; verified by test reading the real manifest via the same path logic.
- **Windows process-tree kill** → POSIX uses `killpg`, Windows uses `taskkill /T /F`; both covered by a timeout test.
- **No weakening of acceptance** → all new code is read-only toward data; tests never assert invented financial values.

## 10. Task breakdown

### Phase 1
- [x] T101 snapshot cache + symlink containment + tests
- [x] T102 HEAD/405/Allow, socket timeout, SSE cap, health uptime + tests
- [x] T103 refresh publishes `snapshot`, `refresh_finished` carries version + tests

### Phase 2
- [x] T201 streamed pipeline log + tree kill + tests
- [x] T202 GitHub run polling + retry + tests
- [x] T203 graceful shutdown + tests

### Phase 3
- [x] T301 `.github/workflows/ci.yml`
- [x] T302 `Dockerfile` + `.dockerignore`
- [x] T303 `.env.example` + README

### Phase 4
- [x] T401 full pytest + compileall
- [x] T402 local real crawl through `/api/refresh` (needs `SEC_USER_AGENT`)
- [x] T403 live HTTP/SSE smoke on the new snapshot
- [x] T404 GitHub mode completion polling verified live
- [x] T405 push + CI green + data sync
- [x] T406 Docker build/run (daemon available)

### Phase 5 — Final hardening and Docker deployment verification
- [x] T501 verify `/api/latest` documents against manifest checksums; add tamper tests
- [x] T502 escalate a POSIX timeout to `SIGKILL` on the process group; add a Linux-only test
- [x] T503 rebuild the image and verify live HTTP/SSE, refresh completion, graceful stop, in-flight cancellation and force-kill

## 11. Execution results

Verified in this change set (local Windows, Python 3.14.7, Node not required after the Vercel descope):

- **Code**: `backend/{snapshot,runner,server,settings,__main__}.py`, `tests/test_backend_{snapshot,runner,server,main}.py`, `.github/workflows/ci.yml`, `Dockerfile`, `.dockerignore`, `.env.example`, `README.md`.
- **Tests**: final run `python -m pytest -q` → **166 passed, 2 skipped** (24 pre-existing warnings). The two Windows skips are symlink creation and POSIX process-group semantics; the Linux-only variants passed inside the container (symlink escape, tampered `/api/latest`, SIGTERM-ignoring process group, force-kill).
- **Local crawl #1** (found the wiring gap): `POST /api/refresh?reason=local-crawl-verification` → `202` job `job_22ffccdd8579`, `succeeded` in 58 s, exit 0, snapshot `v20261106.8`; it exposed that `__main__` built the runner without `snapshot_reader` (no `snapshot_version`), which is now fixed and covered by `tests/test_backend_main.py`.
- **Local crawl #2 with SSE open**: job `job_11bfce1fb725`, real SEC/Yahoo crawl, events `ready → refresh → snapshot (v20261106.9, changed=true) → refresh_finished`; the final event carried `snapshot_version v20261106.9`, exit 0, log `logs/backend-refresh-job_11bfce1fb725.log`; `/api/health` then reported `ok`, `checksum_ok=true`, 11 files, no problems, `quality_mode=label_low`, 79 tests.
- **GitHub mode through the backend**: `POST /api/refresh?reason=github-poll-verification` with `GITHUB_TOKEN_DISPATCH` + `AICOR_GITHUB_REPOSITORY` → `202` job `job_29afe9884514`; backend polled run `42457072244` to `completed: success` in 165 s, reported `run_id=42457072244`, `target=github`, `snapshot_version v20261106.9`. No data commit was produced (remote `main` stayed at `547212f`). Token was read from Git Credential Manager into the process env only; it is not printed, logged, or committed.
- **Push and CI**: `4aab3d8..547212f`; CI run `42456772904` **success**; hourly crawl run `42456772923` **success**; data commit `d0b385b` (`v20261106.9`); local/remote `0/0`. A later `git fetch` after the dispatch run still showed `0/0`.
- **Docker**: final image `aicor-backend:verify` (`sha256:299708a9bf18…`, 2026-11-08T07:39:26Z) rebuilt from the current source; it runs as `uid=10001(aicor)`, `HEALTHCHECK` reached `healthy`, and the container served `v20261106.9` with `checksum_ok=true`, 11 files, no problems. Live contract checks passed for health, manifest/ETag/304, latest, dataset/ETag/304, unknown/traversal 404, HEAD/405/`Allow`, refresh auth 401, CORS/preflight and SSE `ready`; the `503 refresh_disabled` path remains covered by unit tests.
- **Docker refresh + SSE**: fake local pipeline through `POST /api/refresh` → `202`; SSE order `ready → refresh → snapshot → refresh_finished`; final status `succeeded`, exit 0, `snapshot_version v20261106.9`, and `/app/logs/backend-refresh-<job>.log` contained the pipeline output.
- **Docker shutdown**: final image `docker stop` with no refresh exited 0 in **0.66 s** and logged `{"service": "aicor-backend", "event": "stopped"}`. `docker stop` during an in-flight fake pipeline (sleep 300) exited 0 in **0.74 s**; the child process was gone, so `runner.stop()` cancelled the tree rather than waiting for the timeout.
- **Docker force-kill**: a fake pipeline that ignores `SIGTERM` with `AICOR_REFRESH_TIMEOUT_SECONDS=1` was `SIGKILL`ed after the 5 s grace period; `/api/health` reported `failed` with `pipeline timed out after 1s: fake pipeline ignoring SIGTERM`, and only the backend process remained.
- **Docker tamper guard**: mounting a synthetic snapshot with a tampered `overview.json` made `/api/latest` return `checksum_ok=false`, omit `overview`, keep the verified `decision`, and list `overview.json does not match its manifest checksum`.
- **HTTP semantics** (unit/integration): `HEAD /api/manifest` mirrors headers with no body and a real `Content-Length`; `HEAD /api/refresh` → `405` + `Allow` and starts no job; `DELETE /api/refresh` → `405` + `Allow`; the 129th SSE subscriber → `503 sse_capacity`; manifest body is read once per stat signature and re-read after a rewrite.

Unverified / limitations:

- The Vercel-side `api/health.ts` + `vercel.json` are **not implemented** (operator descoped Vercel in this session), so DP-02/DP-05/NFR-11a are covered only by the daemon.
- The final image is verified locally in Docker Desktop; it has **not been pushed to a registry** or deployed to a remote host. A registry push needs the target repository and credentials.
- A real SEC crawl was not rerun in this final session because `SEC_USER_AGENT` is not set in the environment; the real-crawl evidence from the earlier session remains valid, and the Docker refresh path was exercised with a fake pipeline so no source was crawled.
- Windows skips symlink creation; the Linux container ran the symlink-escape test and it passed.
- No performance/load measurement was made for the manifest cache or the SSE cap.
