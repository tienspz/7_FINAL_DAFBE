import React, { useEffect, useRef } from 'react';

export interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  triggerRef?: React.RefObject<HTMLElement | null>;
  children: React.ReactNode;
}

export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  triggerRef,
  children,
}) => {
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    // Focus Trap
    const drawerEl = drawerRef.current;
    if (drawerEl) {
      const focusableElements = drawerEl.querySelectorAll<HTMLElement>(
        'a[href], button, input, textarea, select, [tabindex]:not([tabindex="-1"])'
      );
      const firstEl = focusableElements[0];
      const lastEl = focusableElements[focusableElements.length - 1];

      firstEl?.focus();

      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          onClose();
        } else if (e.key === 'Tab') {
          if (e.shiftKey && document.activeElement === firstEl) {
            e.preventDefault();
            lastEl?.focus();
          } else if (!e.shiftKey && document.activeElement === lastEl) {
            e.preventDefault();
            firstEl?.focus();
          }
        }
      };

      window.addEventListener('keydown', handleKeyDown);
      return () => {
        window.removeEventListener('keydown', handleKeyDown);
        document.body.style.overflow = previousOverflow;
        // Return focus to hamburger
        triggerRef?.current?.focus();
      };
    }
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen, onClose, triggerRef]);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 2000,
        display: 'flex',
      }}
    >
      {/* Scrim */}
      <button
        type="button"
        aria-label="Đóng menu điều hướng"
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          width: '100%',
          height: '100%',
          backgroundColor: 'rgba(0, 0, 0, 0.65)',
          backdropFilter: 'blur(2px)',
          animation: 'fadeIn var(--duration-drawer) var(--ease-spring)',
          cursor: 'default',
        }}
      />

      {/* Drawer content */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Menu điều hướng"
        style={{
          position: 'relative',
          width: '280px',
          maxWidth: '85vw',
          height: '100%',
          overscrollBehavior: 'contain',
          backgroundColor: 'var(--surface-1)',
          borderRight: '1px solid var(--line)',
          display: 'flex',
          flexDirection: 'column',
          zIndex: 2001,
          boxShadow: '4px 0 24px rgba(0, 0, 0, 0.4)',
          animation: 'slideInLeft var(--duration-drawer) var(--ease-spring)',
        }}
      >
        {children}
      </div>
    </div>
  );
};
