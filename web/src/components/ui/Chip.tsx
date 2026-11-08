import React from 'react';

export interface ChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
  icon?: React.ReactNode;
}

export const Chip: React.FC<ChipProps> = ({
  children,
  active = false,
  icon,
  style,
  className = '',
  ...props
}) => {
  return (
    <button
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '3px 10px',
        borderRadius: '12px',
        fontSize: '12px',
        fontFamily: 'var(--font-sans)',
        fontWeight: active ? 600 : 400,
        backgroundColor: active ? 'var(--surface-hover)' : 'var(--surface-1)',
        color: active ? 'var(--text)' : 'var(--text-muted)',
        border: `1px solid ${active ? 'var(--line-strong)' : 'var(--line)'}`,
        transition: 'color var(--duration-fast) var(--ease-spring), background-color var(--duration-fast) var(--ease-spring), border-color var(--duration-fast) var(--ease-spring), transform var(--duration-fast) var(--ease-spring)',
        cursor: 'pointer',
        whiteSpace: 'nowrap',
        ...style,
      }}
      className={`ui-chip ${className}`}
      {...props}
    >
      {icon && <span style={{ display: 'inline-flex' }}>{icon}</span>}
      {children}
    </button>
  );
};
