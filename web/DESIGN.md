# AICOR Design System — Instrument Panel

## 1. Triết lý Thiết kế
Giao diện tuân thủ phong cách **"Instrument Panel"** (bảng khí tài):
- Khung tối giản, hairline 1px thay thế bóng đổ và viền dày.
- Dữ liệu là thứ duy nhất có màu (Neon Cyan `#22E5FF` cho Microsoft, Neon Amber `#FFB020` cho Google Alphabet).
- Chế độ Sáng (Light Mode) tự động chuyển sang tone trầm đậm để đảm bảo tương phản WCAG AA (≥ 4.5:1 với chữ, ≥ 3:1 với yếu tố đồ họa).
- Typography: Geist Sans cho nội dung, Geist Mono cho toàn bộ số liệu tài chính (`font-variant-numeric: tabular-nums`).

## 2. Thang Màu & Tokens

### Bảng màu Bề mặt & Chữ
| Token | Dark (Mặc định) | Light | Mục đích |
|---|---|---|---|
| `--bg` | `#07090C` | `#F6F5F1` | Nền canvas toàn trang |
| `--surface-1` | `#0D1116` | `#FFFFFF` | Nền thẻ, bảng, panel |
| `--surface-2` | `#141A21` | `#EFEDE6` | Nền thứ cấp, header bảng, chip |
| `--surface-hover` | `#1C242E` | `#E4E1D8` | Trạng thái hover |
| `--line` | `#1F2933` | `#DAD7CC` | Đường kẻ hairline 1px |
| `--text` | `#E8EDF2` | `#0E1116` | Chữ chính |
| `--text-muted` | `#8A97A6` | `#566070` | Nhãn phụ (≥ 4.5:1) |
| `--text-dim` | `#5C6773` | `#7A8699` | Chú thích tối |

### Nhận diện Công ty & Trạng thái
| Thực thể | Dark | Light | Ký hiệu thị giác (UI-04) |
|---|---|---|---|
| **Microsoft (MSFT)** | `#22E5FF` (Neon Cyan) | `#007C91` | Nét liền + Marker tròn |
| **Alphabet (GOOGL)** | `#FFB020` (Neon Amber) | `#B06A00` | Nét liền + Marker vuông |
| **Benchmark (SPY/QQQ)** | `#7C8794` | `#6B7480` | Nét đứt xám |
| **Tích cực (Positive)** | `#34F5A0` | `#0A8754` | Icon mũi tên lên / Check |
| **Trung lập (Neutral)** | `#FFD166` | `#946300` | Icon gạch ngang / Minus |
| **Cần thận trọng (Caution)** | `#FF6B6B` | `#D32F2F` | Icon cảnh báo / AlertTriangle |

## 3. Typography & Lưới không gian
- **Font:** Geist Sans (UI) & Geist Mono (Số liệu).
- **Thang chữ 5 bậc:**
  - KPI Hero: 36px / 44px (Mono 600)
  - Tiêu đề Section (H2): 18px / 24px (Sans 600)
  - Tiêu đề Card / Header bảng (H3): 14px / 20px (Sans 500)
  - Nội dung Body: 13px / 18px (Sans 400)
  - Nhãn phụ / Meta: 11px / 14px (Sans/Mono 400)
- **Lưới 4px:** 4, 8, 12, 16, 20, 24, 32, 40, 48px.
- **Max Width Container:** 1280px, căn giữa với padding 16px (mobile) đến 24px (desktop).

## 4. Chuyển động & Vi mô (Emil Kowalski)
- Đường cong: `cubic-bezier(0.23, 1, 0.32, 1)`.
- Nút bấm: `:active` scale 0.97.
- Drawer: trượt từ trái 280ms kèm scrim mờ 50%. Focus trap bằng phím Tab và phím Esc để đóng.
- Tôn trọng `prefers-reduced-motion`: chuyển tức thì, tắt đếm số và vẽ dần.

## 5. Chữ ký thương hiệu: Thước Quý (Quarter Ruler)
Thanh trượt 19 quý từ `2022-Q1` đến `2026-Q3` đặt cố định phía dưới Topbar:
- Kéo hoặc nhấp quý để đồng bộ bộ lọc URL (`?q=...&range=...`) và cập nhật ECharts brush.
- Hiển thị dấu chỉ quý được kiểm toán (SEC 10-Q/10-K).

