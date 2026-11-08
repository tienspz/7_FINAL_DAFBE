import { describe, expect, it } from 'vitest';
import { getBenchmarkFilter, getCompanyFilter } from './filters';

describe('URL filter normalization', () => {
  it('uses compare mode for missing or unknown company filters', () => {
    expect(getCompanyFilter(null)).toBe('BOTH');
    expect(getCompanyFilter('invalid')).toBe('BOTH');
    expect(getCompanyFilter('GOOGL')).toBe('GOOGL');
  });

  it('uses SPY for missing or unknown benchmark filters', () => {
    expect(getBenchmarkFilter(null)).toBe('SPY');
    expect(getBenchmarkFilter('invalid')).toBe('SPY');
    expect(getBenchmarkFilter('QQQ')).toBe('QQQ');
  });
});
