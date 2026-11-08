export type DataReloader = (forceRevalidate: boolean) => Promise<Error | null>;

export interface ReloadResult {
  reloadedCount: number;
  errors: Error[];
}

const dataReloaders = new Set<DataReloader>();

export function registerDataReloader(reloader: DataReloader): () => void {
  dataReloaders.add(reloader);
  return () => {
    dataReloaders.delete(reloader);
  };
}

export async function reloadMountedData(forceRevalidate = false): Promise<ReloadResult> {
  const reloaders = [...dataReloaders];
  const results = await Promise.all(reloaders.map(async (reloader) => {
    try {
      return await reloader(forceRevalidate);
    } catch (error) {
      return error instanceof Error ? error : new Error(String(error));
    }
  }));
  const errors = results.filter((error): error is Error => error !== null);

  return { reloadedCount: reloaders.length, errors };
}
