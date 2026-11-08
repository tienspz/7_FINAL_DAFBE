import React from 'react';

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  icon?: React.ReactNode;
}

export interface SegmentedProps<T extends string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  size?: 'sm' | 'md';
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  size = 'md',
}: SegmentedProps<T>) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="segmented-control"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '2px',
        backgroundColor: 'var(--surface-2)',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--line)',
        gap: '2px',
        maxWidth: '100%',
        overflowX: 'auto',
        overscrollBehaviorX: 'contain',
        scrollbarWidth: 'none',
      }}
    >
      {options.map((opt) => {
        const isSelected = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            aria-pressed={isSelected}
            onClick={() => onChange(opt.value)}
            style={{
              display: 'inline-flex',
              flexShrink: 0,
              alignItems: 'center',
              gap: '4px',
              padding: size === 'sm' ? '3px 8px' : '5px 12px',
              borderRadius: 'var(--radius-sm)',
              fontSize: size === 'sm' ? '11px' : '12px',
              fontFamily: 'var(--font-sans)',
              fontWeight: isSelected ? 600 : 400,
              backgroundColor: isSelected ? 'var(--surface-1)' : 'transparent',
              color: isSelected ? 'var(--text)' : 'var(--text-muted)',
              border: isSelected ? '1px solid var(--line)' : '1px solid transparent',
              transition: 'background-color var(--duration-fast) var(--ease-spring)',
              cursor: 'pointer',
            }}
          >
            {opt.icon && <span style={{ display: 'inline-flex' }}>{opt.icon}</span>}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
