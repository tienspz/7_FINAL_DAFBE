import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useOverview } from '../../data/hooks';

export const QuarterRuler: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data } = useOverview();
  const quarters = [...new Set(data?.business_comparison.MSFT.map((item) => item.calendar_key) ?? [])];
  const latestQuarter = data?.latest_quarter ?? quarters.at(-1) ?? '';
  const requestedQuarter = searchParams.get('q');
  const selectedQuarter = requestedQuarter && quarters.includes(requestedQuarter)
    ? requestedQuarter
    : latestQuarter;

  const handleSelectQuarter = (q: string) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('q', q);
    setSearchParams(nextParams, { replace: true });
  };

  return (
    <nav
      aria-label="Thước quý thời gian"
      style={{
        width: '100%',
        backgroundColor: 'var(--surface-1)',
        borderBottom: '1px solid var(--line)',
        overflowX: 'auto',
        WebkitOverflowScrolling: 'touch',
        padding: '6px 16px',
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        position: 'sticky',
        top: '56px',
        zIndex: 900,
      }}
      className="no-scrollbar"
    >
      <span
        style={{
          fontSize: '11px',
          fontWeight: 600,
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          marginRight: '8px',
          whiteSpace: 'nowrap',
          fontFamily: 'var(--font-sans)',
        }}
      >
        Thước quý
      </span>

      <div style={{ display: 'flex', gap: '3px', alignItems: 'center' }}>
        {quarters.map((q) => {
          const isSelected = q === selectedQuarter;
          const [, quarter] = q.split('-');
          const isYearStart = quarter === 'Q1';

          return (
            <button
              key={q}
              aria-pressed={isSelected}
              onClick={() => handleSelectQuarter(q)}
              title={`Chọn ${q}`}
              style={{
                display: 'inline-flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '3px 7px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: isSelected ? 'var(--surface-hover)' : 'transparent',
                border: isSelected ? '1px solid var(--focus-ring)' : '1px solid transparent',
                color: isSelected ? 'var(--text)' : isYearStart ? 'var(--text)' : 'var(--text-muted)',
                cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                lineHeight: 1.2,
                transition: 'color var(--duration-fast) var(--ease-spring), background-color var(--duration-fast) var(--ease-spring), border-color var(--duration-fast) var(--ease-spring)',
                whiteSpace: 'nowrap',
                fontWeight: isSelected ? 600 : isYearStart ? 500 : 400,
              }}
            >
              <span>{q}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
