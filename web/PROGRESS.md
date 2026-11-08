# AICOR Frontend — Tiến độ triển khai

| Pha | Tên pha | Trạng thái | Skill đã dùng | Bằng chứng | Còn lại |
|---|---|---|---|---|---|
| 0 | Recon & Plan | **Hoàn thành có giới hạn** | frontend-design, frontend-testing | Đối chiếu `FRONTEND_PLAN.md`, dữ liệu tĩnh và cấu hình frontend. | Backend HTTP thật chưa xác minh được trong môi trường này. |
| 1 | Design System | **Hoàn thành** | frontend-design, web-design-guidelines | Dark/light tokens, UI kit, typography, focus state và ảnh tham chiếu đã có. | Không còn mục chặn. |
| 2 | Scaffold + Data Layer | **Hoàn thành** | vercel-react-best-practices, frontend-testing | TypeScript pass; 8/8 Vitest; E2E kiểm fallback khi API trả 500; kiểm tra envelope và snapshot đồng nhất. | ETag 304/live API chưa được kiểm chứng với backend thật. |
| 3 | Shell + Tổng quan | **Hoàn thành** | frontend-design, frontend-testing | 19 quý được lấy từ dữ liệu; URL query cho bộ lọc; dữ liệu KPI/biểu đồ có nguồn; responsive 360/768/1440. | Brush kéo chọn quý chưa nối hai chiều với biểu đồ. |
| 4 | Các trang còn lại | **Hoàn thành** | frontend-design, frontend-testing | Sáu trang domain được smoke-test trên Desktop Chrome và Mobile Chrome; đã sửa tên trường dữ liệu theo JSON thật. | Các giới hạn dữ liệu được ghi ở `GAPS.md`. |
| 5 | Motion & Chi tiết | **Hoàn thành** | vercel-react-best-practices, frontend-testing | Reduced-motion được kiểm tra; ECharts lazy-load; chart tải theo module; export PNG/CSV và kịch bản được test. | Không còn mục chặn. |
| 6 | Rà soát thẩm mỹ & nội dung | **Hoàn thành cơ bản** | frontend-design | 24 ảnh: sáu trang ở dark/light, desktop/mobile; đã sửa lỗi nội dung hiển thị `undefined`, giá phân khúc rỗng giả và cắt nội dung rủi ro trên mobile. | Cần review sản phẩm cuối trên backend/snapshot triển khai thực tế. |
| 7 | Audit thiết kế & UX | **Một phần** | web-design-guidelines | Kiểm tra focus, reduced motion, nhãn biểu đồ và tương phản các cặp màu token đại diện (4.56:1–13.27:1). | Chưa chạy axe hoặc audit WCAG tự động toàn trang. |
| 8 | Verify cuối & Bàn giao | **Chưa hoàn tất** | frontend-testing | `npm run typecheck`, `npm test` (8/8), `npm run build`, `npm run test:e2e` (32/32); ảnh lưu trong `evidence/`. Bundle lớn nhất 249.55 kB minified / 82.14 kB gzip. | Chưa chạy Lighthouse Mobile Performance ≥85; chưa xác minh API/SSE trực tiếp; brush/crosshair đồng bộ còn thiếu. |

## Kết luận

Frontend có thể chạy với dữ liệu JSON tĩnh và các kiểm tra hiện có đều xanh, nhưng **chưa thể đánh dấu toàn bộ giai đoạn frontend hoàn tất** theo `FRONTEND_PLAN.md`. Pha 8 còn mở cho đến khi Lighthouse đạt ngưỡng, backend/SSE thật được xác minh và tương tác brush/crosshair được hoàn thiện.

Các lệnh xác minh cuối:

```powershell
cd web
npm run typecheck
npm test
npm run build
npm run test:e2e
```
