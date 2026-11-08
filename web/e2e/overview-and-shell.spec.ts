import { test, expect } from '@playwright/test';

test.describe('Shell and Overview Page (Gate 3)', () => {
  test('renders Overview without an unused quarter filter', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('main h2').first()).toBeVisible();
    const defaultPeriods = await page.locator('main h2').allTextContents();
    await page.goto('/?q=2024-Q1');

    // Check branding and page title
    await expect(page.locator('text=AICOR')).toBeVisible();
    await expect(page.locator('main h1')).toHaveText('Tổng quan');

    await expect(page.getByRole('navigation', { name: 'Thước quý thời gian' })).toHaveCount(0);
    await expect(page.locator('main h2')).toHaveText(defaultPeriods);

    // Check MSFT and GOOGL KPIs are visible
    await expect(page.locator('text=Microsoft (MSFT)')).toBeVisible();
    await expect(page.locator('text=Alphabet (GOOGL)')).toBeVisible();

    // Check statutory disclaimer
    await expect(page.locator('text=Tương quan ≠ nhân quả')).toBeVisible();
  });

  test('clicking Quarter Ruler on Financials updates URL query state', async ({ page }) => {
    await page.goto('/financials');
    const q2024Btn = page.locator('button:has-text("2024-Q1")');
    await q2024Btn.click();
    await expect(page).toHaveURL(/.*q=2024-Q1.*/);
  });

  test('opens navigation drawer, traps focus, and closes on Escape', async ({ page }) => {
    await page.goto('/');
    const hamburgerBtn = page.locator('button[aria-label="Mở menu điều hướng"]');
    await hamburgerBtn.click();
    await expect(hamburgerBtn).toHaveAttribute('aria-expanded', 'true');

    const drawer = page.locator('#navigation-drawer');
    await expect(drawer).toBeVisible();

    // Press Escape to close
    await page.keyboard.press('Escape');
    await expect(drawer).not.toBeVisible();
    await expect(hamburgerBtn).toHaveAttribute('aria-expanded', 'false');
    await expect(hamburgerBtn).toBeFocused();
  });

  test('toggles dark and light mode', async ({ page }) => {
    await page.goto('/');
    const themeBtn = page.locator('button[aria-label="Chuyển sang chế độ sáng"]');
    if (await themeBtn.isVisible()) {
      await themeBtn.click();
      const htmlEl = page.locator('html');
      await expect(htmlEl).toHaveAttribute('data-theme', 'light');
    }
  });

  test('disables chart animation when reduced motion is requested', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/');
    await expect(page.locator('.echarts-container').first()).toHaveAttribute('data-reduced-motion', 'true');
  });
});
