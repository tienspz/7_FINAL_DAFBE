# Implementation Plan: AICOR Manual Data Reload

**Date**: 2026-11-09 | **Spec**: [`SPEC.md`](../../../SPEC.md) (FR-39, FR-47, SI-08, DP-07) and user request

## Summary

Add a persistent reload control to the AICOR top bar so users can revalidate the
currently displayed snapshot on demand. The control refreshes mounted datasets
and freshness through the existing backend API/SSE and static fallback, shows
progress and errors accessibly, and indicates when SSE detects a newer snapshot.
It resets the in-memory snapshot boundary before revalidation so newly published
versions are accepted consistently. It does not invoke the protected crawl
endpoint from the browser or expose `CRON_SECRET`.

The backend already provides checksum-verified datasets, ETag revalidation,
health/freshness, and snapshot SSE events. The change should reuse those
contracts and avoid a new backend endpoint unless implementation evidence shows
the current contract cannot satisfy the behavior. After validation, publish the
feature through GitHub and verify the configured Vercel deployment path.

## Technical Context

**Language/Version**: TypeScript 5.6, React 18, Python 3.14 backend
**Primary Dependencies**: React, lucide-react, Vitest, Playwright; no new dependencies
**Storage**: Existing versioned JSON snapshot under `web/public/data/`, served by the backend or static fallback
**Testing**: Vitest API tests, TypeScript typecheck, Vite production build, Playwright E2E, existing Python backend tests if backend code changes
**Target Platform**: Vercel static frontend (`web/` project root, `dist` output); standalone backend is separately operated
**Performance Goals**: Revalidate only mounted page datasets and health; do not reload the whole document for an in-app refresh
**Constraints**: Preserve ETag/checksum validation and SSE behavior; never put refresh credentials in frontend code; preserve current page and query filters; surface fetch failures rather than reporting false success

## Constitution Check

No `constitution.md` is present in the workspace. The plan follows the existing
repository contracts:

- The pipeline remains the owner of crawling and snapshot creation — **PASS**.
- The backend remains a read/freshness/SSE service; browser refresh reads only — **PASS**.
- `CRON_SECRET` and GitHub dispatch credentials stay server-side — **PASS**.
- Existing ETag, snapshot-version, checksum, and static fallback behavior is preserved — **PASS**.

## Applied Guidelines

- React best practices: use the existing state/data hooks and event-driven refresh, avoid a document reload and redundant full-page remounts.
- Existing AICOR API contract: revalidate through `/api/data/{key}` and `/api/health`; use the SSE snapshot version only as a signal that data may be newer.
- Existing deployment guidance: Vercel hosts the frontend only; it does not host the long-running Python/SSE backend.

## Implementation Steps

### Phase 1 — Foundational refresh behavior

#### Step 1: Register mounted data loaders (`web/src/data/hooks.ts`)
- **Requirements**: REQ-002
- **Design inputs**: Existing API client ETag/fallback logic in `web/src/api/client.ts`; backend API contract in `docs/api/README.md`
- **Description**: Provide a single application-level refresh operation that revalidates mounted page datasets and health, retains the active route and filters, deduplicates overlapping requests, and returns failures to the caller while preserving each hook's error state.

### Phase 2 — User Story 1: Manually refresh the current dashboard (P1)

#### Step 2: Add persistent reload control and feedback (`web/src/components/shell/Topbar.tsx`, `web/src/components/shell/Layout.tsx`)
- **Requirements**: REQ-001, REQ-002
- **Design inputs**: Existing `IconButton`, `Tooltip`, `Freshness`, and top-bar new-snapshot notice
- **Description**: Always show an accessible reload icon. Disable it while refreshing; expose busy state and a result/error status; retain the new-data notice until a successful revalidation. A click refreshes current data without a full-page navigation.

#### Step 3: Verify realtime notice and failure handling (`web/src/api/sse.ts`, `web/src/api/client.test.ts`, frontend tests)
- **Requirements**: REQ-002, REQ-003
- **Design inputs**: `docs/api/sse-events.schema.json`, `docs/api/types.ts`
- **Description**: Confirm SSE-discovered snapshot changes prompt the user to refresh, repeated clicks do not overlap requests, a 304 keeps the verified snapshot, changed data updates the rendered page, and unavailable API/static data is reported as an error.

### Phase 3 — Release and deployment validation

#### Step 4: Validate and publish (`web/`, GitHub Actions, Vercel project)
- **Requirements**: REQ-003, REQ-004
- **Design inputs**: `.github/workflows/ci.yml`, `.github/workflows/hourly-crawl.yml`, `web/README.md`
- **Description**: Run typecheck, Vitest, build, focused E2E, and backend tests if backend changes are needed. Publish only the reviewed feature changes to the agreed Git branch, confirm GitHub CI, and verify the Vercel build/deployment and live reload behavior. Do not claim Vercel sync until a deployment is confirmed.

## Project Structure

```text
web/src/data/hooks.ts                         # register mounted dataset/health loaders
web/src/data/reload.ts                        # coordinate refresh and collect errors
web/src/data/reload.test.ts                   # refresh coordination tests
web/src/api/client.ts                         # snapshot boundary reset and forced revalidation
web/src/components/shell/Topbar.tsx           # persistent reload control
web/src/components/shell/Layout.tsx           # refresh action and feedback
web/src/api/client.test.ts                    # API revalidation regression coverage
web/e2e/resilience.spec.ts                    # browser refresh journey
```

## Testing Strategy

- **appType**: SPA with a separately hosted read-only backend/API
- **Critical user journeys**:
  1. User refreshes the current page; verified new dataset values render without changing route or filters.
  2. User refreshes when the snapshot is unchanged; the existing values remain and the UI confirms the check completed.
  3. SSE detects a new snapshot; the notice appears and clears only after successful refresh.
  4. API and static fallback are unavailable; the control reports failure and existing page data remains visible.
- **primaryValidationStack**: Vitest, TypeScript compiler, Vite build, Playwright
- **fallbackMatrix**:
  - `infra-tier`: backend API contract tests → existing mock/fallback tests; no live crawl required.
  - `browser-tier`: Playwright E2E → Vitest component/integration tests.
- **Environment requirements**: Node.js/npm; Playwright browser for E2E; no production secrets required for local validation.
- **knownGaps**: Without production credentials and the actual Vercel project, remote workflow/deployment verification cannot be inferred from local build success.
- **Test data strategy**: Use synthetic fixtures with distinct snapshot versions; do not crawl real providers.
- **Acceptance criteria**: Reload control is always present and keyboard-accessible; it refreshes mounted data and freshness without navigation; no secret is sent by the browser; errors are visible; targeted tests and build pass; GitHub/Vercel status is verified before claiming deployment.
- **Validation review expectations**: Check backend/API boundaries, caching/ETag behavior, new-data notice, accessible status, route/filter preservation, and actual deployment URL.

## Tasks

### Phase 1 — Foundational
- [x] T001 [Plan:1.1] Add mounted dataset/health refresh coordination in `web/src/data/hooks.ts` and `web/src/data/reload.ts`, preserving per-hook errors and revalidating the snapshot boundary.
- [x] T002 [P] [Plan:1.1] Add focused tests for refresh coordination and snapshot/ETag revalidation in `web/src/data/reload.test.ts` and `web/src/api/client.test.ts`.

### Phase 2 — User Story 1
- [x] T003 [US1] [Plan:2.1] Add persistent reload icon, accessible busy/disabled states, and status feedback in `web/src/components/shell/Topbar.tsx` and `web/src/components/shell/Layout.tsx`.
- [x] T004 [P] [US1] [Plan:2.1,2.2] Add browser coverage for manual refresh, new snapshot acceptance, and updated rendered data in `web/e2e/resilience.spec.ts`.

### Phase 3 — Release
- [x] T005 [Plan:3.1] Run frontend typecheck, unit tests, production build, full Playwright suite, and Python backend regression tests.
- [ ] T006 [Plan:3.1] Publish the feature-only changes to the user-approved Git branch, verify GitHub CI, then verify the resulting Vercel deployment and live data reload.

## Requirement Mapping

| REQ ID | Description | Plan Items | Implementation Evidence |
|--------|-------------|------------|------------------------|
| REQ-001 | Keep a keyboard-accessible reload icon visible in the top bar with progress feedback. | 2.1 | `web/src/components/shell/Topbar.tsx`, `web/src/components/shell/Layout.tsx` |
| REQ-002 | Revalidate currently mounted datasets and freshness without a page reload, and surface failures. | 1.1, 2.1, 2.2 | `web/src/data/hooks.ts`, `web/src/api/client.test.ts`, frontend tests |
| REQ-003 | Preserve SSE snapshot notices and never expose or invoke protected refresh credentials from browser code. | 2.2 | `web/src/api/sse.ts`, `web/src/components/shell/Topbar.tsx`, `docs/api/README.md` |
| REQ-004 | Validate, publish, and confirm GitHub/Vercel synchronization before declaring completion. | 3.1 | CI run, GitHub commit, Vercel deployment and live smoke evidence |
