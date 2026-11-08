import React from 'react';

export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  'aria-label': string;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'ghost' | 'secondary' | 'outline';
}

export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  (
    {
      children,
      size = 'md',
      variant = 'ghost',
      style,
      className = '',
      ...props
    },
    ref
  ) => {
    const sizeMap = {
      sm: { width: '28px', height: '28px', fontSize: '14px' },
      md: { width: '36px', height: '36px', fontSize: '16px' },
      lg: { width: '44px', height: '44px', fontSize: '18px' }, // 44px min touch target
    };

    const variantMap: Record<string, React.CSSProperties> = {
      ghost: { backgroundColor: 'transparent', color: 'var(--text-muted)', border: 'none' },
      secondary: { backgroundColor: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--line)' },
      outline: { backgroundColor: 'transparent', color: 'var(--text)', border: '1px solid var(--line)' },
    };

    return (
      <button
        ref={ref}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderRadius: 'var(--radius-md)',
          cursor: props.disabled ? 'not-allowed' : 'pointer',
          transition: 'color var(--duration-fast) var(--ease-spring), background-color var(--duration-fast) var(--ease-spring), border-color var(--duration-fast) var(--ease-spring), transform var(--duration-fast) var(--ease-spring)',
          ...sizeMap[size],
          ...variantMap[variant],
          ...style,
        }}
        className={`ui-icon-button ${className}`}
        {...props}
      >
        {children}
      </button>
    );
  }
);

IconButton.displayName = 'IconButton';
