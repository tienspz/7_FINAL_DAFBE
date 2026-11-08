import React, { useState, useRef } from 'react';
import { Button } from '../../components/ui/Button';
import { IconButton } from '../../components/ui/IconButton';
import { Badge } from '../../components/ui/Badge';
import { Chip } from '../../components/ui/Chip';
import { Tooltip } from '../../components/ui/Tooltip';
import { Popover } from '../../components/ui/Popover';
import { Segmented } from '../../components/ui/Segmented';
import { Skeleton } from '../../components/ui/Skeleton';
import { Drawer } from '../../components/ui/Drawer';
import { Sun, Moon, Menu, ExternalLink, Info, CheckCircle, AlertTriangle } from 'lucide-react';

export const DevKitPage: React.FC = () => {
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'MSFT' | 'GOOGL'>('MSFT');
  const [chipActive, setChipActive] = useState(true);
  const hamburgerRef = useRef<HTMLButtonElement>(null);

  const toggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
    document.documentElement.setAttribute('data-theme', nextTheme);
  };

  return (
    <div style={{ minHeight: '100vh', padding: '32px 24px', backgroundColor: 'var(--bg)', color: 'var(--text)' }}>
      <div style={{ maxWidth: '960px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '32px' }}>
        
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--line)', paddingBottom: '16px' }}>
          <div>
            <h1 style={{ fontSize: '20px', fontWeight: 600 }}>AICOR UI Kit (/__kit)</h1>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Môi trường kiểm tra Design System, tokens và micro-interactions</p>
          </div>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <Button variant="outline" size="sm" onClick={toggleTheme} icon={theme === 'dark' ? <Sun size={14}/> : <Moon size={14}/>}>
              Đổi Theme ({theme})
            </Button>
            <IconButton ref={hamburgerRef} aria-label="Mở menu" variant="secondary" onClick={() => setDrawerOpen(true)}>
              <Menu size={18} />
            </IconButton>
          </div>
        </div>

        {/* Section 1: Buttons */}
        <section style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <h2 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-muted)' }}>1. Buttons & IconButtons</h2>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="secondary" icon={<ExternalLink size={14} />}>Xem nguồn</Button>
            <Button variant="secondary" disabled>Disabled</Button>
            <IconButton aria-label="Info"><Info size={16} /></IconButton>
          </div>
        </section>

        {/* Section 2: Badges & Chips */}
        <section style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <h2 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-muted)' }}>2. Badges & Chips</h2>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
            <Badge tone="positive" icon={<CheckCircle size={12}/>}>Tích cực</Badge>
            <Badge tone="neutral">Trung lập</Badge>
            <Badge tone="caution" icon={<AlertTriangle size={12}/>}>Cần thận trọng</Badge>
            <Badge tone="msft">Microsoft (MSFT)</Badge>
            <Badge tone="googl">Alphabet (GOOGL)</Badge>
            <Chip active={chipActive} onClick={() => setChipActive(!chipActive)}>
              Chip có thể bấm ({chipActive ? 'Active' : 'Inactive'})
            </Chip>
          </div>
        </section>

        {/* Section 3: Segmented & Tooltip & Popover */}
        <section style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <h2 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-muted)' }}>3. Segmented, Tooltip & Popover</h2>
          <div style={{ display: 'flex', gap: '20px', alignItems: 'center', flexWrap: 'wrap' }}>
            <Segmented
              ariaLabel="Công ty minh họa"
              options={[
                { value: 'MSFT', label: 'Microsoft' },
                { value: 'GOOGL', label: 'Alphabet' },
              ]}
              value={activeTab}
              onChange={setActiveTab}
            />

            <Tooltip content="Tooltip giải thích ngắn gọn dưới 12 từ.">
              <Button variant="outline" size="sm">Hover xem Tooltip</Button>
            </Tooltip>

            <Popover
              title="Cảnh báo pháp lý"
              trigger={<span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', background: 'var(--surface-2)' }}><Info size={14} />Mở Popover</span>}
            >
              Tương quan không đồng nghĩa với quan hệ nhân quả. Số liệu mang tính khách quan thống kê.
            </Popover>
          </div>
        </section>

        {/* Section 4: Skeletons */}
        <section style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <h2 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-muted)' }}>4. Skeletons (Trạng thái nạp)</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '400px' }}>
            <Skeleton height={28} width="60%" />
            <Skeleton height={16} width="100%" />
            <Skeleton height={16} width="80%" />
          </div>
        </section>

        {/* Drawer */}
        <Drawer
          isOpen={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          triggerRef={hamburgerRef}
        >
          <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', height: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <span style={{ fontWeight: 600, fontSize: '16px' }}>Điều hướng</span>
              <Button size="sm" variant="ghost" onClick={() => setDrawerOpen(false)}>Đóng</Button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
              <Button variant="ghost" style={{ justifyContent: 'flex-start' }}>1. Tổng quan</Button>
              <Button variant="ghost" style={{ justifyContent: 'flex-start' }}>2. Lợi suất cổ đông</Button>
              <Button variant="ghost" style={{ justifyContent: 'flex-start' }}>3. Tài chính</Button>
              <Button variant="ghost" style={{ justifyContent: 'flex-start' }}>4. Đầu tư AI</Button>
              <Button variant="ghost" style={{ justifyContent: 'flex-start' }}>5. Quyết định</Button>
              <Button variant="ghost" style={{ justifyContent: 'flex-start' }}>6. Phương pháp & nguồn</Button>
            </div>
            <div style={{ borderTop: '1px solid var(--line)', paddingTop: '12px', fontSize: '11px', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
              Snapshot: v20261106.9
            </div>
          </div>
        </Drawer>
      </div>
    </div>
  );
};
