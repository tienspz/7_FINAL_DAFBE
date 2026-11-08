import React, { useState } from 'react';
import { Layout } from '../../components/shell/Layout';
import { useMethodology, useTests, useHealth } from '../../data/hooks';
import { formatPValue } from '../../lib/format';
import { Skeleton } from '../../components/ui/Skeleton';
import { Badge } from '../../components/ui/Badge';
import { Segmented } from '../../components/ui/Segmented';
import { EmptyState } from '../../components/ui/EmptyState';
import { ExternalLink, CheckCircle, ShieldCheck, Database, FileText } from 'lucide-react';
import { i18n } from '../../i18n/vi';

export const MethodologyPage: React.FC = () => {
  const { data: methodData, loading: methodLoading, error: methodError } = useMethodology();
  const { data: testsData, loading: testsLoading, error: testsError } = useTests();
  const { health, error: healthError } = useHealth();

  const [qualityMode, setQualityMode] = useState<'exclude_low' | 'label_low'>('exclude_low');

  const snapshot = health?.snapshot;
  const testRows = testsData
    ? [
        ...testsData.results.filter((result) => result.bt_code === 'BT1'),
        ...(qualityMode === 'exclude_low'
          ? testsData.quality_mode_comparison
          : testsData.results.filter((result) => result.quality_mode === 'label_low')),
      ]
    : [];
  const getSourceTone = (status: string) => {
    if (status.startsWith('qualified') || status.startsWith('reachable')) return 'positive' as const;
    if (status.includes('retired') || status.includes('rejected') || status.includes('broken')) return 'caution' as const;
    return 'muted' as const;
  };

  return (
    <Layout pageTitle={i18n.nav.methodology} dataErrors={[methodError, testsError, healthError]}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
        
        {/* Table of contents / Anchor links */}
        <nav
          aria-label="Mục lục phương pháp"
          style={{
            display: 'flex',
            gap: '8px',
            flexWrap: 'wrap',
            padding: '12px 16px',
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <a href="#system-status" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>1. Trạng thái hệ thống</a>
          <span style={{ color: 'var(--line)' }}>•</span>
          <a href="#quality-summary" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>2. Báo cáo chất lượng</a>
          <span style={{ color: 'var(--line)' }}>•</span>
          <a href="#hypothesis-tests" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>3. Kiểm định BT1–BT5</a>
          <span style={{ color: 'var(--line)' }}>•</span>
          <a href="#formulas" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>4. Công thức tính toán</a>
          <span style={{ color: 'var(--line)' }}>•</span>
          <a href="#sources" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>5. Nguồn dữ liệu (21 nguồn)</a>
        </nav>

        {/* Section 1: System Status (Read-only) */}
        <section
          id="system-status"
          style={{
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
            padding: '24px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <Database size={16} style={{ color: 'var(--pos)' }} />
            <h2 style={{ fontSize: '15px', fontWeight: 600 }}>1. Trạng thái hệ thống & Snapshot</h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
            <div style={{ padding: '12px', backgroundColor: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Phiên bản Snapshot</div>
              <div style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                {snapshot?.snapshot_version || '—'}
              </div>
            </div>

            <div style={{ padding: '12px', backgroundColor: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Dữ liệu tính đến ngày</div>
              <div style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                {snapshot?.data_as_of || '—'}
              </div>
            </div>

            <div style={{ padding: '12px', backgroundColor: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Toàn vẹn Checksum SHA-256</div>
              <div style={{ fontSize: '14px', fontWeight: 600, color: snapshot?.checksum_ok ? 'var(--pos)' : 'var(--neu)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                {snapshot?.checksum_ok ? <CheckCircle size={14} /> : <ShieldCheck size={14} />}
                <span>{snapshot?.checksum_ok ? 'Checksum hợp lệ' : 'Chưa xác nhận checksum'}</span>
              </div>
            </div>

            <div style={{ padding: '12px', backgroundColor: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Số tệp dataset</div>
              <div style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                {snapshot?.file_count ?? '—'} {snapshot ? 'tệp JSON' : ''}
              </div>
            </div>
          </div>
        </section>

        {/* Section 2: Quality Summary (FR-63) */}
        <section
          id="quality-summary"
          style={{
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
            padding: '24px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <ShieldCheck size={16} style={{ color: 'var(--msft)' }} />
            <h2 style={{ fontSize: '15px', fontWeight: 600 }}>2. Báo cáo chất lượng & Đối chiếu độc lập (Reconcile)</h2>
          </div>

          {methodLoading ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
              {[1, 2, 3, 4].map((i) => <Skeleton key={i} height={80} />)}
            </div>
          ) : !methodData?.quality_report_summary ? (
            <EmptyState>Chưa có báo cáo chất lượng dữ liệu.</EmptyState>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
              <div style={{ padding: '12px', backgroundColor: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Tỷ lệ Verified</div>
                <div style={{ fontSize: '20px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--pos)' }}>
                  {(methodData.quality_report_summary.verified_ratio * 100).toFixed(1)}%
                </div>
              </div>

              <div style={{ padding: '12px', backgroundColor: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Chỉ số có cảnh báo Low-quality</div>
                <div style={{ fontSize: '20px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                  {methodData.quality_report_summary.low_metric_cells}
                </div>
              </div>

              <div style={{ padding: '12px', backgroundColor: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Quý loại trừ do thiếu dữ liệu</div>
                <div style={{ fontSize: '20px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                  {methodData.quality_report_summary.excluded_quarters}
                </div>
              </div>

              <div style={{ padding: '12px', backgroundColor: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Liên kết hợp lệ (Link Report)</div>
                <div style={{ fontSize: '20px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--pos)' }}>
                  {methodData.link_report_summary?.valid_links ?? '—'} / {methodData.link_report_summary?.total_links ?? '—'}
                </div>
              </div>
            </div>
          )}
        </section>

        {/* Section 3: Hypothesis Tests BT1–BT5 (FR-50..52) */}
        <section
          id="hypothesis-tests"
          style={{
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
            padding: '24px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
            <div>
              <h2 style={{ fontSize: '15px', fontWeight: 600 }}>3. Kết quả kiểm định giả thuyết kinh tế lượng (BT1–BT5)</h2>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Mức ý nghĩa α = {testsData?.alpha ?? '—'} · Hiệu chỉnh Holm cho kiểm định đa biến
              </p>
            </div>

            {/* Quality mode toggle (FR-52) */}
            <Segmented
              ariaLabel="Chế độ xử lý số liệu sơ bộ"
              options={[
                { value: 'exclude_low', label: 'Loại trừ số liệu sơ bộ' },
                { value: 'label_low', label: 'Giữ lại kèm nhãn cảnh báo' },
              ]}
              value={qualityMode}
              onChange={setQualityMode}
              size="sm"
            />
          </div>

          {testsLoading ? (
            <Skeleton height={200} />
          ) : !testsData ? (
            <EmptyState>Chưa có kết quả kiểm định để hiển thị.</EmptyState>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--line-strong)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '8px' }}>Mã</th>
                    <th style={{ padding: '8px' }}>Tên giả thuyết</th>
                    <th style={{ padding: '8px', textAlign: 'right' }}>Thống kê (t / r)</th>
                    <th style={{ padding: '8px', textAlign: 'right' }}>p thô</th>
                    <th style={{ padding: '8px', textAlign: 'right' }}>p hiệu chỉnh</th>
                    <th style={{ padding: '8px', textAlign: 'center' }}>Số mẫu (n)</th>
                    <th style={{ padding: '8px', textAlign: 'right' }}>CI 95%</th>
                    <th style={{ padding: '8px' }}>Kết luận học thuật</th>
                  </tr>
                </thead>
                <tbody>
                  {testRows.length === 0 ? (
                    <tr><td colSpan={8}><EmptyState>Không có kết quả cho chế độ chất lượng đã chọn.</EmptyState></td></tr>
                  ) : testRows.map((t, idx) => {
                    const isLowN = t.n < 30; // FR-53
                    const btCode = t.bt_code;
                    const testName = t.test_name;
                    const decisionText =
                      t.decision === 'reject_h0'
                        ? 'Bác bỏ H0'
                        : t.decision === 'fail_to_reject_h0'
                        ? 'Không bác bỏ H0'
                        : t.decision || 'Tham khảo';
                    const isReject = t.decision === 'reject_h0';
                    const stat = typeof t.statistic === 'number' ? t.statistic.toFixed(2) : '—';
                    const pVal = t.p_value_display || t.p_value;
                    const pAdj = t.p_adjusted;

                    return (
                      <tr key={`${btCode}-${testName}-${idx}`} style={{ borderBottom: '1px solid var(--line)' }}>
                        <td style={{ padding: '8px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{btCode}</td>
                        <td style={{ padding: '8px' }}>
                          <div style={{ fontWeight: 500 }}>{testName}</div>
                          {t.note && <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>{t.note}</div>}
                          {t.excluded_quarters && t.excluded_quarters.length > 0 && (
                            <details style={{ marginTop: '4px', color: 'var(--text-muted)' }}>
                              <summary>{t.excluded_quarters.length} quý bị loại</summary>
                              {t.excluded_quarters.map((quarter, quarterIndex) => (
                                <div key={`${quarter.ticker}-${quarter.calendar_key}-${quarterIndex}`}>
                                  {quarter.ticker} · {quarter.calendar_key}: {quarter.reason}
                                </div>
                              ))}
                            </details>
                          )}
                        </td>
                        <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                          {stat}
                        </td>
                        <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                          {formatPValue(pVal)}
                        </td>
                        <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                          {pAdj === null ? '—' : formatPValue(pAdj)}
                        </td>
                        <td style={{ padding: '8px', textAlign: 'center', fontFamily: 'var(--font-mono)' }}>
                          {t.n} {isLowN && <span title="n < 30: số liệu tham khảo" style={{ color: 'var(--neu)' }}>*</span>}
                        </td>
                        <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                          {typeof t.ci_low === 'number' && typeof t.ci_high === 'number'
                            ? `${t.ci_low.toFixed(3)} – ${t.ci_high.toFixed(3)}`
                            : '—'}
                        </td>
                        <td style={{ padding: '8px' }}>
                          <Badge tone={isReject ? 'positive' : 'neutral'}>
                            {decisionText}
                          </Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Section 4: Formulas (FR-61) */}
        <section
          id="formulas"
          style={{
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
            padding: '24px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <FileText size={16} style={{ color: 'var(--googl)' }} />
            <h2 style={{ fontSize: '15px', fontWeight: 600 }}>4. Bảng quy chuẩn công thức tài chính</h2>
          </div>

          {methodLoading ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
              {[1, 2, 3, 4].map((i) => <Skeleton key={i} height={100} />)}
            </div>
          ) : !methodData?.formulas || Object.keys(methodData.formulas).length === 0 ? (
            <EmptyState>Chưa có công thức để hiển thị.</EmptyState>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
              {Object.entries(methodData.formulas).map(([key, item]) => (
                <div
                  key={key}
                  style={{
                    padding: '12px',
                    backgroundColor: 'var(--surface-2)',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--line)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                  }}
                >
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text)' }}>{key}</div>
                  <code style={{ fontSize: '11px', color: 'var(--msft)', padding: '2px 0' }}>{item.formula}</code>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{item.description}</div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Section 5: Data Sources (21 sources + negative sources, FR-62) */}
        <section
          id="sources"
          style={{
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
            padding: '24px',
          }}
        >
          <div style={{ marginBottom: '16px' }}>
            <h2 style={{ fontSize: '15px', fontWeight: 600 }}>
              5. Danh mục nguồn dữ liệu{methodData?.sources ? ` (${methodData.sources.length})` : ''} & Nguồn phủ định
            </h2>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Tất cả các con số đều có thể đối chiếu chéo về cổng thông tin gốc
            </p>
          </div>

          {methodLoading ? (
            <Skeleton height={200} />
          ) : !methodData?.sources ? (
            <EmptyState>Chưa có danh mục nguồn dữ liệu.</EmptyState>
          ) : methodData.sources.length === 0 ? (
            <EmptyState>Danh mục nguồn dữ liệu hiện đang trống.</EmptyState>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--line-strong)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '8px' }}>Tên nguồn</th>
                    <th style={{ padding: '8px' }}>Phân loại</th>
                    <th style={{ padding: '8px' }}>Địa chỉ liên kết</th>
                    <th style={{ padding: '8px', textAlign: 'center' }}>Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {methodData.sources.map((src) => (
                    <tr key={src.id} style={{ borderBottom: '1px solid var(--line)' }}>
                      <td style={{ padding: '8px', fontWeight: 500 }}>{src.name}</td>
                      <td style={{ padding: '8px', color: 'var(--text-muted)' }}>{src.kind}</td>
                      <td style={{ padding: '8px' }}>
                        <a
                          href={src.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={`Mở nguồn ${src.name}`}
                          style={{
                            color: 'var(--text-dim)',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            textDecoration: 'underline',
                          }}
                        >
                          <span>{src.url.replace('https://', '')}</span>
                          <ExternalLink size={11} />
                        </a>
                      </td>
                      <td style={{ padding: '8px', textAlign: 'center' }}>
                        <Badge tone={getSourceTone(src.status)}>{src.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {methodData?.negative_sources && methodData.negative_sources.length > 0 && (
            <div style={{ overflowX: 'auto', marginTop: '16px' }}>
              <h3 style={{ fontSize: '13px', fontWeight: 600, marginBottom: '8px' }}>
                Nguồn đã loại ({methodData.negative_sources.length})
              </h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--line-strong)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '8px' }}>Nguồn</th>
                    <th style={{ padding: '8px' }}>Trạng thái</th>
                    <th style={{ padding: '8px' }}>Lý do</th>
                  </tr>
                </thead>
                <tbody>
                  {methodData.negative_sources.map((source) => (
                    <tr key={source.id} style={{ borderBottom: '1px solid var(--line)' }}>
                      <td style={{ padding: '8px' }}>
                        <a href={source.url} target="_blank" rel="noopener noreferrer" aria-label={`Mở nguồn bị loại ${source.name}`}>
                          {source.name}
                        </a>
                      </td>
                      <td style={{ padding: '8px' }}><Badge tone={getSourceTone(source.status)}>{source.status}</Badge></td>
                      <td style={{ padding: '8px', color: 'var(--text-muted)' }}>{source.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </Layout>
  );
};
