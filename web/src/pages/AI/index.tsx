import React, { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Layout } from '../../components/shell/Layout';
import { useAIAnalysis } from '../../data/hooks';
import { EChart } from '../../components/charts/EChart';
import { getThemeColors, getEChartsBaseOption } from '../../lib/echarts-theme';
import { formatPValue, formatDate } from '../../lib/format';
import { Skeleton } from '../../components/ui/Skeleton';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { ExternalLink, Sparkles, Clock } from 'lucide-react';
import { i18n } from '../../i18n/vi';
import { useThemeMode } from '../../lib/use-theme-mode';
import { getCompanyFilter } from '../../lib/filters';

export const AIPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedCompany = getCompanyFilter(searchParams.get('company'));
  const selectedCompanies: Array<'MSFT' | 'GOOGL'> = selectedCompany === 'BOTH'
    ? ['MSFT', 'GOOGL']
    : [selectedCompany];

  const { data, loading, error } = useAIAnalysis();

  // Lag slider k = 0..4 (UI-12)
  const requestedLag = Number(searchParams.get('lag'));
  const lagK = Number.isInteger(requestedLag) && requestedLag >= 0 && requestedLag <= 4
    ? requestedLag
    : 1;
  const [selectedEventIndex, setSelectedEventIndex] = useState<number | null>(null);

  const handleLagChange = (nextLag: number) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('lag', String(nextLag));
    setSearchParams(nextParams, { replace: true });
  };

  const isDark = useThemeMode();
  const colors = getThemeColors(isDark);

  // Quarterly AI Indicators Chart with Events Overlay
  const indicatorsChartOption = useMemo(() => {
    if (!data?.indicators) return {};
    const baseOpt = getEChartsBaseOption(isDark);
    const quarters = [...new Set(selectedCompanies.flatMap((company) =>
      data.indicators[company].map((item) => item.calendar_key)
    ))].sort();
    const indicatorsByCompany = selectedCompanies.map((company) => {
      const byQuarter = new Map(data.indicators[company].map((item) => [item.calendar_key, item]));
      return { company, byQuarter };
    });

    return {
      ...baseOpt,
      tooltip: {
        ...baseOpt.tooltip,
        trigger: 'axis',
      },
      legend: {
        ...baseOpt.legend,
        data: selectedCompanies.flatMap((company) => [`${company} · R&D`, `${company} · CapEx`]),
      },
      xAxis: {
        ...baseOpt.xAxis,
        type: 'category',
        data: quarters,
      },
      yAxis: {
        ...baseOpt.yAxis,
        name: '%',
        type: 'value',
      },
      series: indicatorsByCompany.flatMap(({ company, byQuarter }) => {
        const color = company === 'MSFT' ? colors.msft : colors.googl;
        const seriesData = (key: 'rd_growth_yoy' | 'capex_growth_yoy') => quarters.map((quarter) => {
          const value = byQuarter.get(quarter)?.[key];
          return value !== null && value !== undefined ? Number((value * 100).toFixed(1)) : null;
        });
        return [
          {
            name: `${company} · R&D`,
            type: 'line',
            data: seriesData('rd_growth_yoy'),
            itemStyle: { color },
            lineStyle: { width: 2, color },
            showSymbol: true,
            symbol: 'circle',
            symbolSize: 6,
          },
          {
            name: `${company} · CapEx`,
            type: 'line',
            data: seriesData('capex_growth_yoy'),
            itemStyle: { color },
            lineStyle: { width: 2, color, type: 'dashed' },
            showSymbol: true,
            symbol: 'rect',
            symbolSize: 6,
          },
        ];
      }),
    };
  }, [data, selectedCompany, isDark, colors]);

  const rows = ['rd_growth_yoy', 'capex_growth_yoy'];
  const cols = ['revenue_growth_yoy', 'fcf_growth_yoy', 'operating_margin', 'stock_return_quarter'];

  const getColLabel = (c: string) => {
    switch (c) {
      case 'revenue_growth_yoy': return 'Tăng trưởng DT';
      case 'fcf_growth_yoy': return 'Tăng trưởng FCF';
      case 'operating_margin': return 'Biên HĐ';
      case 'stock_return_quarter': return 'Lợi suất CP';
      default: return c;
    }
  };

  const getRowLabel = (r: string) => {
    switch (r) {
      case 'rd_growth_yoy': return 'Tăng trưởng R&D';
      case 'capex_growth_yoy': return 'Tăng trưởng CapEx';
      default: return r;
    }
  };

  return (
    <Layout pageTitle={i18n.nav.ai} dataErrors={[error]} showCompanyFilter>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        
        {/* Section 1: Lagged Correlation Matrix Heatmap (UI-12, FR-30) */}
        <section
          style={{
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
            padding: '24px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '20px', flexWrap: 'wrap', gap: '16px' }}>
            <div>
              <h2 style={{ fontSize: '15px', fontWeight: 600 }}>Ma trận tương quan đầu tư AI</h2>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Chi tiêu R&D, CapEx liên hệ thế nào với các chỉ số tài chính sau k quý
              </p>
              {selectedCompany === 'BOTH' && (
                <div aria-label="Chú giải doanh nghiệp" style={{ display: 'flex', gap: '14px', marginTop: '10px' }}>
                  {[
                    { ticker: 'MSFT', name: 'Microsoft', color: 'var(--msft)' },
                    { ticker: 'GOOGL', name: 'Alphabet', color: 'var(--googl)' },
                  ].map((company) => (
                    <span key={company.ticker} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--text-muted)' }}>
                      <span aria-hidden="true" style={{ width: '7px', height: '7px', borderRadius: '50%', backgroundColor: company.color }} />
                      {company.name} ({company.ticker})
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Slider k = 0..4 with keyboard support */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', backgroundColor: 'var(--surface-2)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--line)' }}>
              <Clock size={15} style={{ color: 'var(--text-muted)' }} />
              <label htmlFor="lag-slider" style={{ display: 'flex', flexDirection: 'column', fontSize: '11px', color: 'var(--text-muted)', lineHeight: 1.3 }}>
                Độ trễ
                <strong style={{ color: 'var(--text)', fontSize: '12px' }}>{lagK} quý</strong>
              </label>
              <input
                id="lag-slider"
                type="range"
                min="0"
                max="4"
                step="1"
                value={lagK}
                onChange={(e) => handleLagChange(Number(e.target.value))}
                style={{ width: '120px', cursor: 'pointer' }}
                aria-valuemin={0}
                aria-valuemax={4}
                aria-valuenow={lagK}
                aria-label="Chọn độ trễ k quý"
              />
            </div>
          </div>

          {loading ? (
            <Skeleton height={200} />
          ) : data ? (
            <div style={{ overflowX: 'auto' }}>
              <div
                role="table"
                aria-label="Ma trận tương quan theo doanh nghiệp"
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'minmax(120px, 0.9fr) repeat(4, minmax(130px, 1fr))',
                  gap: '8px',
                  minWidth: '700px',
                }}
              >
                <div role="row" style={{ display: 'contents' }}>
                  <div role="columnheader" />
                  {cols.map((col) => (
                    <div
                      key={col}
                      role="columnheader"
                      style={{
                        padding: '6px 8px',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: 'var(--text-muted)',
                        textAlign: 'center',
                        alignSelf: 'end',
                      }}
                    >
                      {getColLabel(col)}
                    </div>
                  ))}
                </div>

                {rows.map((rowKey) => (
                  <div key={rowKey} role="row" style={{ display: 'contents' }}>
                    <div
                      role="rowheader"
                      style={{
                        padding: '12px 8px',
                        fontSize: '12px',
                        fontWeight: 600,
                        color: 'var(--text)',
                        display: 'flex',
                        alignItems: 'center',
                        borderTop: '1px solid var(--line)',
                      }}
                    >
                      {getRowLabel(rowKey)}
                    </div>

                    {cols.map((colKey) => (
                      <div
                        key={colKey}
                        role="cell"
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'center',
                          gap: '6px',
                          padding: '8px 10px',
                          backgroundColor: 'var(--surface-2)',
                          border: '1px solid var(--line)',
                          borderRadius: 'var(--radius-sm)',
                        }}
                      >
                        {selectedCompanies.map((company) => {
                          const item = data?.correlations.find(
                            (correlation) => correlation.ticker === company
                              && correlation.lag === lagK
                              && correlation.x === rowKey
                              && correlation.y === colKey
                          );
                          const r = item?.statistic;
                          const n = item?.n;
                          const pAdjusted = item?.p_adjusted ?? item?.p_value;
                          const companyColor = company === 'MSFT' ? 'var(--msft)' : 'var(--googl)';

                          return (
                            <div
                              key={company}
                              aria-label={`${company}, r ${r !== undefined ? r.toFixed(2) : 'không có dữ liệu'}, p ${item ? formatPValue(pAdjusted) : 'không có dữ liệu'}, n ${n ?? 'không có dữ liệu'}${n !== undefined && n < 30 ? ', mẫu nhỏ' : ''}`}
                              style={{
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'stretch',
                                gap: '3px',
                                padding: '5px 7px',
                                borderLeft: `2px solid ${companyColor}`,
                                borderRadius: '2px',
                                backgroundColor: company === 'MSFT' ? 'var(--surface-1)' : 'var(--surface-hover)',
                              }}
                            >
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
                                <span style={{ fontSize: '10px', fontWeight: 600, color: companyColor }}>
                                  {company}
                                </span>
                                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                                  r = {r !== undefined ? r.toFixed(2).replace('.', ',') : '—'}
                                </span>
                              </div>
                              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--text-dim)' }}>
                                <span>p = {item ? formatPValue(pAdjusted) : '—'}</span>
                                <span>n = {n ?? '—'}{n !== undefined && n < 30 ? '*' : ''}</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          ) : <EmptyState>Chưa có dữ liệu tương quan cho doanh nghiệp đã chọn.</EmptyState>}

          <div style={{ marginTop: '14px', fontSize: '11px', color: 'var(--text-dim)' }}>
            <strong style={{ color: 'var(--text-muted)' }}>r</strong> là hệ số tương quan · <strong style={{ color: 'var(--text-muted)' }}>p</strong> là xác suất đã hiệu chỉnh · <strong style={{ color: 'var(--text-muted)' }}>n</strong> là số quan sát · * mẫu nhỏ (dưới 30), chỉ mang tính tham khảo.
          </div>
        </section>

        {/* Section 2: Quarterly AI Indicators */}
        <section
          style={{
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
            padding: '20px',
          }}
        >
          <div style={{ marginBottom: '16px' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600 }}>
              Tăng trưởng R&D và CapEx theo quý{selectedCompany === 'BOTH' ? '' : ` (${selectedCompany})`}
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Chỉ số đầu vào chi tiêu hạ tầng & nghiên cứu AI</p>
          </div>
          {loading ? (
            <Skeleton height={320} />
          ) : selectedCompanies.some((company) => (data?.indicators[company].length ?? 0) > 0) ? (
            <EChart
              option={indicatorsChartOption}
              style={{ height: '320px', width: '100%' }}
              ariaLabel={`Tăng trưởng R&D và CapEx theo quý của ${selectedCompanies.join(' và ')}`}
            />
          ) : <EmptyState>Chưa có dữ liệu chi tiêu R&D và CapEx.</EmptyState>}
        </section>

        {/* Section 3: Timeline of 18 AI Events (FR-29) */}
        {data && (
          <section
            style={{
              backgroundColor: 'var(--surface-1)',
              border: '1px solid var(--line)',
              borderRadius: 'var(--radius-md)',
              padding: '24px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
              <Sparkles size={16} style={{ color: 'var(--msft)' }} />
              <h3 style={{ fontSize: '14px', fontWeight: 600 }}>Dòng sự kiện AI & Trích dẫn bằng chứng ({data.events.length} sự kiện)</h3>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
              {data.events.length === 0 ? (
                <EmptyState>Chưa có sự kiện AI trong bộ dữ liệu hiện tại.</EmptyState>
              ) : data.events.map((ev, idx) => {
                const isSelected = selectedEventIndex === idx;
                return (
                  <div
                    key={idx}
                    style={{
                      padding: '14px',
                      backgroundColor: 'var(--surface-2)',
                      border: isSelected ? '1px solid var(--focus-ring)' : '1px solid var(--line)',
                      borderRadius: 'var(--radius-sm)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                      transition: 'border-color var(--duration-fast) var(--ease-spring), background-color var(--duration-fast) var(--ease-spring)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {formatDate(ev.published_date)}
                      </span>
                      <Badge tone={ev.label === 'Reported' ? 'positive' : ev.label === 'Proxy' ? 'neutral' : 'caution'}>
                        {ev.label}
                      </Badge>
                    </div>

                    <button
                      type="button"
                      aria-expanded={isSelected}
                      aria-controls={`ai-event-${idx}`}
                      onClick={() => setSelectedEventIndex(isSelected ? null : idx)}
                      style={{
                        textAlign: 'left',
                        color: 'var(--text)',
                        fontSize: '13px',
                        fontWeight: 600,
                        lineHeight: 1.4,
                      }}
                    >
                      {ev.title}
                    </button>

                    {isSelected && (
                      <div id={`ai-event-${idx}`} style={{ fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                        <div style={{ marginBottom: '6px' }}>{ev.category}</div>
                        <div style={{ fontStyle: 'italic' }}>“{ev.evidence_quote}”</div>
                        {ev.source_url && (
                          <div style={{ marginTop: '8px', textAlign: 'right' }}>
                        <a
                          href={ev.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            fontSize: '11px',
                            color: 'var(--text-dim)',
                          }}
                        >
                          <span>Xem nguồn</span>
                          <ExternalLink size={11} />
                        </a>
                      </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </div>
    </Layout>
  );
};
