import { describe, it, expect } from 'vitest';
import { calculateInvestmentPure, calculateInvestment, findTradingDay, PriceRow } from './finance';

describe('Finance Calculator Engine (F1)', () => {
  it('passes the mandatory benchmark unit test from SPEC & BRIEF: 1000, 100, 130, 20 => 10 shares, 1320, profit 320, ROI 32%', () => {
    const result = calculateInvestmentPure(1000, 100, 130, 20, 0, 365);
    expect(result.shares).toBe(10);
    expect(result.finalValue).toBe(1320);
    expect(result.profit).toBe(320);
    expect(result.roi).toBeCloseTo(0.32, 4);
    expect(result.annualizedRoi).toBeCloseTo(0.32, 4);
  });

  it('correctly handles fees deduction before buying shares', () => {
    // 1000 capital - 100 fees = 900 net capital / 100 price = 9 shares
    // 9 * 130 + 180 dividends = 1170 + 180 = 1350
    const result = calculateInvestmentPure(1000, 100, 130, 180, 100, 365);
    expect(result.shares).toBe(9);
    expect(result.finalValue).toBe(1350);
    expect(result.profit).toBe(350);
    expect(result.roi).toBeCloseTo(0.35, 4);
  });

  it('throws descriptive error on invalid inputs', () => {
    expect(() => calculateInvestmentPure(-500, 100, 130, 0)).toThrow('Vốn đầu tư phải lớn hơn 0');
    expect(() => calculateInvestmentPure(1000, 0, 130, 0)).toThrow('Giá mua phải lớn hơn 0');
    expect(() => calculateInvestmentPure(1000, 100, 130, 0, 1200)).toThrow('Phí giao dịch không thể vượt quá hoặc bằng số vốn');
    expect(() => calculateInvestmentPure(1000, 100, 130, 0, -1)).toThrow('Phí giao dịch không được âm');
  });

  it('finds the next available trading day when selected day is a weekend/holiday', () => {
    const mockRows: PriceRow[] = [
      { date: '2023-01-03', open: 100, high: 105, low: 99, close: 102, adj_close: 102, volume: 1000, dividends: 0, stock_splits: 0 },
      { date: '2023-01-04', open: 102, high: 106, low: 101, close: 105, adj_close: 105, volume: 1100, dividends: 0, stock_splits: 0 },
      { date: '2023-01-06', open: 105, high: 108, low: 104, close: 107, adj_close: 107, volume: 1200, dividends: 0, stock_splits: 0 },
      { date: '2023-01-09', open: 107, high: 110, low: 106, close: 109, adj_close: 109, volume: 1300, dividends: 0, stock_splits: 0 },
    ];

    // Saturday 2023-01-07 -> should adjust to Monday 2023-01-09
    const match = findTradingDay(mockRows, '2023-01-07');
    expect(match).not.toBeNull();
    expect(match?.adjusted).toBe(true);
    expect(match?.row.date).toBe('2023-01-09');

    // Direct trading day match
    const directMatch = findTradingDay(mockRows, '2023-01-04');
    expect(directMatch?.adjusted).toBe(false);
    expect(directMatch?.row.date).toBe('2023-01-04');
    expect(findTradingDay(mockRows, '2023-01-10')).toBeNull();
  });

  it('calculates investment across real price rows including dividends and notes', () => {
    const mockRows: PriceRow[] = [
      { date: '2023-01-03', open: 100, high: 105, low: 99, close: 100, adj_close: 100, volume: 1000, dividends: 0, stock_splits: 0 },
      { date: '2023-03-15', open: 110, high: 112, low: 109, close: 110, adj_close: 110, volume: 1100, dividends: 2.5, stock_splits: 0 },
      { date: '2024-01-03', open: 120, high: 125, low: 119, close: 120, adj_close: 120, volume: 1200, dividends: 0, stock_splits: 0 },
    ];

    const result = calculateInvestment(mockRows, {
      capital: 10000,
      dateBuy: '2023-01-03',
      dateEval: '2024-01-03',
      fees: 0,
    });

    expect(result.shares).toBe(100); // 10000 / 100
    expect(result.totalDividends).toBe(250); // 100 * 2.5
    expect(result.finalValue).toBe(12250); // 100 * 120 + 250
    expect(result.profit).toBe(2250);
    expect(result.roi).toBeCloseTo(0.225, 3);
  });
});
