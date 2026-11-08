import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  icon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'secondary',
  size = 'md',
  icon,
  className = '',
  style,
  ...props
}) => {
  const baseStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    borderRadius: 'var(--radius-md)',
    fontFamily: 'var(--font-sans)',
    fontWeight: 500,
    cursor: props.disabled ? 'not-allowed' : 'pointer',
    opacity: props.disabled ? 0.45 : 1,
    transition: 'color var(--duration-fast) var(--ease-spring), background-color var(--duration-fast) var(--ease-spring), border-color var(--duration-fast) var(--ease-spring), transform var(--duration-fast) var(--ease-spring)',
    textDecoration: 'none',
    whiteSpace: 'nowrap',
    ...style,
  };

  const sizeStyles: Record<string, React.CSSProperties> = {
    sm: { padding: '4px 10px', fontSize: '12px', minHeight: '28px' },
    md: { padding: '6px 14px', fontSize: '13px', minHeight: '34px' },
    lg: { padding: '8px 18px', fontSize: '14px', minHeight: '40px' },
  };

  const variantStyles: Record<string, React.CSSProperties> = {
    primary: {
      backgroundColor: 'var(--text)',
      color: 'var(--bg)',
      border: '1px solid transparent',
    },
    secondary: {
      backgroundColor: 'var(--surface-2)',
      color: 'var(--text)',
      border: '1px solid var(--line)',
    },
    outline: {
      backgroundColor: 'transparent',
      color: 'var(--text)',
      border: '1px solid var(--line)',
    },
    ghost: {
      backgroundColor: 'transparent',
      color: 'var(--text-muted)',
      border: '1px solid transparent',
    },
  };

  return (
    <button
      style={{ ...baseStyle, ...sizeStyles[size], ...variantStyles[variant] }}
      className={`ui-button ${className}`}
      {...props}
    >
      {icon && <span style={{ display: 'inline-flex' }}>{icon}</span>}
      {children}
    </button>
  );
};
