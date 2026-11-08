# AICOR Frontend — Báo cáo bàn giao

**Ngày:** 2026-11-08  
**Kết luận:** Frontend đã triển khai đủ sáu trang và vượt qua các kiểm thử hiện có, nhưng giai đoạn frontend **chưa hoàn tất hoàn toàn** theo ngưỡng trong `FRONTEND_PLAN.md`.

## Đã hoàn thành

- Shell điều hướng, bộ lọc công ty/benchmark, dark/light theme, trạng thái dữ liệu, thước quý lấy từ dataset thay vì danh sách hard-code.
- Sáu trang domain sử dụng dữ liệu thực trong `public/data/`; API dataset được kiểm tra envelope `schema_version`/`snapshot_version`, snapshot giữa các dataset phải đồng nhất; có fallback tĩnh.
- Calculator kiểm soát ngày/giá/chi phí, lưu/đổi tên/xóa kịch bản, CSV/PNG; lợi suất tháng/quý và bảng phân khúc dùng đúng field theo JSON thật.
- Bảng tài chính hỗ trợ sắp xếp/tìm kiếm, sparkline và nguồn; quý đang chọn được đánh dấu trong biểu đồ/bảng.
- Chart lazy-load theo viewport, ECharts dùng imports theo module, `prefers-reduced-motion` được tôn trọng.
- Đã sửa responsive header, bộ lọc và hàng rủi ro mobile; ảnh toàn trang của sáu route được lưu ở `evidence/` cho bốn cấu hình dark/light × desktop/mobile.

## Xác minh

| Kiểm tra | Kết quả |
|---|---|
| `npm run typecheck` | Pass |
| `npm test` | 8/8 pass |
| `npm run build` | Pass; chunk lớn nhất 249.55 kB minified / 82.14 kB gzip, không còn cảnh báo chunk >500 kB |
| `npm run test:e2e` | 32/32 pass trên Desktop Chrome và Mobile Chrome |
| Responsive | E2E kiểm tra 360, 768, 1440 px trên sáu trang |
| Reduced motion | E2E pass |
| Fallback API | E2E giả lập API 500 và xác nhận trang vẫn hiển thị dữ liệu tĩnh |
| SSE | E2E giả lập event `snapshot` với `changed=true`; backend SSE thật chưa xác minh |
| Tương phản | Các cặp token đại diện đã tính: 4.56:1 đến 13.27:1; đây không phải audit WCAG toàn trang |
| Lighthouse | Chưa chạy; chưa có bằng chứng đạt Mobile Performance ≥85 |

## Ảnh chụp giao diện

Mỗi trang có ảnh toàn trang theo bốn biến thể: `dark-desktop`, `light-desktop`, `dark-mobile`, `light-mobile`. Ví dụ:

- [Tổng quan — dark desktop](./evidence/overview-dark-desktop.png)
- [Tổng quan — light mobile](./evidence/overview-light-mobile.png)
- [Nhà đầu tư — light mobile](./evidence/investor-light-mobile.png)
- [Tài chính — light desktop](./evidence/financials-light-desktop.png)
- [AI — dark desktop](./evidence/ai-dark-desktop.png)
- [Quyết định — light mobile](./evidence/decision-light-mobile.png)
- [Phương pháp — dark desktop](./evidence/methodology-dark-desktop.png)

## Còn mở

1. Hoàn thiện kéo/brush chọn khoảng quý và đồng bộ hai chiều với biểu đồ; hiện tại thước quý cập nhật query và highlight quý trên biểu đồ kinh doanh/tài chính cùng bảng.
2. Crosshair đồng bộ giữa biểu đồ cùng trang chưa được nối.
3. Chạy Lighthouse bản production và xử lý nếu Mobile Performance <85.
4. Xác minh `GET /api/health`, API/ETag 304 và SSE `changed=true` với backend thật. Trong phiên này backend local không trả HTTP response ổn định; vì vậy chỉ xác nhận fallback và SSE bằng test mô phỏng.
5. Chạy audit accessibility tự động/toàn trang (ví dụ axe) và chốt tương phản cho mọi trạng thái/biểu đồ.

Các thiếu hụt trường dữ liệu và quy tắc quyết định vẫn được ghi tại [`GAPS.md`](./GAPS.md); không suy diễn ngưỡng hoặc lý do trạng thái ở frontend.

## Skills đã dùng

- `frontend-design`
- `vercel-react-best-practices`
- `frontend-testing`
- `web-design-guidelines`

## Chạy và deploy

Hướng dẫn setup, kiểm thử và deploy static nằm trong [`README.md`](./README.md). Bản build nằm tại `web/dist`; khi deploy static phải phục vụ `public/data` và cấu hình backend riêng nếu cần API/SSE.
