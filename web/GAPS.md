# AICOR Frontend — Báo cáo sai lệch dữ liệu (GAPS.md)

Tài liệu này ghi nhận các trường dữ liệu được đặc tả trong SPEC nhưng pipeline chưa xuất ra frontend, theo đúng quy định tại Điều 2 của `FRONTEND_BRIEF.md`.

## 1. Quyết định (FR-33 & FR-36)
- **Hiện trạng dữ liệu `decision.json`**: Trường `status` hiện chỉ trả về chuỗi ngắn gọn (`"Tích cực"` / `"positive"`).
- **Yêu cầu spec (FR-33)**: Hiển thị lý do và điều kiện kích hoạt trạng thái (ví dụ: các ngưỡng định lượng cụ thể để chuyển đổi giữa Tích cực -> Trung lập -> Cần thận trọng).
- **Xử lý frontend**: Giao diện hiển thị đúng trạng thái gốc `"Tích cực"` kèm badge màu và biểu tượng, không tự suy diễn hoặc bịa đặt logic ngưỡng trong client.

## 2. Ngưỡng phân kỳ chi tiêu vốn & dòng tiền (FR-36)
- **Hiện trạng**: Cấu hình ngưỡng cảnh báo phân kỳ (CapEx tăng nhưng FCF giảm) không được xuất ra frontend dưới dạng biến độc lập.
- **Xử lý frontend**: Hiển thị thẻ cảnh báo nguyên lý phân kỳ định tính và khuyến cáo kiểm tra trực tiếp trên bảng tài chính 19 quý thay vì tự gán số liệu giả định.

## 3. Tương tác biểu đồ và kiểm chứng triển khai
- **Thước quý**: Chọn một quý cập nhật URL và highlight quý tương ứng trong biểu đồ kinh doanh/tài chính và bảng. Kéo brush để chọn khoảng quý và đồng bộ hai chiều với biểu đồ chưa được triển khai.
- **Crosshair**: Đồng bộ crosshair giữa nhiều biểu đồ cùng trang chưa được triển khai.
- **API/SSE thật**: E2E đã xác nhận fallback JSON khi API lỗi và đã mô phỏng event SSE `changed=true`; API/ETag/SSE thật chưa xác minh được vì backend local không trả HTTP response ổn định.
- **Hiệu năng/accessibility**: Build đã giảm chart bundle lớn nhất xuống 249.55 kB minified (82.14 kB gzip); Lighthouse và audit accessibility tự động toàn trang chưa chạy.
