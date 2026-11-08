import { useState, useEffect, useCallback } from 'react';
import { fetchDataset, fetchHealth, FetchResult } from '../api/client';
import { HealthResponse } from '../api/types';

export function useDataset<T>(key: string) {
  const [result, setResult] = useState<FetchResult<T> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchDataset<T>(key);
      setResult(res);
      setError(res.warning ? new Error(res.warning) : null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return {
    data: result?.data ?? null,
    source: result?.source ?? null,
    etag: result?.etag ?? null,
    snapshotVersion: result?.snapshotVersion ?? null,
    loading,
    error,
    reload: loadData,
  };
}

export function useHealth() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let mounted = true;
    fetchHealth().then((h) => {
      if (mounted) {
        setHealth(h);
        if (!h) setError(new Error('Không thể kiểm tra trạng thái backend hoặc manifest dữ liệu.'));
        setLoading(false);
      }
    }).catch((err: unknown) => {
      if (mounted) {
        setError(err instanceof Error ? err : new Error(String(err)));
        setLoading(false);
      }
    });
    return () => {
      mounted = false;
    };
  }, []);

  return { health, loading, error };
}

// Specialized typed hooks
export interface OverviewDataset {
  schema_version: string;
  snapshot_version: string;
  data_as_of: string;
  latest_quarter: string;
  kpis: {
    MSFT: {
      stock_return_1y: number;
      revenue_growth_latest: number;
      operating_margin_latest: number;
      fcf_margin_latest: number;
      latest_quarter: string;
      period_end: string;
      revenue_source_url: string;
    };
    GOOGL: {
      stock_return_1y: number;
      revenue_growth_latest: number;
      operating_margin_latest: number;
      fcf_margin_latest: number;
      latest_quarter: string;
      period_end: string;
      revenue_source_url: string;
    };
  };
  normalized_prices: Record<'GOOGL' | 'MSFT' | 'QQQ' | 'SPY', Array<{ date: string; value: number }>>;
  business_comparison: Record<'GOOGL' | 'MSFT', Array<{
    calendar_key: string;
    revenue_growth_yoy: number | null;
    operating_margin: number | null;
    fcf_margin: number | null;
  }>>;
}

export function useOverview() {
  return useDataset<OverviewDataset>('overview');
}

export interface InvestorDataset {
  roi_windows: Record<'MSFT' | 'GOOGL', {
    roi_1y: number | null;
    roi_3y: number | null;
    roi_5y: number | null;
    annualized_volatility: number | null;
    max_drawdown: number | null;
  }>;
  monthly_returns: Record<'MSFT' | 'GOOGL' | 'SPY' | 'QQQ', Array<{
    trade_date: string;
    return: number;
    adj_close: number;
  }>>;
  quarterly_returns: Record<'MSFT' | 'GOOGL' | 'SPY' | 'QQQ', Array<{
    calendar_key: string;
    trade_date: string;
    return: number;
  }>>;
  quarter_end_prices: Record<string, Record<string, number>>;
  excess_return_tests: Record<string, {
    statistic: number;
    p_value: string;
    p_adjusted: string;
    n: number;
    ci_95: [number, number];
    conclusion: string;
  }>;
  calculator_note: string;
}

export function useInvestor() {
  return useDataset<InvestorDataset>('investor');
}

export function usePrices(ticker: string) {
  return useDataset<{
    rows: import('../lib/finance').PriceRow[];
    source_url?: string;
    evidence_url?: string;
  }>(`prices/${ticker}`);
}

export interface FinancialMetric {
  value: number | null;
  unit: string;
  source_url?: string;
  evidence_url?: string;
  verification?: string;
  quality?: 'high' | 'low' | 'verified';
}

export interface FinancialsDataset {
  quarters: Array<{
    ticker: 'MSFT' | 'GOOGL';
    calendar_key: string;
    fiscal_period: string;
    period_end: string;
    metrics: Record<string, FinancialMetric>;
    derived_metrics: Record<string, number | null>;
  }>;
  segments: Array<{
    ticker: 'MSFT' | 'GOOGL';
    calendar_key: string;
    segment_name: string;
    value_musd: number;
    operating_income?: number;
    comparable: boolean;
    quality_flag?: string;
  }>;
}

export function useFinancials() {
  return useDataset<FinancialsDataset>('financials');
}

export interface AIAnalysisDataset {
  correlations: Array<{
    ticker: 'MSFT' | 'GOOGL';
    x: string;
    y: string;
    lag: number;
    method: string;
    statistic: number;
    p_value: string;
    p_adjusted: string;
    n: number;
    decision: string;
    note?: string;
  }>;
  indicators: Record<'MSFT' | 'GOOGL', Array<{
    calendar_key: string;
    rd_growth_yoy?: number | null;
    capex_growth_yoy?: number | null;
    revenue_growth_yoy?: number | null;
    fcf_growth_yoy?: number | null;
    operating_margin?: number | null;
    stock_return_quarter?: number | null;
  }>>;
  events: Array<{
    title: string;
    category: string;
    label: 'Reported' | 'Proxy' | 'Estimated';
    published_date: string;
    source_url: string;
    evidence_quote: string;
  }>;
  label_definitions: Record<string, string>;
  event_empty_state: string;
  warnings: string[];
}

export function useAIAnalysis() {
  return useDataset<AIAnalysisDataset>('ai_analysis');
}

export interface DecisionDataset {
  comparison: Array<{
    ticker: 'MSFT' | 'GOOGL';
    stock_return_quarter: number | null;
    revenue_growth_yoy: number | null;
    operating_margin: number | null;
    fcf_growth_yoy: number | null;
    rd_intensity: number | null;
    capex_intensity: number | null;
    eps_trailing_4q: number | null;
    pe_trailing: number | null;
    annualized_volatility: number | null;
    max_drawdown: number | null;
    status: string;
  }>;
  disclaimer: string;
}

export function useDecision() {
  return useDataset<DecisionDataset>('decision');
}

export interface MethodologyDataset {
  formulas: Record<string, { formula: string; description: string }>;
  sources: Array<{ id: string; name: string; kind: string; url: string; status: string; last_checked?: string }>;
  negative_sources: Array<{ id: string; name: string; url: string; status: string; reason: string }>;
  quality_report_summary: {
    total_metrics: number;
    verified_ratio: number;
    low_metric_cells: number;
    excluded_quarters: number;
  };
  link_report_summary: {
    total_links: number;
    valid_links: number;
    broken_links: number;
  };
}

export function useMethodology() {
  return useDataset<MethodologyDataset>('methodology');
}

export interface TestsDataset {
  results: Array<{
    bt_code: string;
    test_name: string;
    statistic?: number;
    p_value: string;
    p_adjusted: string | null;
    p_value_display?: string;
    n: number;
    ci_low?: number;
    ci_high?: number;
    decision: string;
    note?: string;
    quality_mode?: 'exclude_low' | 'label_low';
    excluded_quarters?: Array<{
      ticker: string;
      calendar_key: string;
      reason: string;
    }>;
  }>;
  alpha: number;
  quality_mode_comparison: Array<{
    quality_mode: 'exclude_low';
    bt_code: string;
    test_name: string;
    statistic?: number;
    n: number;
    p_value: string;
    p_adjusted: string | null;
    p_value_display?: string;
    ci_low?: number;
    ci_high?: number;
    note?: string;
    decision: string;
    excluded_quarters: Array<{
      ticker: string;
      calendar_key: string;
      reason: string;
    }>;
    low_quality_quarters: Array<{
      ticker: string;
      calendar_key: string;
      reason: string;
    }>;
  }>;
  warnings: string[];
}

export function useTests() {
  return useDataset<TestsDataset>('tests');
}
