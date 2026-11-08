# Implementation Plan: Snapshot Freshness and Deployment Sync

**Date**: 2026-11-09 | **Spec**: [`SPEC.md`](../../../SPEC.md) (FR-39, FR-47, SI-08, DP-07) and user request

## Summary

The reported age is consistent with the currently published manifest: its
`generated_at` is `2026-11-08T06:51:43Z`; at the screenshot time
`2026-11-08T18:07Z`, that is about 11 hours. The GitHub crawl completed, but the
data-sync script can suppress an additional publish after the first commit of
the UTC day. It also fingerprints a volatile sync log. Consequently, a newer
pipeline result can be withheld from GitHub and the Vercel static snapshot while
the reload button correctly fetches the older published version.

Remove the calendar-day publishing gate and fingerprint only meaningful data
inputs, so every changed verified snapshot can be committed immediately without
hourly no-change commits. Ensure the frontend uses the freshest available
health/SSE freshness and describes reload as revalidating the published
snapshot, not as running a crawl.

## Technical Context

**Language/Version**: Python 3.14; TypeScript 5.6; React 18
**Primary Dependencies**: Existing stdlib, React, Vitest, Playwright; no new dependencies
**Data source of truth**: Successful pipeline outputs and versioned manifest under `web/public/data/`
**Testing**: Pytest for data-publish gating and backend snapshot freshness; Vitest and Playwright for frontend state/display
**Target Platform**: GitHub Actions crawl and commit to `main`; Vercel Git integration builds the frontend/static snapshot
**Performance Goals**: Publish immediately after a verified semantic change; no Vercel deploy for a no-change crawl
**Constraints**: Do not bypass acceptance checks, commit secrets, make the browser call protected crawl endpoints, or publish invalid/partial snapshots

## Constitution Check

No `constitution.md` is present. Existing project rules apply:

- Publish data only after the pipeline and acceptance check succeed — **PASS**.
- Keep provenance and snapshot checksums intact — **PASS**.
- Do not silently treat an old static snapshot as a newly completed crawl — **PASS**.
- Keep backend credentials server-side and prevent browser-triggered secret access — **PASS**.
- Commit changed data promptly while keeping unchanged runs quiet — **PASS**.

## Applied Guidelines

- Backend debugging: confirm the stale timestamp against `manifest.json`, inspect the workflow result and publishing gate, then add a targeted regression test.
- React best practices: derive displayed freshness from existing API/SSE state; avoid extra polling or full-page reloads.
- Existing deployment contract: backend freshness reflects snapshot generation; Vercel static data changes only when verified output is committed.

## Implementation Steps

### Phase 1 — Foundational sync and freshness rules

#### Step 1: Make semantic fingerprint stable (`scripts/ci_sync_data.py`)
- **Requirements**: REQ-001, REQ-002
- **Design inputs**: Existing GitHub hourly workflow and snapshot manifest
- **Description**: Remove volatile run-log data from the semantic fingerprint and remove the once-per-UTC-day commit throttle. Preserve the no-semantic-change early return, force behavior, acceptance-before-commit order, and last-commit bookkeeping.

#### Step 2: Prefer the newest health/SSE freshness (`web/src/api/freshness.ts`, `web/src/components/shell/Layout.tsx`)
- **Requirements**: REQ-003
- **Design inputs**: `web/src/api/types.ts`, `docs/api/README.md`
- **Description**: Select the newer `generated_at`; when versions share a generation timestamp, prefer the more recently calculated non-null `age_seconds`. Ensure manual health and manifest reads revalidate rather than use browser cache.

### Phase 2 — User Story 1: Show and publish the latest verified snapshot (P1)

#### Step 3: Set accurate reload feedback (`web/src/components/shell/Layout.tsx`, `web/src/components/shell/Topbar.tsx`)
- **Requirements**: REQ-003, REQ-004
- **Design inputs**: Existing refresh button and freshness indicator
- **Description**: State that the button rechecks the published snapshot, retain the stale-age warning until `generated_at` advances, and keep new-snapshot notices until successful data revalidation.

#### Step 4: Add regression tests (`tests/test_ci_sync_data.py`, `web/src/api/freshness.test.ts`, `web/src/api/client.test.ts`)
- **Requirements**: REQ-001, REQ-002, REQ-003
- **Design inputs**: Manifest fixtures and existing API tests
- **Description**: Prove a second semantic change on the same UTC day publishes; unchanged data creates no commit; volatile sync-run metadata does not force a commit; and fresh health wins over older SSE state.

### Phase 3 — Release and deployment validation

#### Step 5: Validate and synchronize (`web/`, GitHub Actions, Vercel)
- **Requirements**: REQ-002, REQ-004
- **Design inputs**: `.github/workflows/ci.yml`, `.github/workflows/hourly-crawl.yml`, Vercel Git status
- **Description**: Run pytest, frontend typecheck/unit/E2E/build, push the surgical fix, verify CI and crawl/acceptance, confirm the new manifest commit and Vercel deployment, then check the live snapshot version and age.

## Project Structure

```text
scripts/ci_sync_data.py                 # stable fingerprint and immediate changed-data publication
tests/test_ci_sync_data.py              # same-day publish/no-op regression coverage
web/src/api/client.ts                   # no-cache freshness/manifest fetch
web/src/api/client.test.ts              # no-cache request regression coverage
web/src/api/freshness.ts                # deterministic newest-freshness selection
web/src/api/freshness.test.ts           # freshness source/version tests
web/src/components/shell/Layout.tsx    # current freshness and accurate reload feedback
web/src/components/shell/Topbar.tsx    # snapshot age presentation
```

## Testing Strategy

- **appType**: SPA backed by a versioned static snapshot and separate backend
- **Critical user journeys**:
  1. A verified crawl with changed values on a UTC day that already had a data commit publishes immediately.
  2. An unchanged crawl does not create a redundant data commit.
  3. New health freshness replaces older SSE state after revalidation.
  4. Manual reload with no new published snapshot continues to show the true stale age and says it checked the published snapshot.
- **primaryValidationStack**: pytest, Vitest, TypeScript, Vite build, Playwright; GitHub Actions and Vercel check status for release
- **fallbackMatrix**:
  - `infra-tier`: synthetic pipeline/publish test → unit test of fingerprint/publish guard; no external crawl needed for local test.
  - `browser-tier`: Playwright E2E → Vitest.
- **Environment requirements**: Python and Node; GitHub repository access for publish; Vercel Git integration for remote deployment confirmation.
- **knownGaps**: A real pipeline run depends on GitHub secrets and upstream provider availability; production URL may be protected or changed.
- **Test data strategy**: Temporary Git worktree/data fixtures; synthetic manifest versions and timestamps.
- **Acceptance criteria**: Every changed accepted snapshot is committed without a daily delay; unchanged snapshots stay quiet; UI shows the newest health/SSE snapshot; manual reload never implies it started a crawl; GitHub and Vercel success plus live manifest version/age are confirmed.
- **Validation review expectations**: Check valid checksums, no secrets, fingerprint determinism, same-day update propagation, freshness source selection, and actual deployment state.

## Tasks

### Phase 1 — Foundational
- [x] T001 [Plan:1.1] Remove volatile sync-log fingerprint inputs and UTC-day commit throttle from `scripts/ci_sync_data.py`, preserving force/no-change and acceptance ordering.
- [x] T002 [P] [Plan:1.2] Add a typed freshness selector in `web/src/api/freshness.ts` and wire it into `web/src/components/shell/Layout.tsx`.
- [x] T003 [P] [Plan:1.2] Configure `fetchHealth` and static manifest fallback to bypass browser cache in `web/src/api/client.ts`.

### Phase 2 — User Story 1
- [x] T004 [US1] [Plan:2.1] Clarify reload feedback and preserve the existing accurate stale-age display in `web/src/components/shell/Layout.tsx` and `web/src/components/shell/Topbar.tsx`.
- [x] T005 [P] [US1] [Plan:2.2] Add same-day semantic commit/no-op fingerprint tests in `tests/test_ci_sync_data.py`.
- [x] T006 [P] [US1] [Plan:2.2] Add freshness source selection and non-stale-to-stale reload regression tests in `web/src/api/freshness.test.ts`, `web/src/api/client.test.ts`, and `web/e2e/resilience.spec.ts`.

### Phase 3 — Release
- [x] T007 [Plan:3.1] Run Python tests, frontend typecheck/unit/build/E2E, and inspect git diff for unintended data or secret changes.
- [ ] T008 [Plan:3.1] Push the fix to GitHub `main`; verify successful crawl/acceptance, changed snapshot publication, Vercel deployment, and live freshness before marking complete.

## Requirement Mapping

| REQ ID | Description | Plan Items | Implementation Evidence |
|--------|-------------|------------|------------------------|
| REQ-001 | Publish every semantically changed accepted snapshot without a once-per-day delay, while ignoring volatile run metadata. | 1.1, 2.2 | `scripts/ci_sync_data.py`, `tests/test_ci_sync_data.py` |
| REQ-002 | Keep unchanged data quiet and synchronize verified changes to GitHub/Vercel. | 1.1, 3.1 | workflow results, manifest commit, Vercel deployment |
| REQ-003 | Display the newest available health/SSE snapshot and the true age after manual reload. | 1.2, 2.1, 2.2 | `web/src/api/freshness.ts`, `Layout.tsx`, `Topbar.tsx`, frontend tests |
| REQ-004 | Make reload wording accurately describe revalidation, not a crawler trigger. | 2.1 | `web/src/components/shell/Layout.tsx`, E2E |
