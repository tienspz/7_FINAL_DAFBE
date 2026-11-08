import { test, expect } from '@playwright/test';

test.describe('Resilience and Data Layer Fallback', () => {
  test('loads /__kit page without errors', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    await page.goto('/__kit');
    await expect(page.locator('text=AICOR UI Kit')).toBeVisible();
    expect(consoleErrors).toEqual([]);
  });

  test('verifies static fallback when backend API /api/data/* returns 500 error', async ({ page }) => {
    // Intercept backend API and return 500
    await page.route('**/api/data/**', (route) => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'simulated_backend_failure' }),
      });
    });

    await page.goto('/');
    await expect(page.locator('main h1')).toHaveText('Tổng quan');
    await expect(page.getByText('Microsoft (MSFT)')).toBeVisible();
    await expect(page.getByText('Alphabet (GOOGL)')).toBeVisible();
  });

  test('explains unavailable data and offers retry when API and static fallback both fail', async ({ page }) => {
    await page.route('**/api/data/overview', (route) =>
      route.fulfill({ status: 500, body: JSON.stringify({ error: 'backend_unavailable' }) })
    );
    await page.route('**/data/overview.json', (route) =>
      route.fulfill({ status: 500, body: JSON.stringify({ error: 'static_data_unavailable' }) })
    );

    await page.goto('/');
    await expect(page.getByRole('alert')).toContainText('Dữ liệu chưa tải đầy đủ');
    await expect(page.getByRole('button', { name: 'Thử tải lại' })).toBeVisible();
    await expect(page.getByRole('status').filter({ hasText: 'Không có dữ liệu tổng quan' })).toBeVisible();
  });

  test('shows the changed-snapshot notice for an SSE snapshot event', async ({ page }) => {
    await page.addInitScript(() => {
      class MockEventSource extends EventTarget {
        onopen: (() => void) | null = null;
        constructor(public url: string) {
          super();
          setTimeout(() => {
            this.onopen?.();
            this.dispatchEvent(new MessageEvent('snapshot', {
              data: JSON.stringify({
                snapshot: {
                  available: true,
                  snapshot_version: 'test-snapshot',
                  data_as_of: '2026-11-06',
                  age_seconds: 0,
                  stale: false,
                  checksum_ok: true,
                },
                changed: true,
              }),
            }));
          }, 0);
        }
        close() {}
      }

      Object.defineProperty(window, 'EventSource', { value: MockEventSource });
    });

    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Có dữ liệu mới' })).toBeVisible();
  });
});
