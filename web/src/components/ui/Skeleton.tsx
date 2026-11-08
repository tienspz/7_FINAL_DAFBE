import React from 'react';

export interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  style?: React.CSSProperties;
  className?: string;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  width = '100%',
  height = '16px',
  borderRadius = 'var(--radius-sm)',
  style,
  className = '',
}) => {
  return (
    <div
      style={{
        width,
        height,
        borderRadius,
        backgroundColor: 'var(--surface-2)',
        backgroundImage: 'linear-gradient(90deg, var(--surface-2) 0%, var(--surface-hover) 50%, var(--surface-2) 100%)',
        backgroundSize: '200% 100%',
        animation: 'skeletonShimmer 1.6s infinite ease-in-out',
        ...style,
      }}
      className={`ui-skeleton ${className}`}
    />
  );
};

