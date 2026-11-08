import React from 'react';
import { NavLink, useSearchParams } from 'react-router-dom';
import {
  LayoutDashboard,
  TrendingUp,
  Landmark,
  Cpu,
  Scale,
  BookOpenCheck,
  X,
} from 'lucide-react';
import { Drawer } from '../ui/Drawer';
import { IconButton } from '../ui/IconButton';

export interface NavigationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  triggerRef: React.RefObject<HTMLButtonElement | null>;
  snapshotVersion?: string | null;
}

const NAV_ITEMS = [
  { path: '/', label: '1. Tổng quan', icon: LayoutDashboard },
  { path: '/investor', label: '2. Lợi suất cổ đông', icon: TrendingUp },
  { path: '/financials', label: '3. Tài chính', icon: Landmark },
  { path: '/ai', label: '4. Đầu tư AI', icon: Cpu },
  { path: '/decision', label: '5. Quyết định', icon: Scale },
  { path: '/methodology', label: '6. Phương pháp & nguồn', icon: BookOpenCheck },
];

export const NavigationDrawer: React.FC<NavigationDrawerProps> = ({
  isOpen,
  onClose,
  triggerRef,
  snapshotVersion = null,
}) => {
  const [searchParams] = useSearchParams();

  return (
    <Drawer isOpen={isOpen} onClose={onClose} triggerRef={triggerRef}>
      <div
        id="navigation-drawer"
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          backgroundColor: 'var(--surface-1)',
          padding: '16px',
        }}
      >
        {/* Drawer Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingBottom: '16px',
            borderBottom: '1px solid var(--line)',
            marginBottom: '16px',
          }}
        >
          <div>
            <div style={{ fontWeight: 700, fontSize: '15px' }}>AICOR</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>MSFT vs GOOGL</div>
          </div>
          <IconButton aria-label="Đóng menu" variant="ghost" size="sm" onClick={onClose}>
            <X size={18} />
          </IconButton>
        </div>

        {/* Navigation list */}
        <nav
          aria-label="Danh mục chính"
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
            flex: 1,
          }}
        >
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const nextParams = new URLSearchParams();
            if (['/', '/financials', '/ai'].includes(item.path) && searchParams.has('company')) {
              nextParams.set('company', searchParams.get('company')!);
            }
            if (['/', '/investor'].includes(item.path) && searchParams.has('bench')) {
              nextParams.set('bench', searchParams.get('bench')!);
            }
            if (item.path === '/financials' && searchParams.has('q')) {
              nextParams.set('q', searchParams.get('q')!);
            }
            if (item.path === '/ai' && searchParams.has('lag')) {
              nextParams.set('lag', searchParams.get('lag')!);
            }
            const searchString = nextParams.toString() ? `?${nextParams.toString()}` : '';
            const fullPath = `${item.path}${searchString}`;

            return (
              <NavLink
                key={item.path}
                to={fullPath}
                onClick={onClose}
                end={item.path === '/'}
                style={({ isActive }) => ({
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '10px 12px',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '13px',
                  fontFamily: 'var(--font-sans)',
                  fontWeight: isActive ? 600 : 400,
                  backgroundColor: isActive ? 'var(--surface-2)' : 'transparent',
                  color: isActive ? 'var(--text)' : 'var(--text-muted)',
                  border: isActive ? '1px solid var(--line-strong)' : '1px solid transparent',
                  transition: 'color var(--duration-fast) var(--ease-spring), background-color var(--duration-fast) var(--ease-spring), border-color var(--duration-fast) var(--ease-spring)',
                  textDecoration: 'none',
                })}
              >
                <Icon size={17} style={{ flexShrink: 0 }} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* Drawer Footer */}
        <div
          style={{
            borderTop: '1px solid var(--line)',
            paddingTop: '12px',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          <div
            style={{
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              color: 'var(--text-dim)',
            }}
          >
            Snapshot: {snapshotVersion}
          </div>
          <div
            style={{
              fontSize: '10px',
              color: 'var(--text-dim)',
            }}
          >
            {snapshotVersion ? 'Dữ liệu có phiên bản' : 'Chưa có phiên bản dữ liệu'}
          </div>
        </div>
      </div>
    </Drawer>
  );
};
