import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Topbar } from './Topbar';
import { QuarterRuler } from './QuarterRuler';
import { NavigationDrawer } from './NavigationDrawer';
import { Popover } from '../ui/Popover';
import { Info, AlertCircle } from 'lucide-react';
import { useSnapshotStream } from '../../api/sse';
import { prepareSnapshotRevalidation } from '../../api/client';
import { selectLatestFreshness } from '../../api/freshness';
import { useHealth } from '../../data/hooks';
import { reloadMountedData } from '../../data/reload';
import { i18n } from '../../i18n/vi';

export interface LayoutProps {
  pageTitle: string;
  children: React.ReactNode;
  dataErrors?: Array<Error | null | undefined>;
  showCompanyFilter?: boolean;
  showBenchmarkFilter?: boolean;
  showQuarterRuler?: boolean;
}

export const Layout: React.FC<LayoutProps> = ({
  pageTitle,
  children,
  dataErrors = [],
  showCompanyFilter = false,
  showBenchmarkFilter = false,
  showQuarterRuler = false,
}) => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [isReloading, setIsReloading] = useState(false);
  const [reloadFeedback, setReloadFeedback] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);
  const hamburgerRef = useRef<HTMLButtonElement>(null);

  const { health } = useHealth();
  const { freshness: sseFreshness, hasNewData, resetNewDataNotice } = useSnapshotStream();
  const currentFreshness = selectLatestFreshness(sseFreshness, health?.snapshot);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  const handleReload = useCallback(async () => {
    if (isReloading) return;
    setIsReloading(true);
    setReloadFeedback(null);
    try {
      await prepareSnapshotRevalidation();
      const result = await reloadMountedData(true);
      if (result.errors.length > 0) {
        const detail = result.errors.map((error) => error.message).join(' · ');
        setReloadFeedback({
          type: 'error',
          message: `Không thể cập nhật đầy đủ dữ liệu: ${detail}`,
        });
        return;
      }

      resetNewDataNotice();
      setReloadFeedback({
        type: 'success',
        message: 'Đã tải lại snapshot đang phát hành.',
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setReloadFeedback({ type: 'error', message: `Không thể cập nhật dữ liệu: ${detail}` });
    } finally {
      setIsReloading(false);
    }
  }, [isReloading, resetNewDataNotice]);

  useEffect(() => {
    if (!reloadFeedback || reloadFeedback.type !== 'success') return;
    const timeout = window.setTimeout(() => setReloadFeedback(null), 4000);
    return () => window.clearTimeout(timeout);
  }, [reloadFeedback]);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg)' }}>
      {/* Topbar */}
      <Topbar
        pageTitle={pageTitle}
        onOpenDrawer={() => setDrawerOpen(true)}
        triggerRef={hamburgerRef}
        drawerOpen={drawerOpen}
        freshness={currentFreshness}
        hasNewData={hasNewData}
        onReload={handleReload}
        isReloading={isReloading}
        reloadFeedback={reloadFeedback}
        showCompanyFilter={showCompanyFilter}
        showBenchmarkFilter={showBenchmarkFilter}
      />

      {showQuarterRuler && <QuarterRuler />}

      {/* Statutory Disclaimer Chip (UI-07, FR-30, FR-35) */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          padding: '6px 16px',
          backgroundColor: 'var(--surface-2)',
          borderBottom: '1px solid var(--line)',
        }}
      >
        <Popover
          title="Tuyên bố miễn trừ trách nhiệm pháp lý"
          trigger={
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '11px',
                color: 'var(--text-muted)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              <Info size={13} style={{ color: 'var(--text-dim)' }} />
              <span>{i18n.disclaimer.statutory}</span>
              <span style={{ textDecoration: 'underline', color: 'var(--text-muted)' }}>[Chi tiết]</span>
            </span>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <p>{i18n.disclaimer.full}</p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--neu)', fontSize: '11px' }}>
              <AlertCircle size={14} />
              <span>Số liệu chưa tính thuế và phí giao dịch chi tiết của từng sàn.</span>
            </div>
          </div>
        </Popover>
      </div>

      {/* Main Page Content */}
      <a className="skip-link" href="#main-content">Bỏ qua điều hướng</a>
      {dataErrors.filter((error): error is Error => error instanceof Error).length > 0 && (
        <div
          role="alert"
          aria-live="polite"
          style={{
            maxWidth: '1280px',
            width: '100%',
            margin: '8px auto 0',
            padding: '0 16px',
            color: 'var(--neg)',
            fontSize: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
            <span>Dữ liệu chưa tải đầy đủ. Kiểm tra kết nối rồi thử lại.</span>
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{ color: 'var(--text)', fontSize: '12px', textDecoration: 'underline' }}
            >
              Thử tải lại
            </button>
          </div>
          <details style={{ marginTop: '6px', color: 'var(--text-muted)' }}>
            <summary style={{ cursor: 'pointer' }}>Chi tiết lỗi</summary>
            <div style={{ marginTop: '4px' }}>
              {dataErrors.filter((error): error is Error => error instanceof Error).map((error) => error.message).join(' · ')}
            </div>
          </details>
        </div>
      )}
      <main
        id="main-content"
        className="page-enter"
        style={{
          flex: 1,
          maxWidth: '1280px',
          width: '100%',
          margin: '0 auto',
          padding: '24px 16px',
        }}
      >
        <h1 className="visually-hidden">{pageTitle}</h1>
        {children}
      </main>

      {/* Navigation Drawer */}
      <NavigationDrawer
        isOpen={drawerOpen}
        onClose={closeDrawer}
        triggerRef={hamburgerRef}
        snapshotVersion={currentFreshness?.snapshot_version}
      />
    </div>
  );
};
