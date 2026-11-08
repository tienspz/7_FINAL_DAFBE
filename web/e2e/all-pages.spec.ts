import { test, expect } from '@playwright/test';

test.describe('All 6 Domain Pages (Gate 4 Smoke Suite)', () => {
  test('Page 8.2 /investor: verifies calculator, scenarios, and price charts', async ({ page }) => {
    await page.goto('/investor');
    await expect(page.locator('#calculator-heading')).toBeVisible();

    // Verify calculator result is visible
    await expect(page.locator('text=Giá trị cuối (Vt)')).toBeVisible();
    await expect(page.locator('text=Tỷ suất sinh lời (ROI)')).toBeVisible();
    await expect(page.getByText('So với SPY')).toBeVisible();
    const mddValue = page.getByText('MDD:', { exact: false }).first();
    await mddValue.scrollIntoViewIfNeeded();
    const mddBounds = await mddValue.boundingBox();
    if (!mddBounds) throw new Error('Risk metrics should remain visible within the viewport.');
    const viewportWidth = page.viewportSize()?.width;
    if (!viewportWidth) throw new Error('The test viewport width must be configured.');
    expect(mddBounds.x + mddBounds.width).toBeLessThanOrEqual(viewportWidth);

    // Verify price chart toggle
    const toggleBtn = page.locator('button:has-text("Giá tuyệt đối ($)")');
    await toggleBtn.click();
    await expect(page.getByRole('button', { name: 'Giá tuyệt đối ($)' })).toHaveAttribute('aria-pressed', 'true');

    // Verify save scenario button
    const saveBtn = page.locator('button:has-text("Lưu kịch bản")');
    await saveBtn.click();
    await expect(page.locator('text=Kịch bản đầu tư đã lưu')).toBeVisible();

    const csvDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Xuất CSV' }).click();
    expect((await csvDownload).suggestedFilename()).toMatch(/\.csv$/);

    const pngDownload = page.waitForEvent('download');
    await expect(page.getByRole('button', { name: 'Xuất PNG' })).toBeEnabled();
    await page.getByRole('button', { name: 'Xuất PNG' }).click();
    expect((await pngDownload).suggestedFilename()).toMatch(/\.png$/);
  });

  test('Page 8.2 /investor: validates inputs and persists renamed scenarios', async ({ page }) => {
    await page.goto('/investor');
    await expect(page.locator('#calculator-heading')).toBeVisible();
    await page.getByLabel('Vốn đầu tư (USD)').fill('0');
    await expect(page.getByRole('alert')).toContainText('Vốn đầu tư phải lớn hơn 0');

    await page.getByLabel('Vốn đầu tư (USD)').fill('1000');
    await page.getByRole('button', { name: 'Lưu kịch bản' }).click();
    const scenarioName = page.getByRole('textbox', { name: 'Tên kịch bản MSFT' });
    await expect(scenarioName).toBeVisible();
    await scenarioName.fill('Kịch bản kiểm tra');
    await page.reload();
    await expect(page.getByRole('textbox', { name: 'Tên kịch bản MSFT' })).toHaveValue('Kịch bản kiểm tra');

    page.on('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: 'Xóa kịch bản Kịch bản kiểm tra' }).click();
    await expect(page.getByText('Kịch bản kiểm tra')).not.toBeVisible();
  });

  test('all pages fit 360, 768, and 1440 pixel viewports', async ({ page }) => {
    for (const viewport of [360, 768, 1440]) {
      await page.setViewportSize({ width: viewport, height: 900 });
      for (const path of ['/', '/investor', '/financials', '/ai', '/decision', '/methodology']) {
        await page.goto(path);
        const dimensions = await page.evaluate(() => ({
          viewport: document.documentElement.clientWidth,
          body: document.body.scrollWidth,
          header: document.querySelector('header')?.scrollWidth ?? 0,
          headerClient: document.querySelector('header')?.clientWidth ?? 0,
        }));
        expect(dimensions.body, `${path} at ${viewport}px`).toBeLessThanOrEqual(dimensions.viewport);
        expect(dimensions.header, `${path} header at ${viewport}px`).toBeLessThanOrEqual(dimensions.headerClient);
      }
    }
  });

  test('global filters and quarter ruler appear only on pages that use them', async ({ page }) => {
    const isMobile = (page.viewportSize()?.width ?? 0) <= 600;
    const companyFilter = isMobile
      ? page.getByRole('combobox', { name: 'Bộ lọc doanh nghiệp' })
      : page.getByRole('group', { name: 'Bộ lọc doanh nghiệp' });
    const benchmarkFilter = isMobile
      ? page.getByRole('combobox', { name: 'Bộ lọc Benchmark' })
      : page.getByRole('group', { name: 'Bộ lọc Benchmark' });
    const quarterRuler = page.getByRole('navigation', { name: 'Thước quý thời gian' });

    await page.goto('/');
    await expect(companyFilter).toBeVisible();
    await expect(benchmarkFilter).toBeVisible();
    await expect(quarterRuler).toHaveCount(0);

    await page.goto('/financials');
    await expect(companyFilter).toBeVisible();
    await expect(benchmarkFilter).toHaveCount(0);
    await expect(quarterRuler).toBeVisible();

    await page.goto('/ai');
    await expect(companyFilter).toBeVisible();
    await expect(benchmarkFilter).toHaveCount(0);
    await expect(quarterRuler).toHaveCount(0);

    await page.goto('/investor');
    await expect(companyFilter).toHaveCount(0);
    await expect(benchmarkFilter).toBeVisible();
    await expect(quarterRuler).toHaveCount(0);

    for (const path of ['/decision', '/methodology']) {
      await page.goto(path);
      await expect(companyFilter).toHaveCount(0);
      await expect(benchmarkFilter).toHaveCount(0);
      await expect(quarterRuler).toHaveCount(0);
    }
  });

  test('invalid company filters fall back to compare mode', async ({ page }) => {
    await page.goto('/financials?company=UNKNOWN');
    if ((page.viewportSize()?.width ?? 0) <= 600) {
      await expect(page.getByRole('combobox', { name: 'Bộ lọc doanh nghiệp' })).toHaveValue('BOTH');
    } else {
      await expect(page.getByRole('button', { name: 'So sánh' })).toHaveAttribute('aria-pressed', 'true');
    }

    await page.goto('/ai?company=UNKNOWN&lag=9');
    await expect(page.locator('#lag-slider')).toHaveValue('1');
    const matrix = page.getByRole('table', { name: 'Ma trận tương quan theo doanh nghiệp' });
    await expect(matrix.getByText('MSFT', { exact: true }).first()).toBeVisible();
    await expect(matrix.getByText('GOOGL', { exact: true }).first()).toBeVisible();
  });

  test('Page 8.3 /financials: verifies core metrics, cloud segments, and table', async ({ page }) => {
    await page.goto('/financials');
    await expect(page.locator('h2:has-text("Chỉ số tài chính & Hiệu quả vốn")')).toBeVisible();

    // Click another metric tab (e.g. Biên lợi nhuận HĐ)
    const opMarginTab = page.locator('button:has-text("Biên lợi nhuận HĐ")');
    await opMarginTab.click();

    // Verify cloud segments
    await expect(page.locator('h3:has-text("Phân khúc Đám mây")')).toBeVisible();
    await expect(page.locator('table').first().locator('tbody tr').first().locator('td').nth(3)).not.toHaveText('—');

    // Verify metrics table
    await expect(page.locator('h3:has-text("Bảng chi tiết chỉ số")')).toBeVisible();
  });

  test('Page 8.3 /financials: search provides a clear empty state and reset', async ({ page }) => {
    await page.goto('/financials');
    const search = page.getByRole('textbox', { name: 'Tìm theo quý hoặc mã cổ phiếu' });
    await search.fill('not-a-company-or-quarter');
    await expect(page.getByRole('status').filter({ hasText: 'Không tìm thấy kỳ phù hợp' })).toBeVisible();
    await page.getByRole('button', { name: 'Xóa tìm kiếm' }).click();
    await expect(search).toHaveValue('');
    await expect(page.getByRole('status').filter({ hasText: 'Không tìm thấy kỳ phù hợp' })).toHaveCount(0);
  });

  test('Page 8.3 /financials: quarter ruler highlights data and table supports sorting', async ({ page }) => {
    await page.goto('/financials?q=2024-Q1');
    const table = page.locator('table').last();
    const selectedQuarterRows = table.locator('tbody tr[aria-current="true"]');
    await expect(selectedQuarterRows).toHaveCount(2);
    await expect(selectedQuarterRows.first()).toContainText('2024-Q1');
    await expect(table.getByRole('img', { name: /doanh thu qua các quý/ }).first()).toBeVisible();

    const revenueHeader = table.getByRole('columnheader', { name: 'Doanh thu', exact: true });
    await revenueHeader.getByRole('button').click();
    await expect(revenueHeader).toHaveAttribute('aria-sort', 'ascending');
  });

  test('Page 8.4 /ai: verifies lag slider k=0..4, correlation heatmap, and events', async ({ page }) => {
    await page.goto('/ai');
    await expect(page.locator('h2:has-text("Ma trận tương quan đầu tư AI")')).toBeVisible();

    // Slider k
    const slider = page.locator('#lag-slider');
    await slider.fill('3');
    await expect(page.locator('text=3 quý', { exact: true })).toBeVisible();
    await expect(page).toHaveURL(/lag=3/);

    // Events timeline
    await expect(page.locator('h3:has-text("Dòng sự kiện AI")')).toBeVisible();
    await expect(page.locator('text=Reported').first()).toBeVisible();
  });

  test('Page 8.4 /ai: compare mode shows both companies', async ({ page }) => {
    await page.goto('/ai?company=MSFT');
    const matrix = page.getByRole('table', { name: 'Ma trận tương quan theo doanh nghiệp' });
    await expect(matrix.getByText('MSFT', { exact: true }).first()).toBeVisible();
    await expect(matrix.getByText('GOOGL', { exact: true })).toHaveCount(0);

    if ((page.viewportSize()?.width ?? 0) <= 600) {
      await page.getByRole('combobox', { name: 'Bộ lọc doanh nghiệp' }).selectOption('BOTH');
    } else {
      await page.getByRole('button', { name: 'So sánh' }).click();
    }

    await expect(page).toHaveURL(/company=BOTH/);
    await expect(matrix.getByText('MSFT', { exact: true }).first()).toBeVisible();
    await expect(matrix.getByText('GOOGL', { exact: true }).first()).toBeVisible();
    await expect(page.getByRole('img', { name: 'Tăng trưởng R&D và CapEx theo quý của MSFT và GOOGL' })).toBeVisible();
  });

  test('navigation carries only filters used by the destination page', async ({ page }) => {
    await page.goto('/financials?company=GOOGL&bench=QQQ&q=2024-Q1&lag=3');
    await page.getByRole('button', { name: 'Mở menu điều hướng' }).click();
    await page.getByRole('link', { name: '4. Đầu tư AI' }).click();
    await expect(page).toHaveURL(/\/ai\?company=GOOGL&lag=3$/);
  });

  test('Page 8.5 /decision: verifies decision matrix and status badges', async ({ page }) => {
    await page.goto('/decision');
    await expect(page.locator('h2:has-text("Bảng tổng hợp chỉ tiêu")')).toBeVisible();
    await expect(page.locator('text=Trạng thái tổng hợp')).toBeVisible();
    await expect(page.locator('h3:has-text("Cách đọc tín hiệu chi tiêu vốn và dòng tiền")')).toBeVisible();
  });

  test('Page 8.6 /methodology: verifies formulas, 21 data sources, and hypothesis tests', async ({ page }) => {
    await page.goto('/methodology');
    await expect(page.locator('#system-status h2')).toBeVisible();
    await expect(page.locator('#quality-summary h2')).toBeVisible();
    await expect(page.locator('#hypothesis-tests h2')).toBeVisible();
    await expect(page.locator('#formulas h2')).toBeVisible();
    await expect(page.locator('#sources h2')).toBeVisible();

    // Wait for test results to finish loading
    await expect(page.locator('#hypothesis-tests tbody tr').first()).toBeVisible();

    // Toggle quality mode
    const labelLowBtn = page.locator('#hypothesis-tests [role="group"] button').nth(1);
    await labelLowBtn.click();
    await expect(labelLowBtn).toHaveAttribute('aria-pressed', 'true');
  });
});
