# Implementation Plan: Data-stage backend readiness

**Date**: 2026-11-07 | **Spec**: [`SPEC.md`](../../../SPEC.md), FR-45, FR-46, FR-52, CR-08, NFR-15; existing data-stage plans in `docs/plans/`

## Summary

Bring the prepared data snapshot into full agreement with the current pipeline and acceptance contracts before backend implementation. Add an offline, deterministic statistics refresh from the existing verified JSON artifacts, update the dashboard manifest checksum without changing source data, and make SQLite/snapshot consistency independently testable. Do not mask stale data by weakening acceptance requirements or claim a live-source pass without a live run.

## Technical Context

**Language/Version**: Python 3.14; existing type-annotated pipeline
**Primary Dependencies**: Existing pandas, NumPy, SciPy, statsmodels, PyYAML, pytest
**Storage**: `web/public/data/*.json`, `data/verified/manifest.json`, generated `data/db/aicor.sqlite`
**Testing**: pytest unit/integration tests and offline `scripts.acceptance_check.contract_checks()`
**Target Platform**: Windows local development and Ubuntu GitHub Actions
**Performance Goals**: Offline refresh finishes without source-network access; no regression to scheduled crawl
**Constraints**: Preserve all existing financial facts, formulas, source provenance, snapshot identity, and handoff on failure; no fabricated SEC credentials or values.

## Constitution Check

No project `constitution.md` or separate design artifacts are present. Existing repository constraints apply:

- Keep verified source data immutable during a statistics-only refresh — **PASS**.
- Preserve existing JSON consumer contracts and publish exact checksums — **PASS**.
- Retain the prior SQLite handoff if staging, validation, or replacement fails — **PASS**.
- Do not turn unavailable live-source verification into a success-shaped result — **PASS**.
- Do not weaken existing acceptance requirements to accommodate stale artifacts — **PASS**.

## Applied Guidelines

No migration-specific transformation guidelines apply. Follow existing project conventions: stdlib SQLite/JSON, atomic writes in `pipeline.util`, pinned dependencies, and offline pytest tests.

## Implementation Steps

### Step 1: Rebuilding current statistics from the verified snapshot

- **Requirements**: FR-46, FR-52
- **Design inputs**: `pipeline/stats/tests.py`, `pipeline/preprocess/facts.py`, dashboard `financials.json`, `investor.json`, and `manifest.json`.
- **Description**: Add a CLI that reconstructs typed metric inputs from the existing verified dashboard contracts and computes statistics through the canonical `run_all_tests` and `present_p_values` functions. Use current configured quality mode, Holm families, exclusions, seeds, and analysis window. Preserve snapshot/run/data dates; do not crawl, alter financial values, or replace a missing input with a default success.

### Step 2: Publishing and verifying the refreshed snapshot handoff

- **Requirements**: FR-45, FR-46, NFR-15
- **Design inputs**: Existing manifest checksums, SQLite staging handoff metadata, and `scripts/acceptance_check.py`.
- **Description**: Write refreshed `tests.json`, then atomically update both manifest copies with its checksum. Reuse/extend the SQLite handoff metadata and integrity checks so the snapshot, run, date, and counts match the manifests. Add regression tests for stale metadata, checksum update, malformed inputs, and failure preservation. Keep acceptance thresholds strict.

### Step 3: End-to-end readiness gate and operator documentation

- **Requirements**: FR-45, FR-46, FR-52, CR-08, NFR-15
- **Design inputs**: `README.md`, current raw archive/sync evidence, and acceptance command behavior.
- **Description**: Document offline refresh vs. live-source acceptance. Run unit tests, compile checks, the refresh, and all offline acceptance contracts. Report any live check blocked by missing credentials as unverified, not passed.

### Step 4: External adjusted-close verification

- **Requirements**: FR-45, CR-08
- **Design inputs**: Existing Yahoo adjusted-close series, configured price reconciliation tolerance, source allowlist, and provider credentials.
- **Description**: Replace the inaccessible Alpha Vantage free-tier check with a conditionally enabled Tiingo daily-price check. Send `TIINGO_API_KEY` only in an Authorization header; preserve `unverified` for missing credentials, errors, or fewer than 30 rows. Compare 30 shared sessions with the existing Yahoo adjusted-close series and persist URL/hash evidence.

## Project Structure

```text
scripts/
  rebuild_stats.py              # offline snapshot statistics refresh
pipeline/
  run.py                        # validated SQLite snapshot metadata
  crawlers/tiingo.py            # conditional external adjusted-close source
  stats/tests.py                # canonical statistical computation
  util.py                       # atomic writes and JSON helpers
tests/
  test_rebuild_stats.py
  test_run.py
  test_acceptance_check.py
scripts/
  acceptance_check.py           # strict offline and live acceptance contracts
docs/plans/backend-readiness/
  plan.md
  checkpoints/
```

## Testing Strategy

- **appType**: Offline data pipeline and static JSON handoff.
- **Critical user journeys**:
  1. Recompute statistics from a verified snapshot without network access.
  2. Reject malformed or cross-snapshot inputs rather than publish success-shaped data.
  3. Update the tests artifact and both manifest checksums consistently.
  4. Preserve old SQLite handoff if staging/validation fails and accept only a matching snapshot.
- **primaryValidationStack**: pytest, compileall, deterministic local contract checks, SQLite `integrity_check`, and manifest SHA-256 verification.
- **fallbackMatrix**: No infrastructure or browser tier is required; live provider checks require the configured real `SEC_USER_AGENT`.
- **Environment requirements**: Existing Python dependencies; real SEC contact only for live crawl and source sampling.
- **knownGaps**: A focused Tiingo check passed for 30 recent sessions, but SEC/full-source acceptance has not been rerun with the current credentials.
- **Test data strategy**: Reuse checked-in verified dashboard fixtures and temporary SQLite/JSON files in unit tests; do not invent production financial values.
- **Acceptance criteria**: All pytest tests pass; refreshed artifact schema/quality mode and required Holm/raw/display fields match the running pipeline; every listed manifest checksum matches; SQLite metadata/counts/integrity match both manifests; all offline contract checks pass. Live source acceptance is separately labeled.
- **Validation review expectations**: Confirm no acceptance check was relaxed, the source snapshot identity is preserved, and all worktree changes are limited to this handoff scope.

## Task Breakdown

### Phase 1: Foundational

- [x] T001 [Plan:1.1] Inspect current verified JSON contracts and stats inputs; record required snapshot fields in `scripts/rebuild_stats.py` and its tests.
- [x] T002 [Plan:2.1] Add focused tests for stale metadata, manifest checksum consistency, and failure preservation in `tests/test_rebuild_stats.py`.

### Phase 2: Offline refresh and strict handoff validation

- [x] T003 [Plan:1.1] Implement offline typed-input reconstruction and canonical statistics execution in `scripts/rebuild_stats.py`.
- [x] T004 [Plan:2.1] Atomically publish `tests.json` and both manifest checksum updates in `scripts/rebuild_stats.py`.
- [x] T005 [Plan:2.1] Validate SQLite schema, metadata, row counts, and integrity before replacement in `pipeline/run.py`; add regression coverage in `tests/test_run.py`.
- [x] T006 [Plan:2.1] Enforce snapshot-to-SQLite metadata equality and complete failure reporting in `scripts/acceptance_check.py`; add cases in `tests/test_acceptance_check.py`.

### Phase 3: Stage gate and documentation

- [x] T007 [Plan:3.1] Document offline refresh, strict local acceptance, and live-source requirements in `README.md`.
- [x] T008 [Plan:3.1] Run targeted and full pytest, compileall, offline refresh, checksum/SQLite checks, and all offline contract checks; record live-check blockers explicitly.

### Phase 4: External adjusted-close verification

- **Requirements**: FR-45, CR-08
- **Description**: Replace the inaccessible Alpha Vantage free-tier check with a conditionally enabled Tiingo daily-price check. Keep credentials in `TIINGO_API_KEY` and send them only in an Authorization header. Preserve `unverified` for missing credentials, errors, or fewer than 30 rows; compare 30 shared sessions against the current Yahoo adjusted-close series with existing tolerance and record response hashes.

- [x] T009 [Plan:4.1] Add Tiingo adjusted-close fetching, date-range parsing, authenticated HTTP headers, and conditional domain approval in `pipeline/crawlers/tiingo.py`, `pipeline/http.py`, and `config/allowlist.yaml`.
- [x] T010 [Plan:4.1] Add regression coverage for parsing, missing token, provider errors, credential non-persistence, and reconciliation in `tests/test_tiingo.py`, `tests/test_http.py`, and `tests/test_secondary_prices.py`.
- [x] T011 [Plan:4.1] Run the live 30-session check for MSFT/GOOGL, save source/hash evidence, and document the limitation that this does not replace full-crawl acceptance.

## Requirement Mapping

| Requirement | Description | Plan Items | Implementation Evidence |
|---|---|---|---|
| FR-45 | Check missing, duplicate, unit, and quality failures | 2.1, 3.1, 4.1 | `scripts/acceptance_check.py`, `tests/test_acceptance_check.py`, Tiingo reconciliation |
| FR-46 | Export and hand off calculated data for consumers | 1.1, 2.1, 3.1 | `scripts/rebuild_stats.py`, `pipeline/run.py`, manifest and SQLite |
| FR-52 | Run only on quality-approved data and report excluded quarters | 1.1, 3.1 | canonical `run_all_tests`, `tests.json`, acceptance contracts |
| CR-08 | Retain source-response traceability and avoid rewriting raw inputs | 1.1, 2.1, 4.1 | verified input-only refresh, Tiingo response SHA-256, token-free evidence |
| NFR-15 | Preserve last valid handoff and surface sync failures | 2.1, 3.1 | staged SQLite validation, atomic writes, regression tests |

## Complexity Tracking

No constitution violations or additional dependencies.

## Execution Results

- Offline refresh: `tests.json` schema 1.2, 79 results, 77 sensitivity results, mode B; checksum synchronized to both manifests.
- Offline acceptance: **42/42** contract checks pass; SQLite handoff passes integrity, metadata, and manifest row-count checks.
- Live recrawl completed: run `run_20261107T122003Z_a523f1b1`, snapshot `v20261106.5`, data as of 2026-11-06; **10/10** source samples and **42/42** contracts passed.
- Adjusted-close comparison was attempted with the provided Alpha Vantage free key; the provider responded that `TIME_SERIES_DAILY_ADJUSTED` is a premium endpoint and returned no rows. That attempt remained `unverified`; deterministic close/dividend/split self-check passed.
- Replaced the inaccessible free-tier Alpha Vantage endpoint with Tiingo. Separate live check on the existing `v20261106.5` snapshot: MSFT and GOOGL each matched 30/30 shared sessions within 0.1%; max relative differences were `8.7832e-06` and `7.2432e-06`. SHA-256 and token-free URLs are recorded in `docs/evidence/adjusted_close_tiingo_2026-11-07.json`. This was not a new SEC/full-source crawl and does not change the prior 10/10 full-crawl evidence.
- `python -m pytest -q`: **102 passed** (24 statistical warnings); compileall and `git diff --check` passed.
- Offline acceptance: **42/42** contracts passed after adding Tiingo to the approved-domain assertion. `python -m scripts.rebuild_stats --check` confirms snapshot `v20261106.5` is deterministic.
- Live evidence is captured in `docs/evidence/acceptance_2026-11-06.json`; its `checked_at` is 2026-11-07 and its snapshot is `v20261106.5`.
