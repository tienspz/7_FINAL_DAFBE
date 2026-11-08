/**
 * Vietnamese formatting utilities according to vi-VN standards.
 */

export function formatPercent(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || isNaN(value)) return '—';
  const formatted = (value * 100).toFixed(decimals).replace('.', ',');
  return `${value > 0 ? '+' : ''}${formatted}%`;
}

export function formatRawPercent(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || isNaN(value)) return '—';
  const formatted = value.toFixed(decimals).replace('.', ',');
  return `${value > 0 ? '+' : ''}${formatted}%`;
}

export function formatCurrency(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || isNaN(value)) return '—';
  const parts = value.toFixed(decimals).split('.');
  const integerPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  if (decimals > 0 && parts[1]) {
    return `$${integerPart},${parts[1]}`;
  }
  return `$${integerPart}`;
}

export function formatNumber(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || isNaN(value)) return '—';
  const parts = value.toFixed(decimals).split('.');
  const integerPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  if (parts[1]) {
    return `${integerPart},${parts[1]}`;
  }
  return integerPart;
}

export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '—';
  // Handles YYYY-MM-DD -> DD/MM/YYYY
  const parts = dateString.split('-');
  if (parts.length === 3) {
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }
  return dateString;
}

export function formatQuarter(quarterKey: string | null | undefined): string {
  if (!quarterKey) return '—';
  // 2026-Q3 -> Q3 2026
  const parts = quarterKey.split('-');
  if (parts.length === 2 && parts[1].startsWith('Q')) {
    return `${parts[1]} ${parts[0]}`;
  }
  return quarterKey;
}

export function formatPValue(pVal: string | number | null | undefined): string {
  if (pVal === null || pVal === undefined) return '—';
  if (typeof pVal === 'string') return pVal;
  if (pVal < 0.001) return '< 0,001';
  return pVal.toFixed(3).replace('.', ',');
}

