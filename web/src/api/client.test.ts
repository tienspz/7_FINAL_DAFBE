import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchDataset } from './client';

const validDataset = {
  schema_version: '1.0',
  snapshot_version: 'snapshot-test',
  value: 42,
};

describe('fetchDataset', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads API data with a matching snapshot header', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify(validDataset), {
        headers: {
          ETag: '"dataset-v1"',
          'X-AICOR-Snapshot': 'snapshot-test',
        },
      })
    ));

    await expect(fetchDataset<typeof validDataset>('api-envelope-test')).resolves.toMatchObject({
      data: validDataset,
      source: 'api',
      snapshotVersion: 'snapshot-test',
    });
  });

  it('falls back to the static dataset when the API fails', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 500 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(validDataset))));

    await expect(fetchDataset<typeof validDataset>('static-fallback-test')).resolves.toMatchObject({
      data: validDataset,
      source: 'fallback',
      snapshotVersion: 'snapshot-test',
    });
  });

  it('returns the last valid cache and a warning when a new snapshot conflicts', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(validDataset), {
        headers: {
          ETag: '"dataset-v1"',
          'X-AICOR-Snapshot': 'snapshot-test',
        },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ...validDataset,
        snapshot_version: 'snapshot-new',
      }), {
        headers: {
          ETag: '"dataset-v2"',
          'X-AICOR-Snapshot': 'snapshot-new',
        },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ...validDataset,
        snapshot_version: 'snapshot-new',
      })));
    vi.stubGlobal('fetch', fetchMock);

    await fetchDataset<typeof validDataset>('snapshot-cache-test');
    const result = await fetchDataset<typeof validDataset>('snapshot-cache-test');

    expect(result.source).toBe('cache');
    expect(result.data).toEqual(validDataset);
    expect(result.warning).toContain('không khớp');
  });
});
