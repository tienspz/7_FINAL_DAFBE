import React from 'react';

export type BadgeTone = 'positive' | 'neutral' | 'caution' | 'msft' | 'googl' | 'muted';

export interface BadgeProps {
  children: React.ReactNode;
  tone?: BadgeTone;
  icon?: React.ReactNode;
  style?: React.CSSProperties;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  tone = 'neutral',
  icon,
  style,
  className = '',
}) => {
  const toneMap: Record<BadgeTone, React.CSSProperties> = {
    positive: { backgroundColor: 'var(--pos-bg)', color: 'var(--pos)', border: '1px solid var(--pos)' },
    neutral: { backgroundColor: 'var(--neu-bg)', color: 'var(--neu)', border: '1px solid var(--neu)' },
    caution: { backgroundColor: 'var(--neg-bg)', color: 'var(--neg)', border: '1px solid var(--neg)' },
    msft: { backgroundColor: 'var(--msft-dim)', color: 'var(--msft)', border: '1px solid var(--msft)' },
    googl: { backgroundColor: 'var(--googl-dim)', color: 'var(--googl)', border: '1px solid var(--googl)' },
    muted: { backgroundColor: 'var(--surface-2)', color: 'var(--text-muted)', border: '1px solid var(--line)' },
  };

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: '2px 8px',
        borderRadius: 'var(--radius-sm)',
        fontSize: '11px',
        fontWeight: 500,
        fontFamily: 'var(--font-sans)',
        lineHeight: 1.4,
        ...toneMap[tone],
        ...style,
      }}
      className={`ui-badge ${className}`}
    >
      {icon && <span style={{ display: 'inline-flex', fontSize: '12px' }}>{icon}</span>}
      {children}
    </span>
  );
};

