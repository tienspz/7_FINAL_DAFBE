/**
 * Investment Calculator engine according to Section 3.1 & Section 11 of FRONTEND_BRIEF.md
 */

export interface PriceRow {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adj_close: number;
  volume: number;
  dividends: number;
  stock_splits: number;
}

export interface CalculatorInputs {
  capital: number; // I0
  fees?: number;   // Fees (default 0)
  dateBuy: string; // YYYY-MM-DD
  dateEval: string;// YYYY-MM-DD
}

export interface CalculatorResult {
  shares: number;
  buyPrice: number;
  actualDateBuy: string;
  buyDateAdjusted: boolean;
  evalPrice: number;
  actualDateEval: string;
  evalDateAdjusted: boolean;
  totalDividends: number;
  finalValue: number; // Vt
  profit: number;     // Vt - I0
  roi: number;        // (Vt - I0) / I0
  annualizedRoi: number;
  daysHeld: number;
  notes: string[];
}

/**
 * Pure calculation with given prices:
 * shares = (capital - fees) / buyPrice
 * finalValue = shares * evalPrice + totalDividends (FR-04)
 * profit = finalValue - capital
 * roi = profit / capital
 * annualized = (1 + roi)^(365/days) - 1
 */
export function calculateInvestmentPure(
  capital: number,
  buyPrice: number,
  evalPrice: number,
  totalDividends: number,
  fees = 0,
  days = 365
): { shares: number; finalValue: number; profit: number; roi: number; annualizedRoi: number } {
  if (![capital, buyPrice, evalPrice, totalDividends, fees, days].every(Number.isFinite)) {
    throw new Error('Giá trị đầu vào phải là số hữu hạn');
  }
  if (capital <= 0) throw new Error('Vốn đầu tư phải lớn hơn 0');
  if (buyPrice <= 0) throw new Error('Giá mua phải lớn hơn 0');
  if (evalPrice < 0) throw new Error('Giá đánh giá không hợp lệ');
  if (fees < 0) throw new Error('Phí giao dịch không được âm');
  if (fees >= capital) throw new Error('Phí giao dịch không thể vượt quá hoặc bằng số vốn');

  const netCapital = capital - fees;
  const shares = netCapital / buyPrice;
  const finalValue = shares * evalPrice + totalDividends;
  const profit = finalValue - capital;
  const roi = profit / capital;
  
  const years = days / 365;
  let annualizedRoi = 0;
  if (years > 0) {
    if (roi <= -1) {
      annualizedRoi = -1;
    } else {
      annualizedRoi = Math.pow(1 + roi, 1 / years) - 1;
    }
  }

  return {
    shares,
    finalValue,
    profit,
    roi,
    annualizedRoi,
  };
}

/**
 * Find the closest matching or next trading day in rows
 */
export function findTradingDay(rows: PriceRow[], targetDate: string): { row: PriceRow; adjusted: boolean } | null {
  if (!rows || rows.length === 0) return null;
  
  // Sorted chronologically
  const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
  
  // Direct match
  const direct = sorted.find((r) => r.date === targetDate);
  if (direct) {
    return { row: direct, adjusted: false };
  }

  // Next available trading day
  const next = sorted.find((r) => r.date > targetDate);
  if (next) {
    return { row: next, adjusted: true };
  }

  return null;
}

/**
 * Calculate investment based on real price rows
 */
export function calculateInvestment(
  rows: PriceRow[],
  inputs: CalculatorInputs
): CalculatorResult {
  const { capital, fees = 0, dateBuy, dateEval } = inputs;
  const notes: string[] = [];

  if (dateEval <= dateBuy) {
    throw new Error('Ngày đánh giá phải sau ngày mua');
  }

  const buyInfo = findTradingDay(rows, dateBuy);
  if (!buyInfo) throw new Error(`Không tìm thấy dữ liệu giá cho ngày mua ${dateBuy}`);
  if (buyInfo.adjusted) {
    notes.push(`Ngày mua ${dateBuy} không phải phiên giao dịch, đã chuyển sang ${buyInfo.row.date}`);
  }

  const evalInfo = findTradingDay(rows, dateEval);
  if (!evalInfo) throw new Error(`Không tìm thấy dữ liệu giá cho ngày đánh giá ${dateEval}`);
  if (evalInfo.adjusted) {
    notes.push(`Ngày đánh giá ${dateEval} không phải phiên giao dịch, đã chuyển sang ${evalInfo.row.date}`);
  }

  const buyPrice = buyInfo.row.close;
  const evalPrice = evalInfo.row.close;

  // Calculate dividends received between buy and eval date (inclusive of eval, exclusive of buy)
  const dividendsPerShare = rows
    .filter((r) => r.date > buyInfo.row.date && r.date <= evalInfo.row.date)
    .reduce((sum, r) => sum + (r.dividends || 0), 0);

  const netCapital = capital - fees;
  const shares = netCapital / buyPrice;
  const totalDividends = shares * dividendsPerShare;

  const startMs = new Date(buyInfo.row.date).getTime();
  const endMs = new Date(evalInfo.row.date).getTime();
  const daysHeld = Math.max(1, Math.round((endMs - startMs) / (1000 * 60 * 60 * 24)));

  const pureResult = calculateInvestmentPure(
    capital,
    buyPrice,
    evalPrice,
    totalDividends,
    fees,
    daysHeld
  );

  return {
    shares: pureResult.shares,
    buyPrice,
    actualDateBuy: buyInfo.row.date,
    buyDateAdjusted: buyInfo.adjusted,
    evalPrice,
    actualDateEval: evalInfo.row.date,
    evalDateAdjusted: evalInfo.adjusted,
    totalDividends,
    finalValue: pureResult.finalValue,
    profit: pureResult.profit,
    roi: pureResult.roi,
    annualizedRoi: pureResult.annualizedRoi,
    daysHeld,
    notes,
  };
}
