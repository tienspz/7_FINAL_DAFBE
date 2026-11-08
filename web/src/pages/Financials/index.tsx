import React, { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Layout } from '../../components/shell/Layout';
import { useFinancials } from '../../data/hooks';
import { EChart } from '../../components/charts/EChart';
import { getThemeColors, getEChartsBaseOption } from '../../lib/echarts-theme';
import { formatPercent, formatDate, formatNumber } from '../../lib/format';
import { Skeleton } from '../../components/ui/Skeleton';
import { Segmented } from '../../components/ui/Segmented';
import { Tooltip } from '../../components/ui/Tooltip';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { ExternalLink, AlertTriangle, Search } from 'lucide-react';
import { i18n } from '../../i18n/vi';
import { useThemeMode } from '../../lib/use-theme-mode';
import { getCompanyFilter } from '../../lib/filters';

type SortKey = 'calendar_key' | 'ticker' | 'revenue';

function Sparkline({ values, label }: { values: Array<number | null | undefined>; label: string }) {
  const valid = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (valid.length < 2) {
    return <span aria-label={`${label}: chưa đủ dữ liệu`}>—</span>;
  }

  const min = Math.min(...valid);
  const range = Math.max(...valid) - min || 1;
  const points = values.map((value, index) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return null;
    return `${(index / Math.max(values.length - 1, 1)) * 80},${22 - ((value - min) / range) * 20}`;
  });
  const segments = points.slice(1).flatMap((point, index) =>
    point && points[index]
      ? [`M${points[index]} L${point}`]
      : []
  );

  return (
    <svg
      role="img"
      aria-label={label}
      viewBox="0 0 80 24"
      width="80"
      height="24"
      focusable="false"
    >
      <path d={segments.join(' ')} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
    </svg>
  );
}

export const FinancialsPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const selectedCompany = getCompanyFilter(searchParams.get('company'));

  const { data, loading, error } = useFinancials();
  const requestedQuarter = searchParams.get('q');
  const selectedQuarter = data?.quarters.some((quarter) => quarter.calendar_key === requestedQuarter)
    ? requestedQuarter
    : undefined;

  const [activeMetric, setActiveMetric] = useState<string>('revenue_growth_yoy');
  const [searchFilter, setSearchFilter] = useState('');
  const [sort, setSort] = useState<{ key: SortKey; direction: 'ascending' | 'descending' }>({
    key: 'calendar_key',
    direction: 'descending',
  });

  const isDark = useThemeMode();
  const colors = getThemeColors(isDark);

  const METRIC_TABS = [
    { value: 'revenue_growth_yoy', label: 'Tăng trưởng DT (YoY)' },
    { value: 'operating_margin', label: 'Biên lợi nhuận HĐ' },
    { value: 'fcf_margin', label: 'Biên FCF' },
    { value: 'rd_intensity', label: 'Tỷ trọng R&D' },
    { value: 'capex_intensity', label: 'Tỷ trọng CapEx' },
    { value: 'roe', label: 'ROE' },
    { value: 'roic', label: 'ROIC' },
  ];

  // Align both companies by calendar quarter so missing periods never shift values.
  const chartOption = useMemo(() => {
    if (!data?.quarters) return {};
    const baseOpt = getEChartsBaseOption(isDark);

    const quartersByCompany = {
      MSFT: new Map(data.quarters.filter((q) => q.ticker === 'MSFT').map((q) => [q.calendar_key, q])),
      GOOGL: new Map(data.quarters.filter((q) => q.ticker === 'GOOGL').map((q) => [q.calendar_key, q])),
    };
    const calendarKeys = [...new Set(data.quarters.map((quarter) => quarter.calendar_key))].sort();
    const getValues = (ticker: 'MSFT' | 'GOOGL') => calendarKeys.map((key) => {
      const value = quartersByCompany[ticker].get(key)?.derived_metrics?.[activeMetric];
      return value !== null && value !== undefined ? Number((value * 100).toFixed(1)) : null;
    });

    const series = [];

    if (selectedCompany === 'BOTH' || selectedCompany === 'MSFT') {
      series.push({
        name: 'Microsoft (MSFT)',
        type: 'line',
        data: getValues('MSFT'),
        itemStyle: { color: colors.msft },
        lineStyle: { width: 2, color: colors.msft },
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 6,
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
        type: 'line',
        data: getValues('GOOGL'),
        itemStyle: { color: colors.googl },
        lineStyle: { width: 2, color: colors.googl },
        showSymbol: true,
        symbol: 'rect',
        symbolSize: 6,
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

    return {
      ...baseOpt,
      tooltip: {
        ...baseOpt.tooltip,
        formatter: (params: any) => {
          if (!params || !params.length) return '';
          let res = `<div style="font-size:11px; margin-bottom:4px; font-weight:600;">Quý: ${params[0]?.axisValue}</div>`;
          params.forEach((p: any) => {
            res += `<div style="display:flex; justify-content:space-between; gap:16px;">
              <span>${p.marker} ${p.seriesName}</span>
              <span style="font-weight:600; font-family:var(--font-mono);">${p.value !== null ? p.value + '%' : '—'}</span>
            </div>`;
          });
          return res;
        },
      },
      legend: {
        ...baseOpt.legend,
        data: series.map((s) => s.name),
        formatter: (name: string) => name.includes('(MSFT)') ? 'MSFT' : 'GOOGL',
      },
      xAxis: {
        ...baseOpt.xAxis,
        type: 'category',
        data: calendarKeys,
      },
      yAxis: {
        ...baseOpt.yAxis,
        name: '%',
        type: 'value',
      },
      series,
    };
  }, [data, activeMetric, selectedCompany, selectedQuarter, isDark, colors]);

  // Filtered quarters for data table (UI-13)
  const filteredQuarters = useMemo(() => {
    if (!data?.quarters) return [];
    const filtered = data.quarters.filter((q) => {
      const matchCompany = selectedCompany === 'BOTH' || q.ticker === selectedCompany;
      const matchSearch =
        !searchFilter ||
        q.calendar_key.toLowerCase().includes(searchFilter.toLowerCase()) ||
        q.ticker.toLowerCase().includes(searchFilter.toLowerCase());
      return matchCompany && matchSearch;
    });

    return filtered.sort((left, right) => {
      const leftValue = sort.key === 'revenue'
        ? left.metrics?.revenue?.value ?? Number.NEGATIVE_INFINITY
        : left[sort.key];
      const rightValue = sort.key === 'revenue'
        ? right.metrics?.revenue?.value ?? Number.NEGATIVE_INFINITY
        : right[sort.key];
      const comparison = typeof leftValue === 'number' && typeof rightValue === 'number'
        ? leftValue - rightValue
        : String(leftValue).localeCompare(String(rightValue));
      return sort.direction === 'ascending' ? comparison : -comparison;
    });
  }, [data, selectedCompany, searchFilter, sort]);

  const setSortKey = (key: SortKey) => {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === 'ascending' ? 'descending' : 'ascending',
    }));
  };

  // Cloud segments comparison (FR-21)
  const cloudSegments = useMemo(() => {
    if (!data?.segments) return [];
    return data.segments.filter(
      (segment) =>
        segment.comparable &&
        (selectedCompany === 'BOTH' || segment.ticker === selectedCompany) &&
        (segment.segment_name.includes('Cloud') || segment.segment_name.includes('Intelligent'))
    );
  }, [data, selectedCompany]);

  return (
    <Layout
      pageTitle={i18n.nav.financials}
      dataErrors={[error]}
      showCompanyFilter
      showQuarterRuler
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        
        {/* Metric Selector Tabs */}
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
              <h2 style={{ fontSize: '15px', fontWeight: 600 }}>Chỉ số tài chính & Hiệu quả vốn</h2>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Quy đổi năm tài chính về quý lịch (Calendar Quarter)</p>
            </div>
            <Segmented
              ariaLabel="Chỉ số tài chính"
              options={METRIC_TABS}
              value={activeMetric}
              onChange={setActiveMetric}
              size="sm"
            />
          </div>

          {loading ? (
            <Skeleton height={360} />
          ) : data?.quarters?.length ? (
            <EChart
              option={chartOption}
              style={{ height: '360px', width: '100%' }}
              ariaLabel={`So sánh ${activeMetric} theo quý`}
            />
          ) : <EmptyState>Chưa có dữ liệu tài chính để hiển thị biểu đồ.</EmptyState>}
        </section>

        {/* Section 2: Cloud Segments Comparison (FR-21) */}
        {cloudSegments.length > 0 && (
          <section
            style={{
              backgroundColor: 'var(--surface-1)',
              border: '1px solid var(--line)',
              borderRadius: 'var(--radius-md)',
              padding: '20px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div>
                <h3 style={{ fontSize: '14px', fontWeight: 600 }}>Phân khúc Đám mây (Cloud Segment)</h3>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Doanh thu phân khúc được công bố; chỉ hiển thị các kỳ có phạm vi tương đương.
                </p>
              </div>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--line)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '8px' }}>Quý lịch</th>
                    <th style={{ padding: '8px' }}>Công ty</th>
                    <th style={{ padding: '8px' }}>Phân khúc</th>
                    <th style={{ padding: '8px', textAlign: 'right' }}>Doanh thu ($M)</th>
                    <th style={{ padding: '8px', textAlign: 'center' }}>Tính tương thích</th>
                  </tr>
                </thead>
                <tbody>
                  {cloudSegments.map((seg, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid var(--line)' }}>
                      <td style={{ padding: '8px', fontFamily: 'var(--font-mono)' }}>{seg.calendar_key}</td>
                      <td style={{ padding: '8px' }}>
                        <Badge tone={seg.ticker === 'MSFT' ? 'msft' : 'googl'}>{seg.ticker}</Badge>
                      </td>
                      <td style={{ padding: '8px' }}>{seg.segment_name}</td>
                      <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                        {formatNumber(seg.value_musd)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'center' }}>
                        <Badge tone="positive">Tương đương</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Section 3: Interactive Metrics Table with Source Links & Low-Quality Flags (UI-13, FR-65) */}
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
              <h3 style={{ fontSize: '14px', fontWeight: 600 }}>Bảng chi tiết chỉ số báo cáo tài chính</h3>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Truy vết từng dòng số liệu kèm ngày kết thúc kỳ thực tế và liên kết SEC 10-Q/10-K
              </p>
            </div>

            <div style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: '10px', top: '10px', color: 'var(--text-dim)' }} />
              <input
                type="text"
                name="financial-quarter-search"
                aria-label="Tìm theo quý hoặc mã cổ phiếu"
                autoComplete="off"
                placeholder="Tìm theo quý hoặc mã..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                style={{
                  padding: '6px 10px 6px 32px',
                  backgroundColor: 'var(--surface-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '12px',
                  color: 'var(--text)',
                }}
              />
              {searchFilter && (
                <button
                  type="button"
                  onClick={() => setSearchFilter('')}
                  style={{ marginTop: '4px', fontSize: '11px', color: 'var(--text-muted)', textDecoration: 'underline' }}
                >
                  Xóa tìm kiếm
                </button>
              )}
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--line-strong)', color: 'var(--text-muted)' }}>
                  <th
                    scope="col"
                    aria-sort={sort.key === 'calendar_key' ? sort.direction : 'none'}
                    style={{ padding: '8px' }}
                  >
                    <button type="button" onClick={() => setSortKey('calendar_key')}>Quý</button>
                  </th>
                  <th style={{ padding: '8px' }}>Kỳ thực</th>
                  <th
                    scope="col"
                    aria-sort={sort.key === 'ticker' ? sort.direction : 'none'}
                    style={{ padding: '8px' }}
                  >
                    <button type="button" onClick={() => setSortKey('ticker')}>Mã</button>
                  </th>
                  <th
                    scope="col"
                    aria-sort={sort.key === 'revenue' ? sort.direction : 'none'}
                    style={{ padding: '8px', textAlign: 'right' }}
                  >
                    <button type="button" onClick={() => setSortKey('revenue')}>Doanh thu</button>
                  </th>
                  <th style={{ padding: '8px', textAlign: 'right' }}>Tăng trưởng YoY</th>
                  <th style={{ padding: '8px', textAlign: 'right' }}>Biên HĐ</th>
                  <th style={{ padding: '8px', textAlign: 'right' }}>Biên FCF</th>
                  <th style={{ padding: '8px', textAlign: 'right' }}>R&D</th>
                  <th style={{ padding: '8px', textAlign: 'right' }}>CapEx</th>
                  <th style={{ padding: '8px', textAlign: 'center' }}>Xu hướng doanh thu</th>
                  <th style={{ padding: '8px', textAlign: 'center' }}>Nguồn</th>
                </tr>
              </thead>
              <tbody>
                {filteredQuarters.length === 0 ? (
                  <tr>
                    <td colSpan={11} role="status" style={{ padding: '24px 8px', textAlign: 'center', color: 'var(--text-muted)' }}>
                      {searchFilter ? 'Không tìm thấy kỳ phù hợp. Thử tìm theo quý hoặc mã MSFT, GOOGL.' : 'Không có dữ liệu cho doanh nghiệp hoặc kỳ đã chọn.'}
                    </td>
                  </tr>
                ) : filteredQuarters.map((q, idx) => {
                  const rev = q.metrics?.revenue;
                  const isLowQuality = rev?.quality === 'low';
                  const revGrowth = q.derived_metrics?.revenue_growth_yoy;
                  const opMargin = q.derived_metrics?.operating_margin;
                  const fcfMargin = q.derived_metrics?.fcf_margin;
                  const rdInt = q.derived_metrics?.rd_intensity;
                  const capexInt = q.derived_metrics?.capex_intensity;

                  return (
                    <tr
                      key={idx}
                      aria-current={q.calendar_key === selectedQuarter ? 'true' : undefined}
                      style={{
                        borderBottom: '1px solid var(--line)',
                        backgroundColor: q.calendar_key === selectedQuarter ? 'var(--surface-hover)' : undefined,
                      }}
                    >
                      <td style={{ padding: '8px', fontFamily: 'var(--font-mono)' }}>{q.calendar_key}</td>
                      <td style={{ padding: '8px', color: 'var(--text-muted)', fontSize: '11px' }}>
                        {formatDate(q.period_end)}
                      </td>
                      <td style={{ padding: '8px' }}>
                        <Badge tone={q.ticker === 'MSFT' ? 'msft' : 'googl'}>{q.ticker}</Badge>
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          {isLowQuality && (
                            <Tooltip content="Số liệu sơ bộ; cần đối chiếu lại">
                              <AlertTriangle size={12} style={{ color: 'var(--neu)' }} />
                            </Tooltip>
                          )}
                          {formatNumber(rev?.value)}
                        </span>
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                        {formatPercent(revGrowth)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                        {formatPercent(opMargin)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                        {formatPercent(fcfMargin)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                        {formatPercent(rdInt)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                        {formatPercent(capexInt)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'center' }}>
                        <Sparkline
                          label={`${q.ticker} doanh thu qua các quý đến ${q.calendar_key}`}
                          values={(data?.quarters ?? [])
                            .filter((quarter) => quarter.ticker === q.ticker)
                            .sort((left, right) => left.calendar_key.localeCompare(right.calendar_key))
                            .map((quarter) => quarter.metrics?.revenue?.value)}
                        />
                      </td>
                      <td style={{ padding: '8px', textAlign: 'center' }}>
                        {rev?.source_url ? (
                          <a
                            href={rev.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: 'var(--text-dim)' }}
                            aria-label={`Xem nguồn doanh thu ${q.ticker} ${q.calendar_key}`}
                            title="Mở hồ sơ SEC EDGAR"
                          >
                            <ExternalLink size={13} />
                          </a>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Layout>
  );
};
