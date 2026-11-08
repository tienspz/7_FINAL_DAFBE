import { afterEach, describe, expect, it, vi } from 'vitest';
import { registerDataReloader, reloadMountedData } from './reload';

describe('reloadMountedData', () => {
  const unregister: Array<() => void> = [];

  afterEach(() => {
    unregister.splice(0).forEach((remove) => remove());
  });

  it('runs all registered refreshers and reports successful checks', async () => {
    const first = vi.fn().mockResolvedValue(null);
    const second = vi.fn().mockResolvedValue(null);
    unregister.push(registerDataReloader(first), registerDataReloader(second));

    await expect(reloadMountedData()).resolves.toEqual({
      reloadedCount: 2,
      errors: [],
    });
    expect(first).toHaveBeenCalledOnce();
    expect(first).toHaveBeenCalledWith(false);
    expect(second).toHaveBeenCalledOnce();
  });

  it('returns loader errors without skipping other refreshers', async () => {
    const failure = new Error('backend unavailable');
    const failed = vi.fn().mockResolvedValue(failure);
    const succeeded = vi.fn().mockResolvedValue(null);
    unregister.push(registerDataReloader(failed), registerDataReloader(succeeded));

    await expect(reloadMountedData()).resolves.toEqual({
      reloadedCount: 2,
      errors: [failure],
    });
    expect(succeeded).toHaveBeenCalledOnce();
  });

  it('unregisters refreshers when their owner unmounts', async () => {
    const refresher = vi.fn().mockResolvedValue(null);
    const remove = registerDataReloader(refresher);
    await reloadMountedData();
    remove();

    await expect(reloadMountedData()).resolves.toEqual({
      reloadedCount: 0,
      errors: [],
    });
  });

  it('passes force revalidation to each mounted loader', async () => {
    const refresher = vi.fn().mockResolvedValue(null);
    unregister.push(registerDataReloader(refresher));

    await reloadMountedData(true);

    expect(refresher).toHaveBeenCalledWith(true);
  });
});
