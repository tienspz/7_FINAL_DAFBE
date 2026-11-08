import React from 'react';

export const EmptyState: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    role="status"
    style={{
      padding: '24px 12px',
      color: 'var(--text-muted)',
      fontSize: '12px',
      textAlign: 'center',
    }}
  >
    {children}
  </div>
);
