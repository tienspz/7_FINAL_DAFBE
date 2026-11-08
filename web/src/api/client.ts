/**
 * API client with ETag revalidation and automatic static fallback.
 */

import { HealthResponse, Manifest } from './types';

interface CacheEntry<T> {
  data: T;
  etag: string | null;
  snapshotVersion: string | null;
  timestamp: number;
}

const memoryCache = new Map<string, CacheEntry<unknown>>();
const inFlightRequests = new Map<string, Promise<FetchResult<unknown>>>();
let activeSnapshotVersion: string | null = null;

class DatasetValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DatasetValidationError';
  }
}

export interface FetchResult<T> {
  data: T;
  source: 'api' | 'cache' | 'fallback';
  etag: string | null;
  snapshotVersion: string | null;
  warning?: string;
}

/**
 * Normalizes dataset key to static path
 * e.g. 'prices/MSFT' -> '/data/prices/MSFT.json'
 * e.g. 'overview' -> '/data/overview.json'
 */
function toStaticPath(key: string): string {
  if (key === 'manifest') return '/data/manifest.json';
  return `/data/${key}.json`;
}

function validateDatasetEnvelope(data: unknown, key: string, headerSnapshotVersion?: string | null): asserts data is {
  schema_version: string;
  snapshot_version: string;
} {
  if (!data || typeof data !== 'object') {
    throw new DatasetValidationError(`Dataset '${key}' không phải một object JSON hợp lệ.`);
  }

  const envelope = data as { schema_version?: unknown; snapshot_version?: unknown };
  if (typeof envelope.schema_version !== 'string' || typeof envelope.snapshot_version !== 'string') {
    throw new DatasetValidationError(`Dataset '${key}' thiếu schema_version hoặc snapshot_version hợp lệ.`);
  }

  if (headerSnapshotVersion && envelope.snapshot_version !== headerSnapshotVersion) {
    throw new DatasetValidationError(`Snapshot của API không khớp dữ liệu '${key}'.`);
  }

  if (activeSnapshotVersion && envelope.snapshot_version !== activeSnapshotVersion) {
    throw new DatasetValidationError(
      `Snapshot '${envelope.snapshot_version}' của '${key}' không khớp snapshot '${activeSnapshotVersion}' đang dùng.`
    );
  }

  activeSnapshotVersion ??= envelope.snapshot_version;
}

/**
 * Fetches dataset with ETag support and static fallback.
 */
export async function fetchDataset<T>(key: string): Promise<FetchResult<T>> {
  const pending = inFlightRequests.get(key);
  if (pending) return pending as Promise<FetchResult<T>>;

  const request = fetchDatasetUncached<T>(key);
  inFlightRequests.set(key, request);
  const cleanup = () => {
    if (inFlightRequests.get(key) === request) inFlightRequests.delete(key);
  };
  void request.then(cleanup, cleanup);
  return request;
}

async function fetchDatasetUncached<T>(key: string): Promise<FetchResult<T>> {
  const cacheKey = `dataset:${key}`;
  const cached = memoryCache.get(cacheKey) as CacheEntry<T> | undefined;

  const headers: Record<string, string> = {};
  if (cached?.etag) {
    headers['If-None-Match'] = cached.etag;
  }
  let validationError: DatasetValidationError | null = null;

  // 1. Try Backend API
  try {
    const response = await fetch(`/api/data/${key}`, { headers });
    
    // 304 Not Modified -> return cached data
    if (response.status === 304 && cached) {
      return {
        data: cached.data,
        source: 'cache',
        etag: cached.etag,
        snapshotVersion: cached.snapshotVersion,
      };
    }

    if (response.ok) {
      const data: unknown = await response.json();
      const etag = response.headers.get('ETag');
      const snapshotVersion = response.headers.get('X-AICOR-Snapshot');
      validateDatasetEnvelope(data, key, snapshotVersion);

      memoryCache.set(cacheKey, {
        data: data as T,
        etag,
        snapshotVersion,
        timestamp: Date.now(),
      });

      return {
        data: data as T,
        source: 'api',
        etag,
        snapshotVersion,
      };
    }
  } catch (error) {
    if (error instanceof DatasetValidationError) validationError = error;
    // API network failure -> fall through to static fallback
  }

  // 2. Fallback to static public JSON
  try {
    const staticUrl = toStaticPath(key);
    const staticRes = await fetch(staticUrl);
    if (staticRes.ok) {
      const data: unknown = await staticRes.json();
      validateDatasetEnvelope(data, key);
      memoryCache.set(cacheKey, {
        data,
        etag: null,
        snapshotVersion: data.snapshot_version,
        timestamp: Date.now(),
      });
      return {
        data: data as T,
        source: 'fallback',
        etag: null,
        snapshotVersion: data.snapshot_version,
      };
    }
  } catch (error) {
    if (error instanceof DatasetValidationError) validationError = error;
    // Static fetch also failed
  }

  if (validationError && cached) {
    return {
      data: cached.data,
      source: 'cache',
      etag: cached.etag,
      snapshotVersion: cached.snapshotVersion,
      warning: validationError.message,
    };
  }

  if (validationError) throw validationError;

  // 3. If cached exists, return stale cache as last resort
  if (cached) {
    return {
      data: cached.data,
      source: 'cache',
      etag: cached.etag,
      snapshotVersion: cached.snapshotVersion,
    };
  }

  throw new Error(`Không thể nạp dữ liệu cho '${key}' từ cả API và tệp tĩnh.`);
}

/**
 * Fetches health status with fallback.
 */
export async function fetchHealth(): Promise<HealthResponse | null> {
  try {
    const res = await fetch('/api/health');
    if (res.ok) {
      return (await res.json()) as HealthResponse;
    }
  } catch {
    // API not reachable
  }

  // Simulated fallback health from manifest
  try {
    const manifestRes = await fetch('/data/manifest.json');
    if (manifestRes.ok) {
      const m = (await manifestRes.json()) as Manifest;
      const generatedAt = Date.parse(m.generated_at);
      const ageSeconds = Number.isFinite(generatedAt)
        ? Math.max(0, Math.floor((Date.now() - generatedAt) / 1000))
        : null;
      return {
        status: 'degraded',
        service: 'aicor-backend',
        time: new Date().toISOString(),
        uptime: { started_at: m.generated_at, uptime_seconds: 0 },
        snapshot: {
          available: true,
          snapshot_version: m.snapshot_version,
          data_as_of: m.data_as_of,
          generated_at: m.generated_at,
          run_id: m.run_id || null,
          age_seconds: ageSeconds,
          stale: ageSeconds === null || ageSeconds > 21600,
          stale_after_seconds: 21600,
          checksum_ok: false,
          file_count: Object.keys(m.files || {}).length,
          problems: [],
        },
        refresh: {
          status: 'idle',
          job_id: null,
          reason: '',
          started_at: null,
          finished_at: null,
          detail: '',
          exit_code: null,
          target: 'local',
          log_path: null,
          run_id: null,
          snapshot_version: m.snapshot_version,
          snapshot_changed: null,
        },
        events: { subscribers: 0, capacity: 128 },
        config: {
          refresh_mode: 'local',
          stale_after_seconds: 21600,
          refresh_interval_seconds: 900,
          refresh_endpoint_enabled: false,
          post_refresh_configured: false,
        },
      };
    }
  } catch {
    // Both failed
  }
  return null;
}
