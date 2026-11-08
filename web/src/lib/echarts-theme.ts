export interface ThemeColors {
  isDark: boolean;
  bg: string;
  surface: string;
  line: string;
  text: string;
  textMuted: string;
  msft: string;
  googl: string;
  spy: string;
  qqq: string;
  pos: string;
  neu: string;
  neg: string;
}

export function getThemeColors(isDark: boolean): ThemeColors {
  if (isDark) {
    return {
      isDark: true,
      bg: '#07090C',
      surface: '#0D1116',
      line: '#1F2933',
      text: '#E8EDF2',
      textMuted: '#8A97A6',
      msft: '#22E5FF',
      googl: '#FFB020',
      spy: '#7C8794',
      qqq: '#A0AEC0',
      pos: '#34F5A0',
      neu: '#FFD166',
      neg: '#FF6B6B',
    };
  }
  return {
    isDark: false,
    bg: '#F6F5F1',
    surface: '#FFFFFF',
    line: '#DAD7CC',
    text: '#0E1116',
    textMuted: '#566070',
    msft: '#007C91',
    googl: '#975800',
    spy: '#6B7480',
    qqq: '#4A5568',
    pos: '#0A8754',
    neu: '#946300',
    neg: '#D32F2F',
  };
}

export function getEChartsBaseOption(isDark: boolean) {
  const c = getThemeColors(isDark);
  return {
    backgroundColor: 'transparent',
    color: [c.msft, c.googl, c.spy, c.qqq],
    textStyle: {
      fontFamily: 'Geist Sans, sans-serif',
      color: c.textMuted,
      fontSize: 12,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '10%',
      top: '12%',
      containLabel: true,
      borderColor: c.line,
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.surface,
      borderColor: c.line,
      borderWidth: 1,
      textStyle: {
        color: c.text,
        fontSize: 12,
        fontFamily: 'Geist Mono, monospace',
      },
      padding: [8, 12],
    },
    legend: {
      textStyle: {
        color: c.textMuted,
        fontSize: 12,
      },
      top: 0,
      right: 0,
    },
    xAxis: {
      axisLine: { lineStyle: { color: c.line } },
      axisTick: { show: false },
      axisLabel: { color: c.textMuted, fontSize: 11 },
      splitLine: { show: false },
    },
    yAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: c.textMuted, fontSize: 11 },
      splitLine: { lineStyle: { color: c.line, type: 'dashed' } },
    },
  };
}
