import React, { useEffect, useRef, useState } from 'react';
import type { EChartsOption } from 'echarts';
import type { ECharts } from 'echarts/core';

export interface EChartProps {
  option: EChartsOption;
  style?: React.CSSProperties;
  className?: string;
  ariaLabel?: string;
  onChartReady?: (chart: ECharts) => void;
  groupId?: string;
}

export const EChart: React.FC<EChartProps> = ({
  option,
  style = { height: '360px', width: '100%' },
  className = '',
  ariaLabel = 'Biểu đồ dữ liệu',
  onChartReady,
  groupId,
}) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<ECharts | null>(null);
  const [chartReady, setChartReady] = useState(false);
  const [chartError, setChartError] = useState<string | null>(null);
  const [reducedMotion, setReducedMotion] = useState(() =>
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updatePreference = () => setReducedMotion(preference.matches);
    preference.addEventListener('change', updatePreference);
    return () => preference.removeEventListener('change', updatePreference);
  }, []);

  useEffect(() => {
    const element = chartRef.current;
    if (!element) return;

    let active = true;
    let observer: IntersectionObserver | null = null;
    let resizeObserver: ResizeObserver | null = null;
    const handleResize = () => chartInstance.current?.resize();

    const initialize = async () => {
      try {
        const [echarts, charts, components, renderers] = await Promise.all([
          import('echarts/core'),
          import('echarts/charts'),
          import('echarts/components'),
          import('echarts/renderers'),
        ]);
        if (!active || !chartRef.current) return;

        echarts.use([
          charts.BarChart,
          charts.LineChart,
          components.AxisPointerComponent,
          components.DataZoomComponent,
          components.GridComponent,
          components.LegendComponent,
          components.MarkLineComponent,
          components.TooltipComponent,
          renderers.CanvasRenderer,
        ]);
        const chart = echarts.init(chartRef.current);
        chartInstance.current = chart;
        if (groupId) chart.group = groupId;
        setChartReady(true);

        if (typeof ResizeObserver !== 'undefined') {
          resizeObserver = new ResizeObserver(handleResize);
          resizeObserver.observe(chartRef.current);
        } else {
          window.addEventListener('resize', handleResize);
        }
      } catch (error) {
        if (active) {
          setChartError(error instanceof Error ? error.message : String(error));
        }
      }
    };

    if (typeof IntersectionObserver === 'undefined') {
      void initialize();
    } else {
      observer = new IntersectionObserver(
        (entries) => {
          if (entries.some((entry) => entry.isIntersecting)) {
            observer?.disconnect();
            void initialize();
          }
        },
        { rootMargin: '160px' }
      );
      observer.observe(element);
    }

    return () => {
      active = false;
      observer?.disconnect();
      resizeObserver?.disconnect();
      window.removeEventListener('resize', handleResize);
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, [groupId]);

  useEffect(() => {
    if (!chartInstance.current) return;
    chartInstance.current.setOption({
      ...option,
      animation: !reducedMotion,
      animationDuration: reducedMotion ? 0 : 650,
      animationEasing: 'cubicOut',
    }, true);
  }, [option, reducedMotion, chartReady]);

  useEffect(() => {
    if (chartInstance.current && chartReady) onChartReady?.(chartInstance.current);
  }, [chartReady, onChartReady]);

  return (
    <div
      ref={chartRef}
      style={{ position: 'relative', ...style }}
      className={`echarts-container ${className}`}
      data-reduced-motion={reducedMotion}
      data-chart-loaded={chartReady}
      role="img"
      aria-label={chartError ? `${ariaLabel}. Lỗi: ${chartError}` : ariaLabel}
      aria-busy={!chartReady && !chartError}
    >
      {chartError && (
        <span role="alert" style={{ display: 'block', padding: '16px', color: 'var(--neg)', fontSize: '12px' }}>
          Không thể tải biểu đồ: {chartError}
        </span>
      )}
    </div>
  );
};
