import React, { useState, useRef, useEffect, useId } from 'react';

export interface PopoverProps {
  trigger: React.ReactNode;
  children: React.ReactNode;
  title?: string;
}

export const Popover: React.FC<PopoverProps> = ({ trigger, children, title }) => {
  const [open, setOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const popoverId = useId();

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open]);

  return (
    <div style={{ position: 'relative', display: 'inline-block' }} ref={popoverRef}>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={popoverId}
        onClick={() => setOpen((current) => !current)}
        style={{ display: 'inline-flex', alignItems: 'center', color: 'inherit', font: 'inherit', cursor: 'pointer' }}
      >
        {trigger}
      </button>
      {open && (
        <div
          id={popoverId}
          role="dialog"
          style={{
            position: 'absolute',
            top: 'calc(100% + 8px)',
            right: 0,
            zIndex: 1000,
            width: '280px',
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line-strong)',
            borderRadius: 'var(--radius-md)',
            padding: '12px 14px',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.3)',
            animation: 'fadeIn var(--duration-fast) var(--ease-spring)',
            transformOrigin: 'top right',
            overscrollBehavior: 'contain',
          }}
        >
          {title && (
            <div
              style={{
                fontSize: '12px',
                fontWeight: 600,
                color: 'var(--text)',
                marginBottom: '6px',
                paddingBottom: '4px',
                borderBottom: '1px solid var(--line)',
              }}
            >
              {title}
            </div>
          )}
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.5 }}>
            {children}
          </div>
        </div>
      )}
    </div>
  );
};
