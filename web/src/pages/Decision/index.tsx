import React from 'react';
import { Layout } from '../../components/shell/Layout';
import { useDecision } from '../../data/hooks';
import { formatPercent, formatRawPercent, formatNumber } from '../../lib/format';
import { Skeleton } from '../../components/ui/Skeleton';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { CheckCircle, AlertTriangle, AlertCircle, Info, ShieldCheck } from 'lucide-react';
import { i18n } from '../../i18n/vi';

export const DecisionPage: React.FC = () => {
  const { data, loading, error } = useDecision();

  const msft = data?.comparison?.find((c) => c.ticker === 'MSFT');
  const googl = data?.comparison?.find((c) => c.ticker === 'GOOGL');

  // Map status to badge tone
  const getStatusBadge = (status: string | undefined) => {
    switch (status) {
      case 'Tích cực':
      case 'positive':
        return <Badge tone="positive" icon={<CheckCircle size={12} />}>Tích cực</Badge>;
      case 'Trung lập':
      case 'neutral':
        return <Badge tone="neutral" icon={<Info size={12} />}>Trung lập</Badge>;
      case 'Cần thận trọng':
      case 'caution':
        return <Badge tone="caution" icon={<AlertTriangle size={12} />}>Cần thận trọng</Badge>;
      default:
        return <Badge tone="muted">{status || '—'}</Badge>;
    }
  };

  return (
    <Layout pageTitle={i18n.nav.decision} dataErrors={[error]}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        
        {/* Header Alert: No buy/sell recommendations */}
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            fontSize: '12px',
            color: 'var(--text-muted)',
          }}
        >
          <ShieldCheck size={16} style={{ color: 'var(--pos)', flexShrink: 0 }} />
          <span>Hệ thống phân tích khách quan hỗ trợ quyết định. Báo cáo không đưa ra khuyến nghị mua hoặc bán cổ phiếu.</span>
        </div>

        {/* Section 1: Comprehensive Comparison Table (FR-31, FR-32) */}
        <section
          style={{
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
            padding: '24px',
          }}
        >
          <div style={{ marginBottom: '20px' }}>
            <h2 style={{ fontSize: '15px', fontWeight: 600 }}>Bảng tổng hợp chỉ tiêu & Đánh giá trạng thái</h2>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Phân nhóm theo 5 trụ cột: Lợi suất, Tăng trưởng, Hiệu quả, Định giá và Rủi ro
            </p>
          </div>

          {loading ? (
            <Skeleton height={360} />
          ) : !data ? (
            <EmptyState>Chưa có dữ liệu đánh giá để hiển thị.</EmptyState>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--line-strong)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '10px 12px' }}>Trụ cột / Chỉ tiêu</th>
                    <th style={{ padding: '10px 12px' }}>Microsoft (MSFT)</th>
                    <th style={{ padding: '10px 12px' }}>Alphabet (GOOGL)</th>
                  </tr>
                </thead>
                <tbody>
                  {/* Status Row */}
                  <tr style={{ backgroundColor: 'var(--surface-2)', borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '10px 12px', fontWeight: 600 }}>Trạng thái tổng hợp</td>
                    <td style={{ padding: '10px 12px' }}>{getStatusBadge(msft?.status)}</td>
                    <td style={{ padding: '10px 12px' }}>{getStatusBadge(googl?.status)}</td>
                  </tr>

                  {/* 1. Lợi suất */}
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>Lợi suất theo quý (Stock Return)</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatPercent(msft?.stock_return_quarter)}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatPercent(googl?.stock_return_quarter)}</td>
                  </tr>

                  {/* 2. Tăng trưởng */}
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>Tăng trưởng doanh thu (YoY)</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatPercent(msft?.revenue_growth_yoy)}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatPercent(googl?.revenue_growth_yoy)}</td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>Tăng trưởng dòng tiền tự do (FCF YoY)</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatPercent(msft?.fcf_growth_yoy)}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatPercent(googl?.fcf_growth_yoy)}</td>
                  </tr>

                  {/* 3. Hiệu quả */}
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>Biên lợi nhuận hoạt động</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatPercent(msft?.operating_margin)}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatPercent(googl?.operating_margin)}</td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>Tỷ trọng R&D / Doanh thu</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatPercent(msft?.rd_intensity)}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatPercent(googl?.rd_intensity)}</td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>Tỷ trọng CapEx / Doanh thu</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatPercent(msft?.capex_intensity)}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatPercent(googl?.capex_intensity)}</td>
                  </tr>

                  {/* 4. Định giá */}
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>P/E trượt (12 tháng gần nhất)</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatNumber(msft?.pe_trailing, 1)}x</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatNumber(googl?.pe_trailing, 1)}x</td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>EPS trượt (12 tháng)</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>${formatNumber(msft?.eps_trailing_4q, 2)}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>${formatNumber(googl?.eps_trailing_4q, 2)}</td>
                  </tr>

                  {/* 5. Rủi ro */}
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>Độ biến động quy năm (Volatility)</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatRawPercent(msft?.annualized_volatility)}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatRawPercent(googl?.annualized_volatility)}</td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>Mức sụt giảm tối đa (Max Drawdown)</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatRawPercent(msft?.max_drawdown)}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{formatRawPercent(googl?.max_drawdown)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Section 2: Divergence Warning Card (FR-36) */}
        <section
          style={{
            backgroundColor: 'var(--surface-1)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-md)',
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertCircle size={16} style={{ color: 'var(--neu)' }} />
            <h3 style={{ fontSize: '14px', fontWeight: 600 }}>Cách đọc tín hiệu chi tiêu vốn và dòng tiền</h3>
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.5 }}>
            Khi tỷ trọng chi tiêu tài sản cố định (CapEx Intensity) tăng nhanh trong khi tốc độ tăng trưởng dòng tiền tự do (FCF Growth) chậm lại hoặc suy giảm, biên an toàn của doanh nghiệp có thể bị thu hẹp trong ngắn hạn trước khi hạ tầng AI chuyển hóa thành doanh thu.
          </p>
        </section>

        {/* Section 3: Statutory Disclaimer (FR-35) */}
        {data?.disclaimer && (
          <div
            style={{
              padding: '16px',
              backgroundColor: 'var(--surface-2)',
              borderRadius: 'var(--radius-md)',
              fontSize: '11px',
              color: 'var(--text-dim)',
              lineHeight: 1.6,
            }}
          >
            <strong>Miễn trừ trách nhiệm:</strong> {data.disclaimer}
          </div>
        )}
      </div>
    </Layout>
  );
};
