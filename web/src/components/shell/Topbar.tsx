import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { Menu, Sun, Moon, RefreshCw } from 'lucide-react';
import { IconButton } from '../ui/IconButton';
import { Tooltip } from '../ui/Tooltip';
import { Freshness } from '../../api/types';
import { getBenchmarkFilter, getCompanyFilter } from '../../lib/filters';

export interface TopbarProps {
  pageTitle: string;
  onOpenDrawer: () => void;
  drawerOpen: boolean;
  triggerRef?: React.Ref<HTMLButtonElement>;
  freshness: Freshness | null;
  hasNewData?: boolean;
  onReload?: () => void;
  showCompanyFilter?: boolean;
  showBenchmarkFilter?: boolean;
}

export const Topbar: React.FC<TopbarProps> = ({
  pageTitle,
  onOpenDrawer,
  drawerOpen,
  triggerRef,
  freshness,
  hasNewData = false,
  onReload,
  showCompanyFilter = false,
  showBenchmarkFilter = false,
}) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const currentCompany = getCompanyFilter(searchParams.get('company'));
  const currentBenchmark = getBenchmarkFilter(searchParams.get('bench'));

  const [theme, setTheme] = React.useState<'dark' | 'light'>('dark');

  React.useEffect(() => {
    const current = document.documentElement.getAttribute('data-theme') as 'dark' | 'light';
    if (current) setTheme(current);
  }, []);

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem('aicor-theme', next);
    } catch {
      // localStorage error handled
    }
  };

  const handleCompanyChange = (c: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('company', c);
    setSearchParams(next, { replace: true });
  };

  const handleBenchChange = (b: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('bench', b);
    setSearchParams(next, { replace: true });
  };

  // Age in human readable format
  const ageSeconds = freshness?.age_seconds;
  const ageDescription = ageSeconds === undefined || ageSeconds === null
    ? 'chưa rõ tuổi dữ liệu'
    : ageSeconds < 60
      ? 'vừa cập nhật'
      : ageSeconds < 3600
        ? `cập nhật ${Math.floor(ageSeconds / 60)} phút trước`
        : ageSeconds < 86400
          ? `cập nhật ${Math.max(1, Math.floor(ageSeconds / 3600))} giờ trước`
          : `cập nhật ${Math.floor(ageSeconds / 86400)} ngày trước`;
  const ageLabel = freshness?.stale
    ? `Dữ liệu cũ · ${ageDescription}`
    : freshness?.checksum_ok === false
      ? `Chưa xác minh · ${ageDescription}`
      : ageDescription;
  const isHealthy = freshness?.checksum_ok === true && !freshness.stale;
  const statusColor = !freshness || !freshness.available || freshness.stale
    ? 'var(--neg)'
    : isHealthy
      ? 'var(--pos)'
      : 'var(--neu)';

  return (
    <header
      className="topbar-header"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        height: '56px',
        backgroundColor: 'var(--surface-1)',
        borderBottom: '1px solid var(--line)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        zIndex: 1000,
      }}
    >
      {/* Left: Hamburger & Page Title */}
      <div className="topbar-left" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <IconButton
          ref={triggerRef}
          aria-label="Mở menu điều hướng"
          aria-expanded={drawerOpen}
          aria-controls="navigation-drawer"
          variant="ghost"
          onClick={onOpenDrawer}
        >
          <Menu size={20} />
        </IconButton>

        <div className="topbar-branding" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="topbar-brand" style={{ fontWeight: 700, fontSize: '15px', letterSpacing: '0.04em' }}>AICOR</span>
          <span className="topbar-separator" style={{ color: 'var(--line-strong)' }}>/</span>
          <span className="topbar-page-title" style={{ fontSize: '13px', color: 'var(--text-muted)', fontWeight: 500 }}>
            {pageTitle}
          </span>
        </div>
      </div>

      {/* Center: Global filter chips */}
      {(showCompanyFilter || showBenchmarkFilter) && (
        <div
          className="topbar-filters"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          {showCompanyFilter && (
            <>
              <div
                className="topbar-company-filter"
                role="group"
                aria-label="Bộ lọc doanh nghiệp"
                style={{
                  display: 'flex',
                  backgroundColor: 'var(--surface-2)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--line)',
                  padding: '2px',
                }}
              >
                {(['BOTH', 'MSFT', 'GOOGL'] as const).map((comp) => {
                  const isSelected = currentCompany === comp;
                  const label = comp === 'BOTH' ? 'So sánh' : comp;
                  return (
                    <button
                      key={comp}
                      className="topbar-filter-option"
                      aria-pressed={isSelected}
                      onClick={() => handleCompanyChange(comp)}
                      style={{
                        fontSize: '11px',
                        fontFamily: 'var(--font-sans)',
                        fontWeight: isSelected ? 600 : 400,
                        padding: '2px 8px',
                        borderRadius: '2px',
                        backgroundColor: isSelected ? 'var(--surface-1)' : 'transparent',
                        color: isSelected ? (comp === 'MSFT' ? 'var(--msft)' : comp === 'GOOGL' ? 'var(--googl)' : 'var(--text)') : 'var(--text-muted)',
                        border: isSelected ? '1px solid var(--line)' : '1px solid transparent',
                        cursor: 'pointer',
                        transition: 'color var(--duration-fast) var(--ease-spring), background-color var(--duration-fast) var(--ease-spring), border-color var(--duration-fast) var(--ease-spring)',
                      }}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
              <select
                className="topbar-company-mobile"
                aria-label="Bộ lọc doanh nghiệp"
                value={currentCompany}
                onChange={(event) => handleCompanyChange(event.target.value)}
              >
                <option value="BOTH">So sánh</option>
                <option value="MSFT">MSFT</option>
                <option value="GOOGL">GOOGL</option>
              </select>
            </>
          )}

          {showBenchmarkFilter && (
            <>
              <div
                className="topbar-benchmark-filter"
                role="group"
                aria-label="Bộ lọc Benchmark"
                style={{
                  display: 'flex',
                  backgroundColor: 'var(--surface-2)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--line)',
                  padding: '2px',
                }}
              >
                {(['SPY', 'QQQ'] as const).map((b) => {
                  const isSelected = currentBenchmark === b;
                  return (
                    <button
                      key={b}
                      className="topbar-filter-option"
                      aria-pressed={isSelected}
                      onClick={() => handleBenchChange(b)}
                      style={{
                        fontSize: '11px',
                        fontFamily: 'var(--font-sans)',
                        fontWeight: isSelected ? 600 : 400,
                        padding: '2px 8px',
                        borderRadius: '2px',
                        backgroundColor: isSelected ? 'var(--surface-1)' : 'transparent',
                        color: isSelected ? 'var(--text)' : 'var(--text-muted)',
                        border: isSelected ? '1px solid var(--line)' : '1px solid transparent',
                        cursor: 'pointer',
                        transition: 'color var(--duration-fast) var(--ease-spring), background-color var(--duration-fast) var(--ease-spring), border-color var(--duration-fast) var(--ease-spring)',
                      }}
                    >
                      {b}
                    </button>
                  );
                })}
              </div>
              <select
                className="topbar-benchmark-mobile"
                aria-label="Bộ lọc Benchmark"
                value={currentBenchmark}
                onChange={(event) => handleBenchChange(event.target.value)}
              >
                <option value="SPY">SPY</option>
                <option value="QQQ">QQQ</option>
              </select>
            </>
          )}
        </div>
      )}

      {/* Right: Sync Status & Theme Switch */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {hasNewData && (
          <button
            onClick={onReload}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '3px 8px',
              backgroundColor: 'var(--pos-bg)',
              color: 'var(--pos)',
              border: '1px solid var(--pos)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11px',
              cursor: 'pointer',
            }}
          >
            <RefreshCw size={12} />
            <span>Có dữ liệu mới</span>
          </button>
        )}

        <Tooltip
          content={`Snapshot: ${freshness?.snapshot_version || '—'} · As of: ${freshness?.data_as_of || '—'} · Checksum: ${freshness?.checksum_ok === true ? 'OK' : freshness?.checksum_ok === false ? 'chưa xác nhận' : '—'}`}
        >
          <div
            className="topbar-freshness"
            role="status"
            aria-label={`Trạng thái dữ liệu: ${ageLabel}`}
            tabIndex={0}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              color: 'var(--text-muted)',
              cursor: 'default',
            }}
          >
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                backgroundColor: statusColor,
              }}
            />
            <span className="topbar-age" style={{ display: 'inline-block' }}>{ageLabel}</span>
          </div>
        </Tooltip>

        <IconButton
          aria-label={theme === 'dark' ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối'}
          variant="ghost"
          size="sm"
          onClick={toggleTheme}
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </IconButton>
      </div>
    </header>
  );
};
