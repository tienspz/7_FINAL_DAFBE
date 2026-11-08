# AICOR backend API contract

The backend serves the snapshot published by the pipeline and orchestrates
refreshes. It never writes pipeline data. This directory is the machine-readable
contract for frontend work:

| File | Purpose |
| --- | --- |
| [`openapi.yaml`](openapi.yaml) | HTTP routes, statuses, headers, and JSON schemas (OpenAPI 3.1) |
| [`sse-events.schema.json`](sse-events.schema.json) | SSE event payloads (JSON Schema 2020-12) |
| [`types.ts`](types.ts) | TypeScript interfaces and event union for the frontend |

The dataset document schemas themselves are owned by the pipeline acceptance
checks (`docs/` and `tests/test_acceptance_check.py`); this contract covers the
transport envelope.

## Base URL

- Local: `http://127.0.0.1:8000`
- Production: operator-provided HTTPS origin (see `deploy/README.md`)

All responses are JSON unless the path is `/api/events`.

## Endpoints

| Method | Path | Purpose | Cache |
| --- | --- | --- | --- |
| `GET` | `/` | Endpoint and dataset discovery | `no-store` |
| `GET` | `/api/health` | Freshness, refresh state, capacity | `no-store` |
| `GET` | `/api/manifest` | Published manifest | `no-cache, must-revalidate` + ETag |
| `GET` | `/api/latest` | Freshness + manifest + `overview`/`decision` | `no-store` |
| `GET` | `/api/data/{key}` | Checksum-verified dataset | `no-cache, must-revalidate` + ETag |
| `GET` | `/api/events` | SSE stream | `no-store` |
| `GET` | `/api/refresh` | Trigger a refresh (`CRON_SECRET`; for cron callers) | `no-store` |
| `POST` | `/api/refresh` | Trigger a refresh (`CRON_SECRET`) | `no-store` |

`HEAD` mirrors `GET` for the read-only routes without a body. Unsupported
methods return `405` with an `Allow` header.

### Health

`GET /api/health` returns `200` with `status=ok` or `status=degraded`, and `503`
with `status=unavailable` when no manifest can be read.

`degraded` means at least one of:

- the snapshot is older than `stale_after_seconds`;
- `generated_at` is missing or unparseable (the age is unknown, so freshness
  cannot be proven);
- a dataset listed in the manifest fails checksum verification.

A frontend should show the dashboard with a freshness warning rather than
treating `degraded` as a hard failure.

### Caching, ETag, and compression

- JSON bodies of at least 1024 bytes are gzip-compressed when the request
  accepts gzip (`Accept-Encoding: gzip`, including wildcard `*`).
- Compressible responses send `Vary: Accept-Encoding`.
- When the CORS allowlist is not `*`, every response sends `Vary: Origin`,
  including requests with no `Origin` or a disallowed origin.
- Manifest and dataset responses carry a weak ETag: `W/"<sha256>"`, derived
  from the identity body. Send it as `If-None-Match`; weak, strong, wildcard,
  and comma-separated forms are accepted and return `304` without a body.
- Do not hash the compressed bytes: the ETag is the same for identity and gzip
  representations.

`fetch` in browsers handles gzip transparently. Read `X-AICOR-Snapshot` to learn
which snapshot version produced the response, and `ETag` for revalidation.

### Errors

```json
{ "error": "unknown_dataset", "datasets": ["financials", "overview"] }
```

| Status | Error codes |
| --- | --- |
| `401` | `unauthorized` |
| `404` | `not_found`, `unknown_dataset` |
| `405` | `method_not_allowed` |
| `409` | refresh conflict (`status=conflict`) |
| `502` | `checksum_mismatch` |
| `503` | `snapshot_unavailable`, `dataset_unreadable`, `refresh_disabled`, `sse_capacity` |

Error bodies never contain credentials or raw pipeline output.

### Refresh authorization

`GET /api/refresh` and `POST /api/refresh` both trigger a refresh and require
`CRON_SECRET`:

```http
Authorization: Bearer <CRON_SECRET>
```

or:

```http
X-Cron-Secret: <CRON_SECRET>
```

Only one refresh runs at a time. `202` returns the accepted `RefreshState`;
`409` returns the in-flight state. The browser should not hold the secret; in
production the frontend triggers refreshes through an authenticated server-side
route or the scheduler, not by embedding `CRON_SECRET` in client code.

## SSE contract

Connect to `GET /api/events` with `Accept: text/event-stream`. The server sends
`Content-Type: text/event-stream`, `retry: 3000`, and then:

| Event | Payload | Meaning |
| --- | --- | --- |
| `ready` | `{ snapshot: Freshness, refresh: RefreshState, heartbeat_seconds: number }` | Initial state after connecting |
| `snapshot` | `{ snapshot: Freshness, changed: boolean }` | New or resynchronized snapshot state |
| `refresh` | `RefreshState` | A refresh started |
| `refresh_finished` | `RefreshState` (including `snapshot_changed`) | A refresh finished |
| `scheduler_error` | `{ error: string }` | The freshness loop caught an exception |

Wire format:

```text
retry: 3000

event: ready
data: {"snapshot":{...},"refresh":{...},"heartbeat_seconds":15}

event: snapshot
data: {"snapshot":{...},"changed":true}

event: refresh_finished
data: {"status":"succeeded","snapshot_changed":true,...}
```

Every `snapshot` event has the same envelope regardless of producer (refresh
runner, scheduler, or heartbeat resync). Read `payload.snapshot.*`
consistently; do not expect the freshness fields at the top level.

If no event is available for `heartbeat_seconds`, the server sends a
`snapshot` event with `changed=false` instead of a bodyless comment. A client
that missed an earlier event therefore recovers on the next heartbeat.

### Recommended client protocol

1. On load, call `/api/latest` (and `/api/health` if you need refresh state).
2. Open `/api/events`; replace state from `ready`.
3. On `snapshot`, compare `snapshot.snapshot_version` with the version already
   rendered. Refetch documents only when it differs, or when
   `snapshot.checksum_ok` changes.
4. On `refresh`, show progress from `RefreshState`.
5. On `refresh_finished`, if `status=succeeded` and `snapshot_changed=true`,
   expect a `snapshot` event and refetch. If `snapshot_changed=false` in GitHub
   mode, the served data did not change (see the deployment caveat below).
6. Reconnect with backoff; the browser `EventSource` honors `retry: 3000`.
   Always resynchronize from `ready` after a reconnect.

`changed` is producer-relative: it means the producer observed a different
version than its previous event. It is not a global sequence number. Version
comparison is the idempotence rule.

## GitHub dispatch caveat

`GITHUB_TOKEN_DISPATCH` mode dispatches the workflow and polls it, but the
workflow commits data to the repository; that does not update the daemon's
`AICOR_DATA_DIR` by itself. Configure `AICOR_POST_REFRESH_COMMAND` (for example
`git pull --ff-only`) or an external sync. Check
`/api/health` → `config.post_refresh_configured`. Local pipeline mode with a
persistent volume is the default production path.

## Examples

```bash
curl -s http://127.0.0.1:8000/api/health | jq '.status, .snapshot.snapshot_version'

curl -sD - -o /tmp/financials.gz \
  -H 'Accept-Encoding: gzip' \
  http://127.0.0.1:8000/api/data/financials

curl -s http://127.0.0.1:8000/api/events -N
```
