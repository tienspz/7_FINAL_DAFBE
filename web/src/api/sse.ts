import { useState, useEffect, useCallback } from 'react';
import { Freshness } from './types';

export interface SnapshotStreamState {
  connected: boolean;
  freshness: Freshness | null;
  hasNewData: boolean;
  error: string | null;
  resetNewDataNotice: () => void;
}

export function useSnapshotStream(): SnapshotStreamState {
  const [connected, setConnected] = useState(false);
  const [freshness, setFreshness] = useState<Freshness | null>(null);
  const [hasNewData, setHasNewData] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resetNewDataNotice = useCallback(() => setHasNewData(false), []);

  useEffect(() => {
    // Only connect if EventSource is supported
    if (typeof EventSource === 'undefined') return;

    let eventSource: EventSource | null = null;
    let retryTimer: NodeJS.Timeout | null = null;

    function connect() {
      try {
        eventSource = new EventSource('/api/events');

        eventSource.onopen = () => {
          setConnected(true);
          setError(null);
        };

        eventSource.addEventListener('ready', (e) => {
          try {
            const data = JSON.parse(e.data);
            if (data?.snapshot) {
              setFreshness(data.snapshot);
            }
          } catch {
            // parsing error
          }
        });

        eventSource.addEventListener('snapshot', (e) => {
          try {
            const data = JSON.parse(e.data);
            if (data?.snapshot) {
              setFreshness(data.snapshot);
            }
            if (data?.changed) {
              setHasNewData(true);
            }
          } catch {
            // parsing error
          }
        });

        eventSource.addEventListener('refresh_finished', (e) => {
          try {
            const data = JSON.parse(e.data);
            if (data?.snapshot_changed) {
              setHasNewData(true);
            }
          } catch {
            // parsing error
          }
        });

        eventSource.onerror = () => {
          setConnected(false);
          eventSource?.close();
          // Silently attempt reconnect after 10 seconds without crashing
          retryTimer = setTimeout(connect, 10000);
        };
      } catch {
        // Fallback silently when SSE endpoint is not available
      }
    }

    connect();

    return () => {
      if (retryTimer) clearTimeout(retryTimer);
      eventSource?.close();
    };
  }, []);

  return {
    connected,
    freshness,
    hasNewData,
    error,
    resetNewDataNotice,
  };
}
