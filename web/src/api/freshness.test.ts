import { describe, expect, it } from 'vitest';
import type { Freshness } from './types';
import { selectLatestFreshness } from './freshness';

const freshness = (overrides: Partial<Freshness> = {}): Freshness => ({
  available: true,
  snapshot_version: 'snapshot-old',
  data_as_of: '2026-11-06',
  generated_at: '2026-11-08T06:51:43Z',
  run_id: null,
  age_seconds: 40_000,
  stale: true,
  stale_after_seconds: 21_600,
  checksum_ok: true,
  file_count: 10,
  problems: [],
  ...overrides,
});

describe('selectLatestFreshness', () => {
  it('prefers health when its snapshot was generated after the SSE snapshot', () => {
    const sse = freshness();
    const health = freshness({
      snapshot_version: 'snapshot-new',
      generated_at: '2026-11-08T18:00:00Z',
      age_seconds: 60,
      stale: false,
    });

    expect(selectLatestFreshness(sse, health)).toBe(health);
  });

  it('prefers a more recently calculated health age for the same snapshot', () => {
    const sse = freshness({ age_seconds: 120 });
    const health = freshness({ age_seconds: 20 });

    expect(selectLatestFreshness(sse, health)).toBe(health);
  });

  it('uses the valid generation timestamp when the other source has none', () => {
    const sse = freshness({ generated_at: null, age_seconds: null });
    const health = freshness();

    expect(selectLatestFreshness(sse, health)).toBe(health);
  });

  it('keeps an unchanged old snapshot stale after a health revalidation', () => {
    const sse = freshness({ age_seconds: 40_000, stale: true });
    const health = freshness({ age_seconds: 40_010, stale: true });

    expect(selectLatestFreshness(sse, health)?.stale).toBe(true);
  });
});
