import React, { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Layout } from '../../components/shell/Layout';
import { useOverview } from '../../data/hooks';
import { EChart } from '../../components/charts/EChart';
import { getThemeColors, getEChartsBaseOption } from '../../lib/echarts-theme';
import { formatPercent, formatQuarter } from '../../lib/format';
import { Skeleton } from '../../components/ui/Skeleton';
import { Segmented } from '../../components/ui/Segmented';
import { EmptyState } from '../../components/ui/EmptyState';
import { Tooltip } from '../../components/ui/Tooltip';
import { ExternalLink, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { i18n } from '../../i18n/vi';
import { useThemeMode } from '../../lib/use-theme-mode';
import { getBenchmarkFilter, getCompanyFilter } from '../../lib/filters';

export const OverviewPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const selectedCompany = getCompanyFilter(searchParams.get('company'));
  const selectedBenchmark = getBenchmarkFilter(searchParams.get('bench'));

  const { data, loading, error } = useOverview();
  const availableQuarters = [...new Set(data?.business_comparison.MSFT.map((item) => item.calendar_key) ?? [])].sort();
  const selectedQuarter = data?.latest_quarter ?? availableQuarters.at(-1);
  const [businessMetric, setBusinessMetric] = useState<'operating_margin' | 'fcf_margin' | 'revenue_growth_yoy'>('operating_margin');

  const isDark = useThemeMode();
  const colors = getThemeColors(isDark);

  // Normalized Price Chart Option
  const priceChartOption = useMemo(() => {
    if (!data?.normalized_prices) return {};
    const baseOpt = getEChartsBaseOption(isDark);

    const msftData = data.normalized_prices.MSFT || [];
    const googlData = data.normalized_prices.GOOGL || [];
    const benchData = data.normalized_prices[selectedBenchmark as 'SPY' | 'QQQ'] || [];

    const dates = msftData.map((d) => d.date);

    const series = [];

    if (selectedCompany === 'BOTH' || selectedCompany === 'MSFT') {
      series.push({
        name: 'Microsoft (MSFT)',
        type: 'line',
        data: msftData.map((d) => d.value),
        itemStyle: { color: colors.msft },
        lineStyle: { width: 2, color: colors.msft },
        showSymbol: false,
        symbol: 'circle',
        symbolSize: 6,
      });
    }

    if (selectedCompany === 'BOTH' || selectedCompany === 'GOOGL') {
      series.push({
        name: 'Alphabet (GOOGL)',
        type: 'line',
        data: googlData.map((d) => d.value),
        itemStyle: { color: colors.googl },
        lineStyle: { width: 2, color: colors.googl },
        showSymbol: false,
        symbol: 'rect',
        symbolSize: 6,
      });
    }

    series.push({
      name: `${selectedBenchmark} (Benchmark)`,
      type: 'line',
      data: benchData.map((d) => d.value),
      itemStyle: { color: colors.spy },
      lineStyle: { width: 1.5, type: 'dashed', color: colors.spy },
      showSymbol: false,
    });

    return {
      ...baseOpt,
      tooltip: {
        ...baseOpt.tooltip,
        formatter: (params: any) => {
          if (!params || !params.length) return '';
          let res = `<div style="font-size:11px; margin-bottom:4px; font-weight:600;">Ngày: ${params[0]?.axisValue}</div>`;
          params.forEach((p: any) => {
            res += `<div style="display:flex; justify-content:space-between; gap:16px;">
              <span>${p.marker} ${p.seriesName}</span>
              <span style="font-weight:600; font-family:var(--font-mono);">${p.value?.toFixed(1)}</span>
            </div>`;
          });
          return res;
        },
      },
      legend: {
        ...baseOpt.legend,
        data: series.map((s) => s.name),
        formatter: (name: string) => name.includes('(MSFT)')
          ? 'MSFT'
          : name.includes('(GOOGL)')
            ? 'GOOGL'
            : selectedBenchmark,
      },
      xAxis: {
        ...baseOpt.xAxis,
        type: 'category',
        data: dates,
      },
      yAxis: {
        ...baseOpt.yAxis,
        name: 'Cơ sở 100',
        type: 'value',
      },
      series,
    };
  }, [data, selectedCompany, selectedBenchmark, isDark, colors]);

  // Business Comparison Bar Chart Option
  const businessChartOption = useMemo(() => {
    if (!data?.business_comparison) return {};
    const baseOpt = getEChartsBaseOption(isDark);

    const msftQuarters = data.business_comparison.MSFT || [];
    const googlQuarters = data.business_comparison.GOOGL || [];

    const categories = [...new Set([...msftQuarters, ...googlQuarters].map((quarter) => quarter.calendar_key))].sort();
    const valuesByQuarter = (quarters: typeof msftQuarters) => {
      const byQuarter = new Map(quarters.map((quarter) => [quarter.calendar_key, quarter]));
      return categories.map((key) => {
        const value = byQuarter.get(key)?.[businessMetric];
        return value !== null && value !== undefined ? Number((value * 100).toFixed(1)) : null;
      });
    };
    const msftValues = valuesByQuarter(msftQuarters);
    const googlValues = valuesByQuarter(googlQuarters);

    const series = [];

    if (selectedCompany === 'BOTH' || selectedCompany === 'MSFT') {
      series.push({
        name: 'Microsoft (MSFT)',
        type: 'bar',
        data: msftValues,
        itemStyle: { color: colors.msft, borderRadius: [2, 2, 0, 0] },
        ...(selectedQuarter ? {
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: colors.textMuted, type: 'dashed' },
            label: { formatter: selectedQuarter, color: colors.textMuted },
            data: [{ xAxis: selectedQuarter }],
          },
        } : {}),
      });
    }

    if (selectedCompany === 'BOTH' || selectedCompany === 'GOOGL') {
      series.push({
        name: 'Alphabet (GOOGL)',
        type: 'bar',
        data: googlValues,
        itemStyle: { color: colors.googl, borderRadius: [2, 2, 0, 0] },
      });
    }

    return {
      ...baseOpt,
      legend: {
        ...baseOpt.legend,
        data: series.map((s) => s.name),
        formatter: (name: string) => name.includes('(MSFT)') ? 'MSFT' : 'GOOGL',
      },
      xAxis: {
        ...baseOpt.xAxis,
        type: 'category',
        data: categories,
      },
      yAxis: {
        ...baseOpt.yAxis,
        name: '%',
        type: 'value',
      },
      series,
    };
  }, [data, businessMetric, selectedCompany, selectedQuarter, isDark, colors]);

  const renderKPICard = (
    label: string,
    value: number | null | undefined,
    sourceUrl?: string,
    isGrowth = false
  ) => {
    const isPos = (value || 0) > 0;
    const isZero = value === 0 || value === null || value === undefined;

    return (
      <div
        style={{
          backgroundColor: 'var(--surface-1)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--radius-md)',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{label}</span>
          {sourceUrl && (
            <Tooltip content="Xem tài liệu nguồn SEC 10-Q">
              <a
                href={sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'var(--text-dim)', display: 'inline-flex' }}
                aria-label={`Xem nguồn ${label}`}
              >
                <ExternalLink size={13} />
              </a>
            </Tooltip>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '12px' }}>
          <span
            className="tabular-nums"
            style={{
              fontSize: '26px',
              fontWeight: 600,
              fontFamily: 'var(--font-mono)',
              color: 'var(--text)',
            }}
          >
            {formatPercent(value)}
          </span>

          {isGrowth && !isZero && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '2px',
                fontSize: '11px',
                color: isPos ? 'var(--pos)' : 'var(--neg)',
                fontWeight: 500,
              }}
            >
              {isPos ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
              {isPos ? 'Tăng' : 'Giảm'}
            </span>
          )}
          {isGrowth && isZero && (
            <span style={{ color: 'var(--text-dim)', fontSize: '11px' }}>
              <Minus size={13} />
            </span>
          )}
        </div>
      </div>
    );
  };

  return (
    <Layout
      pageTitle={i18n.nav.overview}
      dataErrors={[error]}
      showCompanyFilter
      showBenchmarkFilter
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        
        {/* Loading state */}
        {loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
              {[1, 2, 3, 4].map((i) => (
                <Skeleton key={i} height={100} />
              ))}
            </div>
            <Skeleton height={380} />
          </div>
        )}

        {/* Error state */}
        {/* Loaded Data Content */}
        {data && !loading && (
          <>
            {/* KPI Section: MSFT */}
            {(selectedCompany === 'BOTH' || selectedCompany === 'MSFT') && (
              <section aria-labelledby="msft-kpis">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--msft)' }} />
                  <h2 id="msft-kpis" style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text)' }}>
                    Microsoft (MSFT) — Kỳ {formatQuarter(data.kpis.MSFT.latest_quarter)}
                  </h2>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
                  {renderKPICard(i18n.metrics.stock_return_1y, data.kpis.MSFT.stock_return_1y, undefined, true)}
                  {renderKPICard(i18n.metrics.revenue_growth_latest, data.kpis.MSFT.revenue_growth_latest, data.kpis.MSFT.revenue_source_url, true)}
                  {renderKPICard(i18n.metrics.operating_margin_latest, data.kpis.MSFT.operating_margin_latest)}
                  {renderKPICard(i18n.metrics.fcf_margin_latest, data.kpis.MSFT.fcf_margin_latest)}
                </div>
              </section>
            )}

            {/* KPI Section: GOOGL */}
            {(selectedCompany === 'BOTH' || selectedCompany === 'GOOGL') && (
              <section aria-labelledby="googl-kpis">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', marginTop: selectedCompany === 'BOTH' ? '8px' : '0' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: 'var(--googl)' }} />
                  <h2 id="googl-kpis" style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text)' }}>
                    Alphabet (GOOGL) — Kỳ {formatQuarter(data.kpis.GOOGL.latest_quarter)}
                  </h2>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
                  {renderKPICard(i18n.metrics.stock_return_1y, data.kpis.GOOGL.stock_return_1y, undefined, true)}
                  {renderKPICard(i18n.metrics.revenue_growth_latest, data.kpis.GOOGL.revenue_growth_latest, data.kpis.GOOGL.revenue_source_url, true)}
                  {renderKPICard(i18n.metrics.operating_margin_latest, data.kpis.GOOGL.operating_margin_latest)}
                  {renderKPICard(i18n.metrics.fcf_margin_latest, data.kpis.GOOGL.fcf_margin_latest)}
                </div>
              </section>
            )}

            {/* Normalized Price Comparison Chart */}
            <section
              style={{
                backgroundColor: 'var(--surface-1)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--radius-md)',
                padding: '20px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
                <div>
                  <h3 style={{ fontSize: '14px', fontWeight: 600 }}>Biểu đồ giá chuẩn hóa (Cơ sở 100)</h3>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>So sánh biến động thị trường trong 252 phiên gần nhất</p>
                </div>
              </div>
              <EChart
                option={priceChartOption}
                style={{ height: '380px', width: '100%' }}
                ariaLabel={`Giá chuẩn hóa của ${selectedCompany === 'BOTH' ? 'MSFT, GOOGL' : selectedCompany} và ${selectedBenchmark}`}
              />
            </section>

            {/* Business Comparison Quarterly Bar Chart */}
            <section
              style={{
                backgroundColor: 'var(--surface-1)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--radius-md)',
                padding: '20px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
                <div>
                  <h3 style={{ fontSize: '14px', fontWeight: 600 }}>Hiệu quả kinh doanh theo quý</h3>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    {availableQuarters.length > 0
                      ? `${availableQuarters.length} quý dữ liệu · ${formatQuarter(availableQuarters[0])}–${formatQuarter(availableQuarters[availableQuarters.length - 1])}`
                      : 'Chưa có dữ liệu theo quý'}
                  </p>
                </div>
                <Segmented
                  ariaLabel="Chỉ số hiệu quả kinh doanh"
                  options={[
                    { value: 'operating_margin', label: 'Biên hoạt động' },
                    { value: 'fcf_margin', label: 'Biên FCF' },
                    { value: 'revenue_growth_yoy', label: 'Tăng trưởng DT' },
                  ]}
                  value={businessMetric}
                  onChange={setBusinessMetric}
                  size="sm"
                />
              </div>
              <EChart
                option={businessChartOption}
                style={{ height: '340px', width: '100%' }}
                ariaLabel={`Hiệu quả kinh doanh theo quý của ${selectedCompany === 'BOTH' ? 'MSFT và GOOGL' : selectedCompany}`}
              />
            </section>
          </>
        )}

        {!loading && !data && <EmptyState>Không có dữ liệu tổng quan để hiển thị.</EmptyState>}
      </div>
    </Layout>
  );
};
