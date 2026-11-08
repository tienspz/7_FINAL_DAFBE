import React, { useState, useMemo, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Layout } from '../../components/shell/Layout';
import { useInvestor, usePrices } from '../../data/hooks';
import { EChart } from '../../components/charts/EChart';
import { getThemeColors, getEChartsBaseOption } from '../../lib/echarts-theme';
import { formatCurrency, formatPercent, formatRawPercent, formatPValue, formatDate } from '../../lib/format';
import { calculateInvestment, CalculatorResult } from '../../lib/finance';
import { Skeleton } from '../../components/ui/Skeleton';
import { Segmented } from '../../components/ui/Segmented';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { Download, Bookmark, Trash2, ArrowRight, ImageDown, AlertTriangle } from 'lucide-react';
import { i18n } from '../../i18n/vi';
import { useThemeMode } from '../../lib/use-theme-mode';
import { getBenchmarkFilter } from '../../lib/filters';

interface SavedScenario {
  id: string;
  name: string;
  ticker: 'MSFT' | 'GOOGL';
  capital: number;
  dateBuy: string;
  dateEval: string;
  finalValue: number;
  profit: number;
  roi: number;
}

export const InvestorPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const selectedBenchmark = getBenchmarkFilter(searchParams.get('bench'));

  // Calculator State
  const [calcTicker, setCalcTicker] = useState<'MSFT' | 'GOOGL'>('MSFT');
  const [capital, setCapital] = useState<number>(1000);
  const [fees, setFees] = useState<number>(0);
  const [dateBuy, setDateBuy] = useState<string>('2022-01-03');
  const [dateEval, setDateEval] = useState<string>('2026-09-30');
  const [calcError, setCalcError] = useState<string | null>(null);
  const [calcResult, setCalcResult] = useState<CalculatorResult | null>(null);
  const [storageError, setStorageError] = useState(false);
  const [chartReady, setChartReady] = useState(false);
  const chartInstance = useRef<import('echarts/core').ECharts | null>(null);

  // Price Mode: absolute vs normalized (UI-10)
  const [priceMode, setPriceMode] = useState<'normalized' | 'absolute'>('normalized');
  const [returnPeriod, setReturnPeriod] = useState<'monthly' | 'quarterly'>('monthly');

  // Scenarios State (saved in localStorage)
  const [scenarios, setScenarios] = useState<SavedScenario[]>([]);
  const persistScenarios = (nextScenarios: SavedScenario[]) => {
    setScenarios(nextScenarios);
    try {
      localStorage.setItem('aicor-saved-scenarios', JSON.stringify(nextScenarios));
      setStorageError(false);
    } catch {
      setStorageError(true);
    }
  };

  useEffect(() => {
    try {
      const saved = localStorage.getItem('aicor-saved-scenarios');
      if (!saved) return;
      const parsed: unknown = JSON.parse(saved);
      if (
        Array.isArray(parsed) &&
        parsed.every((scenario) =>
          scenario &&
          typeof scenario.id === 'string' &&
          typeof scenario.name === 'string' &&
          (scenario.ticker === 'MSFT' || scenario.ticker === 'GOOGL') &&
          typeof scenario.capital === 'number' &&
          typeof scenario.dateBuy === 'string' &&
          typeof scenario.dateEval === 'string' &&
          typeof scenario.finalValue === 'number' &&
          typeof scenario.profit === 'number' &&
          typeof scenario.roi === 'number'
        )
      ) {
        setScenarios(parsed.slice(0, 10));
      }
    } catch {
      setStorageError(true);
    }
  }, []);

  const { data: investorData, loading: investorLoading, error: investorError } = useInvestor();
  const { data: pricesData, loading: pricesLoading, snapshotVersion, error: pricesError } = usePrices(calcTicker);
  const { data: benchmarkData, error: benchmarkError } = usePrices(selectedBenchmark);

  const benchmarkComparison = useMemo(() => {
    if (!calcResult) return null;
    if (!benchmarkData?.rows?.length) {
      return { roi: null, error: `Chưa có dữ liệu ${selectedBenchmark} để so sánh.` };
    }
    try {
      const result = calculateInvestment(benchmarkData.rows, { capital, fees, dateBuy, dateEval });
      return { roi: result.roi, error: null };
    } catch (error) {
      return {
        roi: null,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }, [calcResult, benchmarkData, capital, fees, dateBuy, dateEval, selectedBenchmark]);

  const isDark = useThemeMode();
  const colors = getThemeColors(isDark);

  // Run calculation when prices load or inputs change
  useEffect(() => {
    if (!pricesData?.rows || pricesData.rows.length === 0) return;
    try {
      const res = calculateInvestment(pricesData.rows, {
        capital,
        fees,
        dateBuy,
        dateEval,
      });
      setCalcResult(res);
      setCalcError(null);
    } catch (err) {
      setCalcError(err instanceof Error ? err.message : String(err));
      setCalcResult(null);
    }
  }, [pricesData, capital, fees, dateBuy, dateEval]);

  // Save Scenario (FR-58)
  const handleSaveScenario = () => {
    if (!calcResult) return;
    const newScenario: SavedScenario = {
      id: Date.now().toString(),
      name: `Kịch bản ${calcTicker} (${formatDate(dateBuy)} - ${formatDate(dateEval)})`,
      ticker: calcTicker,
      capital,
      dateBuy,
      dateEval,
      finalValue: calcResult.finalValue,
      profit: calcResult.profit,
      roi: calcResult.roi,
    };
    persistScenarios([newScenario, ...scenarios.slice(0, 9)]);
  };

  const handleDeleteScenario = (id: string) => {
    if (!window.confirm('Xóa kịch bản đầu tư này?')) return;
    persistScenarios(scenarios.filter((s) => s.id !== id));
  };

  const handleRenameScenario = (id: string, name: string) => {
    persistScenarios(scenarios.map((scenario) =>
      scenario.id === id ? { ...scenario, name } : scenario
    ));
  };

  // Export CSV (FR-55, FR-57)
  const handleExportCSV = () => {
    if (!calcResult) return;
    const headers = ['Ma_co_phieu', 'Von_dau_tu', 'Phi', 'Ngay_mua', 'Ngay_danh_gia', 'Gia_mua', 'Gia_danh_gia', 'Co_tuc', 'Gia_tri_cuoi', 'Loi_nhuan', 'ROI', 'Nguon_du_lieu', 'Phien_ban_snapshot'];
    const row = [
      calcTicker,
      capital,
      fees,
      calcResult.actualDateBuy,
      calcResult.actualDateEval,
      calcResult.buyPrice,
      calcResult.evalPrice,
      calcResult.totalDividends.toFixed(2),
      calcResult.finalValue.toFixed(2),
      calcResult.profit.toFixed(2),
      (calcResult.roi * 100).toFixed(2) + '%',
      pricesData?.source_url ?? `Dataset prices/${calcTicker}`,
      snapshotVersion ?? '—',
    ];
    const escapeCsv = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`;
    const csvContent = new Blob(
      [[headers, row].map((line) => line.map(escapeCsv).join(',')).join('\r\n')],
      { type: 'text/csv;charset=utf-8' }
    );
    const url = URL.createObjectURL(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `aicor_calculator_${calcTicker}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportPNG = () => {
    const chart = chartInstance.current;
    if (!chart) return;
    const link = document.createElement('a');
    link.href = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: colors.bg });
    link.download = `aicor_prices_${calcTicker}.png`;
    link.click();
  };

  // Historical Price Chart Option
  const priceChartOption = useMemo(() => {
    if (!pricesData?.rows || pricesData.rows.length === 0) return {};
    const baseOpt = getEChartsBaseOption(isDark);

    const rows = pricesData.rows;
    const dates = rows.map((r) => r.date);

    let stockValues: number[];
    let benchValues: number[] = [];

    if (priceMode === 'normalized') {
      const basePrice = rows[0]?.adj_close || 1;
      stockValues = rows.map((r) => (r.adj_close / basePrice) * 100);

      if (benchmarkData?.rows) {
        const baseBench = benchmarkData.rows[0]?.adj_close || 1;
        benchValues = benchmarkData.rows.map((r) => (r.adj_close / baseBench) * 100);
      }
    } else {
      stockValues = rows.map((r) => r.adj_close);
    }

    const series: any[] = [
      {
        name: calcTicker,
        type: 'line',
        data: stockValues,
        itemStyle: { color: calcTicker === 'MSFT' ? colors.msft : colors.googl },
        lineStyle: { width: 2, color: calcTicker === 'MSFT' ? colors.msft : colors.googl },
        showSymbol: false,
      },
    ];

    if (priceMode === 'normalized' && benchValues.length > 0) {
      series.push({
        name: `${selectedBenchmark} (Benchmark)`,
        type: 'line',
        data: benchValues,
        itemStyle: { color: colors.spy },
        lineStyle: { width: 1.5, type: 'dashed' as const, color: colors.spy },
        showSymbol: false,
      });
    }

    return {
      ...baseOpt,
      tooltip: {
        ...baseOpt.tooltip,
        trigger: 'axis',
      },
      legend: {
        ...baseOpt.legend,
        data: series.map((s) => s.name),
      },
      dataZoom: [{ type: 'inside' }, { type: 'slider', bottom: 0, height: 20 }],
      xAxis: {
        ...baseOpt.xAxis,
        type: 'category',
        data: dates,
      },
      yAxis: {
        ...baseOpt.yAxis,
        name: priceMode === 'normalized' ? 'Cơ sở 100' : 'USD ($)',
        type: 'value',
      },
      series,
    };
  }, [pricesData, benchmarkData, calcTicker, priceMode, selectedBenchmark, isDark, colors]);

  const returnsChartOption = useMemo(() => {
    if (!investorData) return {};
    const companyReturns = returnPeriod === 'monthly'
      ? investorData.monthly_returns[calcTicker]
      : investorData.quarterly_returns[calcTicker];
    const benchmarkReturns = returnPeriod === 'monthly'
      ? investorData.monthly_returns[selectedBenchmark]
      : investorData.quarterly_returns[selectedBenchmark];
    const benchmarkByPeriod = new Map(
      benchmarkReturns.map((item) => [
        'calendar_key' in item ? item.calendar_key : item.trade_date,
        item.return,
      ])
    );
    const periods = companyReturns.map((item) =>
      'calendar_key' in item ? item.calendar_key : item.trade_date
    );
    const baseOption = getEChartsBaseOption(isDark);

    return {
      ...baseOption,
      tooltip: {
        ...baseOption.tooltip,
        trigger: 'axis',
      },
      legend: {
        ...baseOption.legend,
        data: [calcTicker, selectedBenchmark],
      },
      dataZoom: [{ type: 'inside' }, { type: 'slider', bottom: 0, height: 20 }],
      xAxis: {
        ...baseOption.xAxis,
        type: 'category',
        data: periods,
      },
      yAxis: {
        ...baseOption.yAxis,
        type: 'value',
        name: '%',
      },
      series: [
        {
          name: calcTicker,
          type: 'bar',
          data: companyReturns.map((item) => Number((item.return * 100).toFixed(2))),
          itemStyle: { color: calcTicker === 'MSFT' ? colors.msft : colors.googl },
        },
        {
          name: selectedBenchmark,
          type: 'bar',
          data: periods.map((period) => {
            const value = benchmarkByPeriod.get(period);
            return value === undefined ? null : Number((value * 100).toFixed(2));
          }),
          itemStyle: { color: colors.spy },
        },
      ],
    };
  }, [investorData, returnPeriod, calcTicker, selectedBenchmark, isDark, colors]);

  const bt1 = investorData?.excess_return_tests?.MSFT;

  return (
    <Layout
      pageTitle={i18n.nav.investor}
      dataErrors={[investorError, pricesError, benchmarkError]}
      showBenchmarkFilter
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        
        {/* Section 1: Stock Investment Calculator (F1, FR-01..FR-10) */}
        <section
          aria-labelledby="calculator-heading"
          style={{
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
            padding: '24px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
            <div role="group" aria-label="Cổ phiếu tính toán">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h2 id="calculator-heading" style={{ fontSize: '16px', fontWeight: 600 }}>Máy tính đầu tư cổ phiếu</h2>
                <Badge tone="muted">{i18n.labels.illustration_tag}</Badge>
              </div>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Tính toán giá trị nắm giữ dựa trên giá đóng cửa thực tế và cổ tức nhận được
              </p>
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <Button size="sm" variant="outline" onClick={handleExportCSV} icon={<Download size={14} />}>
                {i18n.labels.export_csv}
              </Button>
              <Button size="sm" variant="secondary" onClick={handleSaveScenario} icon={<Bookmark size={14} />}>
                {i18n.labels.save_scenario}
              </Button>
            </div>
          </div>

          {/* Calculator Inputs Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '20px' }}>
            {/* Ticker */}
            <div>
              <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>Cổ phiếu</label>
              <Segmented
                ariaLabel="Cổ phiếu tính toán"
                options={[
                  { value: 'MSFT', label: 'Microsoft (MSFT)' },
                  { value: 'GOOGL', label: 'Alphabet (GOOGL)' },
                ]}
                value={calcTicker}
                onChange={setCalcTicker}
                size="sm"
              />
            </div>

            {/* Capital */}
            <div>
              <label htmlFor="capital-input" style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>
                Vốn đầu tư (USD)
              </label>
              <input
                id="capital-input"
                name="investment-capital"
                type="number"
                min="1"
                autoComplete="off"
                value={capital}
                onChange={(e) => setCapital(Number(e.target.value))}
                style={{
                  width: '100%',
                  padding: '6px 10px',
                  backgroundColor: 'var(--surface-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '13px',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text)',
                }}
              />
            </div>

            {/* Date Buy */}
            <div>
              <label htmlFor="date-buy" style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>
                Ngày mua
              </label>
              <input
                id="date-buy"
                name="investment-buy-date"
                type="date"
                autoComplete="off"
                value={dateBuy}
                onChange={(e) => setDateBuy(e.target.value)}
                style={{
                  width: '100%',
                  padding: '6px 10px',
                  backgroundColor: 'var(--surface-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '13px',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text)',
                }}
              />
            </div>

            {/* Date Eval */}
            <div>
              <label htmlFor="date-eval" style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>
                Ngày đánh giá
              </label>
              <input
                id="date-eval"
                name="investment-evaluation-date"
                type="date"
                autoComplete="off"
                value={dateEval}
                onChange={(e) => setDateEval(e.target.value)}
                style={{
                  width: '100%',
                  padding: '6px 10px',
                  backgroundColor: 'var(--surface-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '13px',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text)',
                }}
              />
            </div>

            {/* Fees */}
            <div>
              <label htmlFor="fees-input" style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>
                Phí giao dịch (USD)
              </label>
              <input
                id="fees-input"
                name="investment-fees"
                type="number"
                min="0"
                autoComplete="off"
                value={fees}
                onChange={(e) => setFees(Number(e.target.value))}
                style={{
                  width: '100%',
                  padding: '6px 10px',
                  backgroundColor: 'var(--surface-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '13px',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text)',
                }}
              />
            </div>
          </div>

          {/* Validation Error Message */}
          {calcError && (
            <div role="alert" aria-live="polite" style={{ color: 'var(--neg)', fontSize: '12px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <AlertTriangle size={14} aria-hidden="true" /> {calcError}
            </div>
          )}

          {/* Calculator Results */}
          {calcResult && (
            <div
              style={{
                backgroundColor: 'var(--surface-2)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--radius-md)',
                padding: '16px 20px',
              }}
            >
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '16px' }}>
                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Giá trị cuối (Vt)</span>
                  <div style={{ fontSize: '24px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
                    {formatCurrency(calcResult.finalValue)}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Lợi nhuận ròng</span>
                  <div
                    style={{
                      fontSize: '20px',
                      fontWeight: 600,
                      fontFamily: 'var(--font-mono)',
                      color: calcResult.profit >= 0 ? 'var(--pos)' : 'var(--neg)',
                    }}
                  >
                    {calcResult.profit >= 0 ? '+' : ''}{formatCurrency(calcResult.profit)}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Tỷ suất sinh lời (ROI)</span>
                  <div
                    style={{
                      fontSize: '20px',
                      fontWeight: 600,
                      fontFamily: 'var(--font-mono)',
                      color: calcResult.roi >= 0 ? 'var(--pos)' : 'var(--neg)',
                    }}
                  >
                    {formatPercent(calcResult.roi)}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Lợi suất quy năm</span>
                  <div style={{ fontSize: '20px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
                    {formatPercent(calcResult.annualizedRoi)}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>So với {selectedBenchmark}</span>
                  <div style={{ fontSize: '20px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: benchmarkComparison?.roi !== null && benchmarkComparison?.roi !== undefined && calcResult.roi >= benchmarkComparison.roi ? 'var(--pos)' : 'var(--neg)' }}>
                    {benchmarkComparison?.roi === null || benchmarkComparison?.roi === undefined
                      ? '—'
                      : formatPercent(calcResult.roi - benchmarkComparison.roi)}
                  </div>
                  {benchmarkComparison?.error && (
                    <span role="status" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                      {benchmarkComparison.error}
                    </span>
                  )}
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Số cổ phiếu / Cổ tức</span>
                  <div style={{ fontSize: '14px', fontFamily: 'var(--font-mono)', color: 'var(--text)', marginTop: '4px' }}>
                    {calcResult.shares.toFixed(2)} CP · {formatCurrency(calcResult.totalDividends)}
                  </div>
                </div>
              </div>

              {calcResult.notes.length > 0 && (
                <div style={{ borderTop: '1px solid var(--line)', marginTop: '12px', paddingTop: '8px', fontSize: '11px', color: 'var(--neu)' }}>
                  {calcResult.notes.map((n, idx) => (
                    <div key={idx}>ℹ {n}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>

        {/* Section 2: Saved Scenarios Comparison (F10, FR-58..60) */}
        {scenarios.length > 0 && (
          <section
            style={{
              backgroundColor: 'var(--surface-1)',
              border: '1px solid var(--line)',
              borderRadius: 'var(--radius-md)',
              padding: '20px',
            }}
          >
            <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px' }}>
              Kịch bản đầu tư đã lưu · So sánh ({scenarios.length})
            </h3>
            {storageError && (
              <p role="status" aria-live="polite" style={{ color: 'var(--neg)', fontSize: '12px', marginBottom: '10px' }}>
                Không thể lưu kịch bản trên thiết bị này.
              </p>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
              {scenarios.map((sc) => (
                <div
                  key={sc.id}
                  style={{
                    backgroundColor: 'var(--surface-2)',
                    border: '1px solid var(--line)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '12px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
                    <Badge tone={sc.ticker === 'MSFT' ? 'msft' : 'googl'}>{sc.ticker}</Badge>
                    <input
                      aria-label={`Tên kịch bản ${sc.ticker}`}
                      name={`scenario-${sc.id}`}
                      autoComplete="off"
                      value={sc.name}
                      onChange={(event) => handleRenameScenario(sc.id, event.target.value)}
                      style={{
                        flex: 1,
                        minWidth: 0,
                        padding: '4px 6px',
                        color: 'var(--text)',
                        background: 'transparent',
                        border: '1px solid var(--line)',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '11px',
                      }}
                    />
                    <button
                      onClick={() => handleDeleteScenario(sc.id)}
                      style={{ color: 'var(--text-dim)', cursor: 'pointer' }}
                      title="Xóa kịch bản"
                      aria-label={`Xóa kịch bản ${sc.name}`}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--text-muted)' }}>
                    {formatDate(sc.dateBuy)} <ArrowRight size={11} style={{ display: 'inline' }} /> {formatDate(sc.dateEval)}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', alignItems: 'baseline' }}>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Vốn: {formatCurrency(sc.capital)}</span>
                    <span style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: sc.profit >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                      {formatCurrency(sc.finalValue)} ({formatPercent(sc.roi)})
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Section 3: Historical Prices Chart (UI-10) */}
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
              <h3 style={{ fontSize: '14px', fontWeight: 600 }}>Biểu đồ giá lịch sử & Lợi suất tích lũy</h3>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Dữ liệu giá điều chỉnh từ 2020 đến 2026</p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <Segmented
                ariaLabel="Chế độ hiển thị giá"
                options={[
                  { value: 'normalized', label: 'Chuẩn hóa (Base 100)' },
                  { value: 'absolute', label: 'Giá tuyệt đối ($)' },
                ]}
                value={priceMode}
                onChange={setPriceMode}
                size="sm"
              />
              <Button size="sm" variant="outline" onClick={handleExportPNG} icon={<ImageDown size={14} />} disabled={!chartReady}>
                {i18n.labels.export_png}
              </Button>
            </div>
          </div>
          {pricesLoading ? (
            <Skeleton height={360} />
          ) : pricesData?.rows?.length ? (
            <EChart
              option={priceChartOption}
              style={{ height: '360px', width: '100%' }}
              ariaLabel={`Giá lịch sử ${calcTicker}${priceMode === 'normalized' ? ` và ${selectedBenchmark} chuẩn hóa` : ''}`}
              onChartReady={(chart) => {
                chartInstance.current = chart;
                setChartReady(true);
              }}
            />
          ) : <EmptyState>Chưa có dữ liệu giá cho cổ phiếu đã chọn.</EmptyState>}
        </section>

        <section
          style={{
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
            padding: '20px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: '12px' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600 }}>Lợi suất theo kỳ</h3>
            <Segmented
              ariaLabel="Kỳ lợi suất"
              options={[
                { value: 'monthly', label: 'Tháng' },
                { value: 'quarterly', label: 'Quý' },
              ]}
              value={returnPeriod}
              onChange={setReturnPeriod}
              size="sm"
            />
          </div>
          {investorLoading ? (
            <Skeleton height={320} />
          ) : investorData ? (
            <EChart
              option={returnsChartOption}
              style={{ height: '320px', width: '100%' }}
              ariaLabel={`Lợi suất ${returnPeriod === 'monthly' ? 'theo tháng' : 'theo quý'} của ${calcTicker} và ${selectedBenchmark}`}
            />
          ) : (
            <EmptyState>Chưa có dữ liệu lợi suất để hiển thị.</EmptyState>
          )}
        </section>

        {/* Section 4: ROI Windows & Hypothesis BT1 */}
        {investorData && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
            {/* ROI Windows */}
            <div
              style={{
                backgroundColor: 'var(--surface-1)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--radius-md)',
                padding: '20px',
              }}
            >
              <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px' }}>Cửa sổ lợi suất & Rủi ro</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {(['MSFT', 'GOOGL'] as const).map((t) => {
                  const win = investorData.roi_windows[t];
                  return (
                    <div
                      key={t}
                      style={{
                        padding: '10px 12px',
                        backgroundColor: 'var(--surface-2)',
                        borderRadius: 'var(--radius-sm)',
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
                        gap: '8px',
                      }}
                    >
                      <Badge tone={t === 'MSFT' ? 'msft' : 'googl'}>{t}</Badge>
                      <div style={{ display: 'contents', fontSize: '12px', fontFamily: 'var(--font-mono)' }}>
                        <span>1Y: <strong>{formatPercent(win?.roi_1y)}</strong></span>
                        <span>3Y: <strong>{formatPercent(win?.roi_3y)}</strong></span>
                        <span>5Y: <strong>{formatPercent(win?.roi_5y)}</strong></span>
                        <span>Vol: <strong>{formatRawPercent(win?.annualized_volatility)}</strong></span>
                        <span>MDD: <strong>{formatRawPercent(win?.max_drawdown)}</strong></span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Hypothesis BT1 Card (FR-50) */}
            {bt1 && (
              <div
                style={{
                  backgroundColor: 'var(--surface-1)',
                  border: '1px solid var(--line)',
                  borderRadius: 'var(--radius-md)',
                  padding: '20px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <h3 style={{ fontSize: '14px', fontWeight: 600 }}>Kiểm định BT1: Excess Return</h3>
                  <Badge tone="muted">H0: μ = 0</Badge>
                </div>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '12px' }}>
                  {bt1.conclusion}
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', fontSize: '12px', fontFamily: 'var(--font-mono)' }}>
                  <div style={{ padding: '8px', backgroundColor: 'var(--surface-2)', borderRadius: '4px' }}>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>t-statistic</div>
                    <div style={{ fontWeight: 600 }}>{bt1.statistic.toFixed(2)}</div>
                  </div>
                  <div style={{ padding: '8px', backgroundColor: 'var(--surface-2)', borderRadius: '4px' }}>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>p-value</div>
                    <div style={{ fontWeight: 600 }}>{formatPValue(bt1.p_value)}</div>
                  </div>
                  <div style={{ padding: '8px', backgroundColor: 'var(--surface-2)', borderRadius: '4px' }}>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Số mẫu (n)</div>
                    <div style={{ fontWeight: 600 }}>{bt1.n}</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
};
