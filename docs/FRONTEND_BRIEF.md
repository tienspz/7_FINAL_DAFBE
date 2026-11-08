# AICOR — Frontend Brief & Technical Specification

> Tài liệu này là brief/đặc tả được lập trước khi triển khai frontend. Ứng dụng
> React + TypeScript hiện đã có trong `web/`; tiến độ, kết quả kiểm thử và các
> giới hạn còn lại được cập nhật tại [`web/PROGRESS.md`](../web/PROGRESS.md),
> [`web/FINAL_REPORT.md`](../web/FINAL_REPORT.md) và [`web/GAPS.md`](../web/GAPS.md).
> Các mục bên dưới mô tả yêu cầu và bối cảnh ban đầu, không phải khẳng định rằng
> mọi yêu cầu đã được hoàn tất.

## 0. Mục tiêu

Xây dashboard React **tối giản, hiện đại, độc nhất, đọc số liệu nhanh**, trông như sản phẩm thật chứ không phải bản demo AI. Người dùng là nhà đầu tư cá nhân, sinh viên, giảng viên: họ cần thấy con số và biểu đồ ngay, không phải đọc giải thích.

Thước đo cảm nhận: mở trang ra, 3 giây đầu phải thấy được "MSFT và GOOGL đang thế nào" mà không đọc câu chữ nào dài hơn một dòng.

## 1. Luật bất biến

1. **Phạm vi file**: chỉ làm việc trong `web/`. Không đụng `backend/`, `pipeline/`, `data/`, `config/`, `scripts/`, `tests/`, `DataProcessedView/`. Thư mục `web/public/data/` là output của pipeline và được CI ghi đè: **chỉ đọc, không sửa**.
2. **Không mock, không bịa**: mọi số trên UI đến từ JSON/API. Giá trị `null` hiển thị `—` kèm tooltip lý do ngắn (ví dụ "chưa đủ 4 quý để tính YoY"). Nếu spec đòi một trường mà dữ liệu chưa có (ví dụ lý do/điều kiện của trạng thái ở FR-33 mà `decision.json` hiện chỉ có `status`), **không tự suy diễn**: ghi vào `web/GAPS.md` và báo cuối pha.
3. **Không phải khuyến nghị đầu tư**: UI không dùng ngôn từ khuyên mua/bán, không dùng cụm "AI ROI", luôn nói rõ tương quan ≠ nhân quả (UI-07, FR-30, FR-35).
4. **Trung thực thống kê**: hiển thị `n` cạnh mọi hệ số; `n < 30` có dấu hiệu "tham khảo"; hiển thị p đã hiệu chỉnh Holm khi có; `p_value` trong JSON là **string**, dùng `p_value_display` nếu có, không `parseFloat` bừa.
5. **Truy vết**: mỗi con số tài chính/sự kiện có nút "Xem nguồn" (icon `external-link`, `target="_blank" rel="noopener noreferrer"`) mở `source_url` hoặc `evidence_url` (FR-65).
6. **Git**: lịch sử triển khai frontend đã dùng nhánh `feat/frontend` và được hợp nhất vào `main`. Với thay đổi tiếp theo, tuân theo quy trình nhánh hiện hành của repository; không tái tạo nhánh cũ. Không push `node_modules`, `dist`, báo cáo Playwright, ảnh tạm (thêm vào `.gitignore`).
7. **Bí mật**: không nhúng `CRON_SECRET` hay token nào vào client. Frontend **không** gọi `/api/refresh`.

## 2. Skills bắt buộc và thời điểm dùng

Agent phải **mở và đọc SKILL.md trước khi dùng**, và ghi trong `PROGRESS.md` skill nào đã dùng ở pha nào. Nếu một skill không tồn tại trong môi trường, ghi rõ và dùng phương án thay thế gần nhất, không giả vờ đã dùng.

| Skill | Dùng ở pha | Dùng để làm gì |
|---|---|---|
| **Awesome Design HTML**, **Awesome Claude Design** | 1 (Design) | Tham khảo cấu trúc design-system/DESIGN.md và mẫu bố cục dashboard dữ liệu. Chỉ học nguyên tắc, không sao chép nguyên mẫu. |
| **Taste Skill** | 1, 6 | Chốt gu thẩm mỹ, chống giao diện chung chung: tỷ lệ, nhịp spacing, phân cấp chữ, tiết chế màu. |
| **Image to Code** | 1, 3, 4 | Tạo ảnh tham chiếu (mockup) cho 4 màn hình chủ lực (Tổng quan dark desktop, Máy tính đầu tư mobile 360px, Heatmap AI dark, Quyết định light), rồi dựng lại sát ảnh. So sánh bằng ảnh chụp Playwright. |
| **emil-design-eng** (Emil Kowalski) | 5 | Chuyển động và chi tiết tương tác: easing, thời lượng, trạng thái nhấn, transform-origin, tôn trọng reduced-motion. Xem mục 6.3. |
| **Impeccable** | 1, 5, 7 | Kiểm toán thiết kế: typography, màu, khoảng cách, trạng thái (empty/loading/error/hover/focus/disabled). Chạy bản audit ở pha 7 và sửa hết mục mức cao. |
| **Web Design Guidelines** | 7 | Rà soát accessibility và UX: focus, label, kích thước vùng chạm, tương phản, semantic HTML, form. Sửa mọi vi phạm. |
| **Playwright CLI** | 2 → 8 | Chạy app thật, chụp ảnh, bắt console error, kiểm tra tương tác và responsive. Mọi lời "đã kiểm tra" phải kèm lệnh và ảnh/đầu ra thật. |

## 3. Hiện trạng repo và hợp đồng dữ liệu (đã xác minh)

Frontend đã được triển khai trong `web/` bằng React, TypeScript và Vite; ứng
dụng gồm sáu trang domain và có thể chạy với dữ liệu JSON tĩnh hoặc backend API.
Các hướng dẫn chạy/kiểm thử hiện hành nằm trong [`web/README.md`](../web/README.md).
Không tạo lại scaffold Vite hoặc sửa dữ liệu sinh tự động trong
`web/public/data/` khi chỉ cập nhật giao diện.

**Snapshot hiện tại**: `data_as_of = 2026-11-06`, `latest_quarter = 2026-Q3`, 2 công ty (MSFT, GOOGL), 19 quý mỗi công ty (2022-Q1 → 2026-Q3), benchmark SPY và QQQ, `verified_ratio = 1.0`, `low_metric_cells = 34`, `excluded_quarters = 16`. Đừng hard-code các số này, chỉ đọc từ manifest/quality summary.

**Backend** (chạy `python -m backend`, mặc định `http://127.0.0.1:8000`, CORS cho `localhost:5173`):

| Route | Dùng cho |
|---|---|
| `GET /api/health` | Độ tươi dữ liệu: `ok` / `degraded` / `unavailable`. `degraded` ⇒ vẫn hiển thị dashboard kèm cảnh báo, không phải lỗi cứng. |
| `GET /api/manifest` | Manifest + checksums |
| `GET /api/latest` | Freshness + manifest + `overview` + `decision` (một request cho first paint) |
| `GET /api/data/{key}` | Dataset đã kiểm checksum, có ETag/304, gzip. Key: `financials`, `overview`, `investor`, `ai_analysis`, `decision`, `methodology`, `tests`, `prices/MSFT`, `prices/GOOGL`, `prices/SPY`, `prices/QQQ` |
| `GET /api/events` | SSE: `ready`, `snapshot` (`{snapshot, changed}`), `refresh`, `refresh_finished`, `scheduler_error` |

Dùng `docs/api/types.ts` làm nguồn kiểu cho transport (copy vào `web/src/api/types.ts`, giữ nguyên). Đọc `openapi.yaml` để biết chính xác cú pháp key có dấu `/` như `prices/MSFT`.

**Hình dạng dataset** (đã kiểm tra thực tế, dùng `python`/`jq` để xem thêm, **không dán nguyên JSON vào context**):

- `overview.json`: `kpis[MSFT|GOOGL]` = `stock_return_1y, revenue_growth_latest, operating_margin_latest, fcf_margin_latest, latest_quarter, period_end, revenue_source_url`; `normalized_prices[GOOGL|MSFT|QQQ|SPY]` = 252 điểm `{date, value}` (base 100, ~1 năm); `business_comparison[ticker]` = 19 quý `{calendar_key, revenue_growth_yoy, operating_margin, fcf_margin}`.
- `investor.json`: `roi_windows[ticker]` = `roi_1y, roi_3y, roi_5y, annualized_volatility, max_drawdown`; `monthly_returns` (58 tháng) và `quarterly_returns` (19 quý) theo ticker; `quarter_end_prices`; `excess_return_tests`; `calculator_note`.
- `prices/{T}.json`: `rows[]` = `{date, open, high, low, close, adj_close, volume, dividends, stock_splits}`, từ 2020-12-01.
- `financials.json`: `quarters[]` (38) mỗi dòng có `metrics` (revenue, operating_income, net_income, rd_expense, capex, cfo, eps_diluted, total_equity…; mỗi metric có `value, unit, source_url, evidence_url, accession_number, fetched_at, verification/quality`) và `derived_metrics` (revenue_growth_yoy, operating_margin, net_profit_margin, rd_intensity, capex_intensity, fcf, fcf_margin, roe, roic, eps_trailing_4q, pe_trailing, stock_return_quarter, *_growth_yoy); `segments[]` (173 dòng, có cờ `comparable`, `quality_flag`).
- `ai_analysis.json`: `correlations[]` (70) = `{ticker, x, y, lag, method, statistic, p_value, p_adjusted, n, decision, note}`; `indicators[ticker][]` (19 quý); `events[]` (18) = `{title, category, label, published_date, source_url, evidence_quote, ...}`; `label_definitions` (Reported/Proxy/Estimated); `event_empty_state`; `warnings[]`.
- `decision.json`: `comparison[]` (2 dòng) = `stock_return_quarter, revenue_growth_yoy, operating_margin, fcf_growth_yoy, rd_intensity, capex_intensity, eps_trailing_4q, pe_trailing, annualized_volatility, max_drawdown, status`; `disclaimer`.
- `tests.json`: `results[]` (BT1–BT5), `alpha`, `quality_mode_*`, `warnings[]`, `quality_mode_comparison[]` (chuyển `exclude_low` / `label_low`).
- `methodology.json`: `formulas{}`, `sources[]` (21), `negative_sources[]`, `quality_report_summary`, `link_report_summary`, `reconcile_summary`.

**Giá trị `decision`** (kiểm tra bộ giá trị thực trong dữ liệu rồi map qua **một** từ điển duy nhất, có fallback hiển thị chuỗi gốc): `reject_h0` → "Bác bỏ H0", `fail_to_reject_h0` → "Không bác bỏ H0", `exploratory` → "Tham khảo (chưa kết luận)". Trạng thái quyết định: "Tích cực" / "Trung lập" / "Cần thận trọng".

**Máy tính đầu tư (F1)**: dùng cột `close` (đã điều chỉnh split) **cộng** `dividends`; biểu đồ giá dùng `adj_close`. **Không cộng cổ tức hai lần.** Công thức: `shares = (I0 − fees)/P0`, `Vt = shares×Pt + Dt`, `ROI = (Vt − I0)/I0`, `annualized = (1+ROI)^(365/days) − 1`. Ngày không phải phiên giao dịch → lấy phiên kế tiếp và báo bằng một dòng ngắn. Unit test bắt buộc: vốn 1.000, giá mua 100, giá đánh giá 130, cổ tức 20 ⇒ 10 cổ phiếu, 1.320, lãi 320, ROI 32% (số minh họa, nhãn "minh họa").

## 4. Kiến trúc frontend

- **Stack**: Vite + React 18 + TypeScript (strict). Router: React Router v6. Biểu đồ: **Apache ECharts** (crosshair đồng bộ qua `echarts.connect`, `dataZoom`/`brush`, heatmap, xuất PNG có sẵn), nạp lazy theo trang. Animation: **Framer Motion** (`motion`). Icon: `lucide-react`. Trạng thái bộ lọc: URL query (UI-11) qua router, không dùng store toàn cục cho thứ URL đã giữ. Dữ liệu: TanStack Query (hoặc hook tự viết nhẹ với ETag/cache).
- **Font** (tự host qua `@fontsource`, không gọi CDN): Geist Sans cho giao diện, Geist Mono cho số (`font-variant-numeric: tabular-nums`).
- **Cấu trúc**: `src/api/` (client, types, sse), `src/data/` (hook + selector theo dataset), `src/lib/` (finance.ts: calculator, format.ts: định dạng `vi-VN`), `src/components/` (ui, charts, shell), `src/pages/`, `src/styles/tokens.css`, `src/i18n/vi.ts` (toàn bộ nhãn + từ điển thuật ngữ), `DESIGN.md`.
- **Hiệu năng**: code-split theo route, ECharts import theo module (tree-shaking), ảnh/biểu đồ nặng lazy. Lighthouse Mobile Performance ≥ 85 ở trang chủ (UI-16).
- **Dev**: `vite.config.ts` proxy `/api` → `http://127.0.0.1:8000`. Viết `web/README.md` ngắn: cách chạy backend + frontend.

## 5. Định hướng thiết kế

Tên gọi nội bộ: **"Instrument panel"**: yên tĩnh, chính xác như bảng đồng hồ. Khung tối giản; **dữ liệu là thứ duy nhất có màu**.

### 5.1 Nguyên tắc
- Hairline 1px thay cho bóng đổ và khung dày. Phân tầng nền bằng độ sáng, không bằng viền màu mè.
- Số liệu lớn, đơn sắc, dùng Geist Mono; nhãn nhỏ, xám, chữ thường.
- Một **chữ ký riêng**: **thước quý (Quarter Ruler)**, thanh trục thời gian mảnh 2022-Q1 → 2026-Q3 ở đầu mỗi trang, vừa là bộ lọc khoảng thời gian (kéo để chọn, nhấp để chọn một quý) vừa đồng bộ với brush của biểu đồ. Đây là yếu tố nhận diện, không phải trang trí.
- Danh tính công ty phải phân biệt được **không chỉ bằng màu** (UI-04): MSFT = nét liền + marker tròn; GOOGL = nét liền + marker vuông; benchmark = nét đứt xám. Chú giải bật/tắt chuỗi được.
- Neon dùng **tiết chế**: chỉ cho đường/cột dữ liệu đang hoạt động, điểm nhấn trạng thái và focus ring. Không glow trên chữ, không gradient nền, không viền phát sáng quanh mọi thẻ.

### 5.2 Token khởi đầu

| Token | Dark (mặc định) | Light |
|---|---|---|
| `--bg` | `#07090C` | `#F6F5F1` |
| `--surface-1` | `#0D1116` | `#FFFFFF` |
| `--surface-2` | `#141A21` | `#EFEDE6` |
| `--line` | `#1F2933` | `#DAD7CC` |
| `--text` | `#E8EDF2` | `#0E1116` |
| `--text-muted` | `#8A97A6` (≥ 4.5:1 trên `--bg`) | `#566070` |
| `--msft` | neon cyan `#22E5FF` | `#007C91` |
| `--googl` | neon amber `#FFB020` | `#B06A00` |
| `--bench` | `#7C8794` nét đứt | `#6B7480` |
| `--pos` / `--neu` / `--neg` | `#34F5A0` / `#FFD166` / `#FF6B6B` | bản đậm hơn để đạt AA |

Quy tắc tương phản: chữ ≥ 4.5:1, thành phần đồ họa và đường biểu đồ ≥ 3:1 trên nền của chúng, **ở cả hai chế độ** (UI-14). Chế độ sáng không dùng neon, dùng bản đậm tương ứng. Trạng thái luôn có **icon + chữ**, không chỉ màu.

Dark mode là mặc định theo `prefers-color-scheme` khi lần đầu, sau đó nhớ lựa chọn (try/catch quanh `localStorage`). Công tắc ở topbar, không dùng emoji.

### 5.3 Typography và nhịp
Thang chữ 5 bậc (12/13/15/20/32 hoặc tương đương), số KPI 32–44 mono. Lưới 4px. Một container tối đa ~1280px. Khoảng thở rộng quanh KPI, dày đặc có tổ chức ở bảng.

## 6. Chống "mùi AI", microcopy và chuyển động

### 6.1 Cấm tuyệt đối
- Emoji trong UI. Gradient tím-xanh. Icon trong vòng tròn màu ở lưới 3 thẻ giống nhau. Glassmorphism khắp nơi. Thẻ bo tròn quá lớn lồng nhau.
- Câu mở đầu kiểu "Chào mừng đến với…", "Khám phá…", "Dưới đây là…", slogan, mô tả dưới mỗi tiêu đề, chú thích kỹ thuật dành cho dev ("dữ liệu lấy từ…", "component này…", TODO, lorem, "demo", "powered by").
- Ghi chú giải thích dài trên trang. Mọi giải thích chuyển vào **tooltip thuật ngữ** (≤ 12 từ) hoặc popover "Thông tin" mở theo yêu cầu.
- Bình luận trong code kiểu hướng dẫn cho người đọc AI. Comment chỉ khi giải thích "vì sao".

### 6.2 Microcopy
Tiêu đề trang 1–3 từ. Nhãn ngắn, danh từ. Một dòng là tối đa cho mọi chuỗi trong UI (trừ trang Phương pháp). Số theo `vi-VN` (ví dụ `32,0%`, `$1.320`), tiền tệ USD, ngày `dd/MM/yyyy`, quý `Q1 2022`. Thuật ngữ tài chính giữ tiếng Anh (FCF, ROIC, CapEx) nhưng có tooltip tiếng Việt.

**Cảnh báo bắt buộc (UI-07, FR-30, FR-35)**: nén thành **một thanh/chip cố định gọn** (icon `info` + "Tương quan ≠ nhân quả · Không phải khuyến nghị đầu tư", nhấp để mở popover chi tiết). Không viết thành đoạn văn.

### 6.3 Chuyển động (emil-design-eng)
- Easing vào/ra: ease-out mạnh, ví dụ `cubic-bezier(0.23, 1, 0.32, 1)`. Không dùng `ease-in`/linear cho UI.
- Thời lượng: tương tác nhỏ 120–200ms, chuyển trang và drawer ≤ 280ms (UI-08), biểu đồ vẽ dần ≤ 700ms.
- Chỉ animate `transform` và `opacity`. Không bắt đầu từ `scale(0)`; bắt đầu từ ~0.96 kèm opacity.
- Nút nhấn: `:active` scale ~0.97. Popover/tooltip có `transform-origin` theo vị trí kích hoạt.
- Stagger danh sách ≤ 40ms/phần tử, tổng ≤ 300ms. KPI đếm tăng dần (một lần khi vào màn hình).
- Không animate hành động lặp rất thường xuyên bằng bàn phím (đổi tab bằng phím, đổi k bằng phím mũi tên: phản hồi tức thì).
- `prefers-reduced-motion`: tắt đếm số, vẽ dần, trượt; chỉ giữ fade ngắn (UI-09). Phải có test.

## 7. Shell và điều hướng

- **Topbar cố định** (UI-02): trái là nút **hamburger** (icon `menu`, `aria-expanded`, `aria-controls`); giữa/trái là tên trang; phải là bộ lọc toàn cục dạng chip nhỏ (công ty, benchmark), chỉ báo đồng bộ (chấm trạng thái + "cập nhật 2 giờ trước", xem 9.3) và công tắc sáng/tối.
- **Drawer điều hướng** mở từ hamburger (cả desktop và mobile): trượt từ trái ≤ 280ms, có scrim, đóng bằng Esc/nhấp scrim/chọn mục, **focus trap**, trả focus về nút hamburger. Danh sách 6 mục có icon `lucide` và dấu hiệu mục đang mở:
  1. Tổng quan (`layout-dashboard`)
  2. Lợi suất cổ đông (`trending-up`)
  3. Tài chính (`landmark` hoặc `bar-chart-3`)
  4. Đầu tư AI (`cpu` hoặc `sparkles`)
  5. Quyết định (`scale`)
  6. Phương pháp & nguồn (`book-open-check`)
  Chân drawer: phiên bản snapshot (mono, mờ).
- Chuyển trang: fade + trượt nhẹ ≤ 280ms. Khôi phục vị trí cuộn hợp lý.
- Bộ lọc toàn cục (công ty, benchmark, khoảng thời gian/quý) **nằm trong URL query**, tải lại hoặc chia sẻ link vẫn giữ nguyên (UI-11).
- Phím tắt (không bắt buộc, làm nếu còn thời gian): `[` / `]` đổi trang, `T` đổi theme.

## 8. Đặc tả 6 trang

Mỗi trang phải có đủ trạng thái: **skeleton** khi tải, **lỗi** (hiển thị thông báo ngắn + dữ liệu cũ nhất còn hợp lệ, không bao giờ để trang trống, UI-15), **rỗng** (dùng `event_empty_state` khi không có sự kiện).

### 8.1 Tổng quan `/` (dữ liệu: `overview`)
- Hàng KPI: mỗi công ty 4 chỉ số (`stock_return_1y`, `revenue_growth_latest`, `operating_margin_latest`, `fcf_margin_latest`), số đếm tăng dần, mũi tên/dấu tăng giảm kèm chữ, nút "Xem nguồn" ở số doanh thu.
- Biểu đồ giá chuẩn hóa (base 100, MSFT/GOOGL/benchmark) với crosshair, tooltip, bật/tắt chuỗi, nét vẽ dần.
- Biểu đồ so sánh hiệu quả kinh doanh theo quý (biên hoạt động, biên FCF, tăng trưởng doanh thu); chuyển chỉ số bằng segmented control; cột mọc lên.
- Tuổi dữ liệu và thời điểm cập nhật hiển thị ở topbar (FR-39).

### 8.2 Lợi suất cổ đông `/investor` (dữ liệu: `investor`, `prices/*`)
- **Máy tính** (FR-01..FR-10): chọn cổ phiếu (segmented), vốn, ngày mua, ngày đánh giá, phí (tùy chọn). Kết quả: giá trị cuối, lãi/lỗ, ROI, lợi suất quy năm, vượt trội so với benchmark. Biểu đồ giá trị khoản đầu tư theo thời gian vẽ dần. Lỗi nhập hiển thị ngay dưới trường, ngắn gọn. Ví dụ minh họa có nhãn "minh họa" (UI-06) và không dùng cho kiểm định.
- Biểu đồ giá: chuyển tuyệt đối/chuẩn hóa (UI-10), chọn SPY/QQQ, brush/zoom/reset.
- Thẻ ROI cửa sổ 1/3/5 năm, độ biến động, MDD (`roi_windows`), ẩn cửa sổ khi chưa đủ dữ liệu.
- Cột lợi suất tháng/quý; kết quả BT1 (excess return) ở dạng thẻ nhỏ: thống kê, p, n, CI 95%, kết luận.
- **Kịch bản đã lưu** (F10, FR-58..60): lưu `localStorage` bọc try/catch, so sánh song song 2 kịch bản, đổi tên, xóa.
- Xuất CSV (kèm nguồn, ngày cập nhật, phiên bản dữ liệu) và PNG biểu đồ (FR-55..57).

### 8.3 Tài chính `/financials` (dữ liệu: `financials`)
- Sáu chỉ số cốt lõi + ROE/ROIC theo quý cho MSFT và GOOGL: chọn chỉ số bằng tab, biểu đồ đường/cột so sánh hai công ty, crosshair đồng bộ.
- **Bảng chỉ số** (UI-13): sắp xếp, tìm kiếm, sparkline theo quý, nút "Xem nguồn" từng dòng. Ô có `quality = low` đánh dấu bằng icon + tooltip, không chỉ màu.
- Khối phân khúc đám mây (Intelligent Cloud vs Google Cloud): chỉ hiển thị dòng `comparable`; nếu không tương đương, đánh dấu và giải thích bằng tooltip ngắn (FR-21).
- Hiển thị ngày kết thúc kỳ thực tế của từng quý (FR-22), quy đổi về quý lịch.

### 8.4 Đầu tư AI `/ai` (dữ liệu: `ai_analysis`, `tests`)
- Thanh trượt độ trễ **k = 0..4** (hỗ trợ bàn phím), **heatmap** tương quan (hàng: chỉ báo đầu tư R&D/CapEx growth; cột: Revenue growth, FCF growth, Operating margin, Stock return) chuyển mượt khi đổi k. Mỗi ô: `r`, `p` đã hiệu chỉnh, `n` (UI-12). Ô `n < 30` có dấu "tham khảo". Chọn công ty bằng bộ lọc toàn cục.
- Biểu đồ chuỗi chỉ báo AI theo quý, phủ **timeline sự kiện AI** (18 sự kiện): marker nhấp được mở thẻ với tiêu đề, ngày, nhãn, trích dẫn bằng chứng, nút "Xem nguồn".
- Nhãn **Reported / Proxy / Estimated** hiển thị bằng chip phân biệt hình dạng/icon (FR-29). Estimated không dùng trong MVP: chỉ hiện khi dữ liệu có.
- Thanh cảnh báo cố định (xem 6.2). Hiển thị n hiệu dụng và ghi chú ADF/sai phân khi dữ liệu có (FR-30a).

### 8.5 Quyết định `/decision` (dữ liệu: `decision`)
- Bảng so sánh 2 công ty theo các chỉ tiêu trong `comparison` (FR-31/32), nhóm theo: Lợi suất, Tăng trưởng, Hiệu quả, Định giá, Rủi ro. Huy hiệu trạng thái **Tích cực / Trung lập / Cần thận trọng** với icon + chữ + ngày cập nhật.
- Cảnh báo khi CapEx tăng nhưng FCF suy giảm, hoặc định giá cao (FR-36): tính từ dữ liệu có sẵn bằng ngưỡng đọc từ cấu hình hiển thị công khai nếu có; nếu ngưỡng không được xuất ra frontend, ghi vào `GAPS.md` thay vì tự đặt ngưỡng.
- Không có nút/câu "mua/bán". Hiển thị `disclaimer` từ dữ liệu.

### 8.6 Phương pháp & nguồn `/methodology` (dữ liệu: `methodology`, `tests`, `manifest`, `/api/health`)
- Công thức mọi chỉ số (`formulas`) dạng danh sách gọn, công thức hiển thị bằng font mono.
- Bảng nguồn (21 nguồn + nguồn phủ định) có trạng thái, link.
- Tóm tắt chất lượng: số quý thiếu, tỷ lệ verified, kết quả link report, reconcile (FR-63).
- Bảng kiểm định BT1–BT5: thống kê, p thô/p hiệu chỉnh, n, CI, kết luận bằng tiếng Việt dễ hiểu (FR-50); công tắc `quality_mode` (`exclude_low` / `label_low`) lấy từ `tests.quality_mode_comparison`; liệt kê quý bị loại và lý do (FR-52); cảnh báo `n < 30`.
- Trạng thái hệ thống (chỉ đọc): snapshot version, checksum ok, tuổi dữ liệu. Không có nút refresh.
- Đây là trang duy nhất được phép nhiều chữ hơn, nhưng vẫn gọn, có mục lục neo (`#hash` đơn giản).

## 9. Data layer và thời gian thực

### 9.1 Lấy dữ liệu
1. Thử `GET /api/data/{key}` (kèm ETag/`If-None-Match`, xử lý `304`).
2. Nếu API không tới được (lỗi mạng/`503`/`502`), **fallback** sang file tĩnh cùng nguồn `/data/{key}.json`. Production trên Vercel có thể không có backend, nên đường tĩnh phải chạy được độc lập.
3. Không bao giờ để trang trắng: giữ dữ liệu hợp lệ gần nhất trong bộ nhớ và hiển thị chip cảnh báo ngắn.
4. Mọi dữ liệu qua một lớp **validate + typed selectors**: kiểm tra `schema_version`, `snapshot_version` đồng nhất giữa các dataset; lệch thì cảnh báo, không crash.

### 9.2 Hợp đồng chuỗi thời gian
Dùng `calendar_key` (`2022-Q1`) làm khóa quý. Dùng `period_end` cho ngày kết thúc kỳ thực. Giá theo `date`. Tính toán trong trình duyệt chỉ cho calculator; các chỉ số khác lấy nguyên từ pipeline (không tự tính lại số liệu tài chính).

### 9.3 Chỉ báo đồng bộ và SSE
- Hook `useSnapshotStream` kết nối `/api/events` (EventSource). Xử lý `ready`, `snapshot` (đọc `payload.snapshot.*`, `changed`), `refresh`, `refresh_finished`, `scheduler_error`. Tự kết nối lại; nếu SSE không có (production tĩnh), bỏ qua êm, không báo lỗi.
- Khi `changed = true`: hiện chip nhỏ "Có dữ liệu mới" + nút tải lại (không tự đổi dữ liệu giữa lúc người dùng đang thao tác).
- Chỉ báo ở topbar: chấm xanh khi `ok`, vàng khi `degraded/stale`, đỏ khi `unavailable`, kèm chữ tuổi dữ liệu ("2 giờ trước"). Tooltip: snapshot version, `data_as_of`, `checksum_ok`.

## 10. Tương tác biểu đồ (UI-10, FR-15)
Crosshair đồng bộ giữa các biểu đồ cùng trang; brush chọn khoảng thời gian đồng bộ với Quarter Ruler; zoom và nút reset; bật/tắt chuỗi qua chú giải; tooltip có đơn vị và `n` khi cần; trục luôn ghi đơn vị. Xuất PNG qua API của ECharts. Dùng cùng một theme ECharts sinh từ design tokens (cập nhật khi đổi dark/light).

## 11. Quy trình theo pha (có GATE)

Làm theo vertical slice, kiểm chứng từng pha. Sau mỗi pha: cập nhật `web/PROGRESS.md` (đã làm gì, skill nào đã dùng, kết quả test, vấn đề còn lại), commit, rồi **DỪNG ở GATE** chờ xác nhận.

- **Pha 0 — Recon & Plan**: Đọc tài liệu, kiểm tra skills, chạy thử backend (`python -m backend`) và `curl /api/health`, `/api/data/overview`. Xuất Implementation Plan.
- **Pha 1 — Design system**: Tạo `DESIGN.md`, `tokens.css` (dark/light), theme ECharts, bộ component cơ bản (Button, IconButton, Chip, Tooltip, Popover, Segmented, Skeleton, Badge, Drawer). Dùng Awesome Design HTML, Awesome Claude Design, Taste, Impeccable, Image to Code (tạo 4 ảnh mockup tham chiếu và lưu trong `web/design-refs/`).
- **Pha 2 — Scaffold + data layer**: Vite, router, typed API client, fallback tĩnh, ETag, SSE, validate, `finance.ts` + Vitest.
- **Pha 3 — Shell + Tổng quan**: Topbar, hamburger drawer, theme, Quarter Ruler, bộ lọc URL, trang 8.1.
- **Pha 4 — Các trang còn lại**: Làm lần lượt 8.2 → 8.6, mỗi trang xong chạy Playwright smoke test. Dùng Image to Code cho màn hình đã có mockup.
- **Pha 5 — Motion & chi tiết**: Áp dụng mục 6.3 (emil-design-eng), hover/focus/active/disabled cho mọi tương tác, đếm số KPI, vẽ dần đường, heatmap đổi k mượt, reduced-motion.
- **Pha 6 — Rà soát thẩm mỹ & nội dung**: Rà "mùi AI" (Taste Skill): đối chiếu mục 6.1, cắt chữ thừa, kiểm tra nhịp, tỷ lệ, gu màu neon. Không có chữ nào dành cho dev còn sót.
- **Pha 7 — Audit**: Chạy audit đầy đủ (Impeccable + Web Design Guidelines), sửa mọi lỗi mức cao/trung, ghi lại mức thấp trong `GAPS.md`.
- **Pha 8 — Verify cuối + bàn giao**: Chạy toàn bộ ma trận mục 12 (Playwright CLI), `npm run build`, kiểm tra bundle và Lighthouse. Viết `web/README.md`, cập nhật `.gitignore`.

## 12. Ma trận kiểm chứng (Playwright CLI + Vitest)
1. Console: Không lỗi/cảnh báo bất thường.
2. Viewport: 360, 768, 1440; không cuộn ngang ở `body`.
3. Theme: Cả dark và light cho mọi trang.
4. Tương phản: Chữ ≥ 4.5:1, đường/biểu tượng ≥ 3:1 (đo kiểm thực).
5. Điều hướng: Hamburger mở/đóng, Esc, focus trap, trả focus, URL query giữ bộ lọc sau reload.
6. Bàn phím: Tab hợp lý, visible focus ring, slider k bằng phím mũi tên.
7. Calculator: Khớp test 1.000/100/130/20; lỗi đầu vào; ngày ngoài phiên có báo.
8. Dữ liệu: Fallback tĩnh chạy khi tắt backend; không trắng trang khi lỗi.
9. SSE: Nhận ready; snapshot changed=true hiện chip "Có dữ liệu mới".
10. Trung thực: n hiện cạnh hệ số; n < 30 có dấu hiệu; "Xem nguồn" mở đúng link; null hiện "—".
11. Motion: prefers-reduced-motion tắt đếm số và vẽ dần.
12. Hiệu năng: Lighthouse Mobile Performance ≥ 85.
13. Quét chữ: Không còn emoji, "Chào mừng", lorem, TODO, ghi chú dev.
14. Build: `npm run build` sạch; `npm run typecheck` và `vitest` xanh.
