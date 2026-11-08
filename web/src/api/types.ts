/**
 * AICOR backend API and SSE types.
 *
 * Keep these in sync with docs/api/openapi.yaml and
 * docs/api/sse-events.schema.json.
 */

export type HealthStatus = "ok" | "degraded" | "unavailable";
export type RefreshStatus = "idle" | "running" | "succeeded" | "failed";
export type RefreshTarget = "local" | "github";

export interface Freshness {
  available: boolean;
  snapshot_version: string | null;
  data_as_of: string | null;
  generated_at: string | null;
  run_id: string | null;
  /** Seconds since generated_at; null when generated_at is missing/invalid. */
  age_seconds: number | null;
  /** True when stale or when generated_at is missing/unparseable. */
  stale: boolean;
  stale_after_seconds: number;
  checksum_ok: boolean;
  file_count: number;
  problems: string[];
}

export interface RefreshState {
  status: RefreshStatus;
  job_id: string | null;
  reason: string;
  started_at: string | null;
  finished_at: string | null;
  detail: string;
  exit_code: number | null;
  target: RefreshTarget;
  log_path: string | null;
  run_id: number | null;
  snapshot_version: string | null;
  /** True when the version changed across the refresh; null when not reread. */
  snapshot_changed: boolean | null;
}

/** Canonical payload of the `snapshot` SSE event. */
export interface SnapshotEvent {
  snapshot: Freshness;
  /**
   * The producer observed a version different from its previous snapshot
   * event. Compare snapshot.snapshot_version for idempotence; a heartbeat
   * resync always sends changed=false.
   */
  changed: boolean;
}

/** Payload of the first SSE event after connecting. */
export interface ReadyEvent {
  snapshot: Freshness;
  refresh: RefreshState;
  heartbeat_seconds: number;
}

/** Payload of the `refresh` SSE event. */
export type RefreshEvent = RefreshState;

/** Payload of the `refresh_finished` SSE event. */
export type RefreshFinishedEvent = RefreshState;

/** Payload of the `scheduler_error` SSE event. */
export interface SchedulerErrorEvent {
  error: string;
}

export type BackendEvent =
  | { event: "ready"; data: ReadyEvent }
  | { event: "snapshot"; data: SnapshotEvent }
  | { event: "refresh"; data: RefreshEvent }
  | { event: "refresh_finished"; data: RefreshFinishedEvent }
  | { event: "scheduler_error"; data: SchedulerErrorEvent };

export interface Manifest {
  schema_version?: string;
  snapshot_version: string;
  generated_at: string;
  data_as_of: string;
  latest_quarter?: string;
  run_id?: string;
  files: Record<string, string>;
  checksums: Record<string, string>;
  row_counts?: Record<string, number>;
  [key: string]: unknown;
}

export interface Uptime {
  started_at: string;
  uptime_seconds: number;
}

export interface EventCapacity {
  subscribers: number;
  capacity: number;
}

export interface PublicConfig {
  refresh_mode: RefreshTarget;
  stale_after_seconds: number;
  refresh_interval_seconds: number;
  refresh_endpoint_enabled: boolean;
  /** False in GitHub mode means the served snapshot is not updated by dispatch alone. */
  post_refresh_configured: boolean;
}

export interface HealthResponse {
  status: HealthStatus;
  service: "aicor-backend";
  time: string;
  uptime: Uptime;
  snapshot: Freshness;
  refresh: RefreshState;
  events: EventCapacity;
  config: PublicConfig;
  scheduler?: Record<string, unknown>;
}

export interface LatestResponse {
  freshness: Freshness;
  manifest: Manifest;
  overview?: Record<string, unknown>;
  decision?: Record<string, unknown>;
}

export interface RefreshAccepted {
  status: "accepted";
  refresh: RefreshState;
}

export interface RefreshConflict {
  status: "conflict";
  refresh: RefreshState;
}

export interface ErrorResponse {
  error: string;
  [key: string]: unknown;
}

export interface IndexResponse {
  service: string;
  time: string;
  snapshot_version: string | null;
  endpoints: Record<string, string>;
  datasets: string[];
}

/** Weak ETag format used by manifest and dataset responses. */
export const WEAK_ETAG_PATTERN = /^W\/"[0-9a-f]{64}"$/;

/** Response headers the frontend may need to read. */
export const EXPOSED_RESPONSE_HEADERS = ["ETag", "X-AICOR-Snapshot"] as const;

/**
 * Returns the snapshot version carried by an SSE event, if any.
 * Use it to ignore duplicate or out-of-order snapshot deliveries.
 */
export function snapshotVersionOf(event: BackendEvent): string | null {
  switch (event.event) {
    case "ready":
    case "snapshot":
      return event.data.snapshot.snapshot_version;
    case "refresh_finished":
      return event.data.snapshot_version;
    default:
      return null;
  }
}

