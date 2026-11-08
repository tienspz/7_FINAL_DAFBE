export type CompanyFilter = 'BOTH' | 'MSFT' | 'GOOGL';
export type BenchmarkFilter = 'SPY' | 'QQQ';

export function getCompanyFilter(value: string | null): CompanyFilter {
  return value === 'MSFT' || value === 'GOOGL' ? value : 'BOTH';
}

export function getBenchmarkFilter(value: string | null): BenchmarkFilter {
  return value === 'QQQ' ? 'QQQ' : 'SPY';
}
