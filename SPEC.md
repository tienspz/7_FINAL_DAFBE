# Software Requirements Specification

## AICOR – AI & Stock Investment Intelligence

| | |
|---|---|
| **Tên đề tài** | Hệ thống phân tích hiệu quả đầu tư cổ phiếu và hiệu quả kinh doanh gắn với đầu tư AI của Microsoft và Alphabet theo quý (AICOR) |
| **Phiên bản** | 2.0 (bản chuẩn hóa để vibe code) |
| **Môn học** | Data Analysis for Business Environment (71DAEE10012), Học kỳ 1 năm 2026–2027 |
| **Mẫu tham chiếu** | Carnegie Mellon University – SRS Template (IEEE Std 830-1998) |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Overall Description](#2-overall-description)
3. [System Features](#3-system-features)
4. [External Interface Requirements](#4-external-interface-requirements)
5. [Other Nonfunctional Requirements](#5-other-nonfunctional-requirements)
6. [Other Requirements](#6-other-requirements)
- [Appendix A: Glossary](#appendix-a-glossary)
- [Appendix B: Analysis Models](#appendix-b-analysis-models)
- [Appendix C: Issues List và quyết định đã chốt](#appendix-c-issues-list-và-quyết-định-đã-chốt)
- [Appendix D: Lịch thực hiện](#appendix-d-lịch-thực-hiện-9-tuần)
- [Appendix E: Lộ trình Vibe Code](#appendix-e-lộ-trình-vibe-code)
- [Appendix F: Cấu trúc repository và quy ước](#appendix-f-cấu-trúc-repository-và-quy-ước)
- [Appendix G: Ma trận truy vết](#appendix-g-ma-trận-truy-vết)
- [Appendix H: Đối chiếu với đề cương môn học](#appendix-h-đối-chiếu-với-đề-cương-môn-học)

---

## 1. Introduction

### 1.1 Purpose

Tài liệu đặc tả yêu cầu phần mềm cho **AICOR**, ứng dụng web phân tích đồng thời (1) hiệu quả đầu tư cổ phiếu và (2) hiệu quả kinh doanh của **Microsoft (MSFT)** và **Alphabet (GOOGL)**, kèm lớp kết nối khảo sát mối liên hệ giữa đầu tư AI, kết quả kinh doanh và biến động cổ phiếu. Tài liệu áp dụng cho toàn bộ phiên bản 1.0 của hệ thống và được viết để một công cụ lập trình bằng AI (vibe coding) có thể thực hiện từng milestone mà không phải đoán ý.

### 1.2 Document Conventions

- Mã yêu cầu: `FR-xx` chức năng, `NFR-xx` phi chức năng, `UI-xx` giao diện, `SI-xx` giao tiếp phần mềm, `DR-xx` dữ liệu, `CR-xx` crawler, `DP-xx` triển khai.
- Mức ưu tiên: **Cao** (bắt buộc MVP), **Trung bình** (giai đoạn 2), **Thấp** (giai đoạn 3).
- "Phải" là bắt buộc; "nên" là khuyến nghị.
- Công thức viết dạng văn bản thuần trong khối mã.
- Đơn vị tiền tệ mặc định: USD. Đơn vị tài chính lưu: triệu USD.
- Mọi yêu cầu có tiêu chí chấp nhận kiểm chứng được ở Phụ lục E (cột DoD) hoặc Phụ lục G.

### 1.3 Intended Audience and Reading Suggestions

| Đối tượng | Nên đọc |
|---|---|
| Giảng viên, người chấm | Mục 1, 2, 3, 5, Phụ lục H |
| Thành viên pipeline dữ liệu | Mục 3.7, 4.3, 6, Phụ lục B, E, F |
| Thành viên phân tích | Mục 3.3–3.5, 3.8, Phụ lục A, B |
| Thành viên web | Mục 3.1, 3.2, 3.6, 4.1, 5, Phụ lục E |
| Công cụ vibe code (AI) | Toàn bộ, đặc biệt Phụ lục E, F |
| Người dùng cuối | Mục 1.4, 2.2, 2.3 |

### 1.4 Project Scope

**Mục tiêu sản phẩm:** giúp người dùng đánh giá hiệu quả đầu tư cổ phiếu MSFT và GOOGL, phân tích hiệu quả kinh doanh và hoạt động đầu tư vào AI của hai doanh nghiệp, hỗ trợ quyết định dựa trên dữ liệu có nguồn kiểm chứng được.

**Trong phạm vi**

- Giả lập khoản đầu tư MSFT/GOOGL: số cổ phiếu, giá trị, cổ tức, lợi nhuận, ROI, so sánh benchmark.
- Phân tích hiệu quả kinh doanh theo quý: doanh thu, lợi nhuận, dòng tiền, R&D, CapEx, ROIC, ROE.
- Tương quan có độ trễ 1–4 quý giữa đầu tư (R&D, CapEx) với kết quả kinh doanh và lợi suất cổ phiếu.
- Dashboard tương tác có hiệu ứng chuyển động; trang hỗ trợ quyết định có trạng thái giải thích được.
- Dữ liệu từ Q1/2022 đến quý gần nhất có hồ sơ SEC hợp lệ.
- Kiểm định giả thuyết thống kê cho BT1–BT5 trên số liệu thật.
- Crawler tự động từ nguồn chính thức, mỗi số liệu có liên kết nguồn mở được và đã qua kiểm tra liên kết.
- Xuất dữ liệu và biểu đồ, lưu và so sánh kịch bản, trang Phương pháp & Nguồn dữ liệu.

**Ngoài phạm vi**

- Dự báo giá cổ phiếu hoặc kết quả kinh doanh.
- Khuyến nghị mua/bán tự động dựa vào một chỉ số.
- Khẳng định nhân quả; dùng tên "AI ROI".
- Giao dịch thật, kết nối môi giới, tư vấn thuế.
- Công ty khác ngoài Microsoft và Alphabet.

**Lưu ý nền tảng:** khi nhà đầu tư mua cổ phiếu trên sàn, tiền chuyển cho người bán chứ không vào tài khoản công ty. Hệ thống không dùng tổng tiền giao dịch cổ phiếu làm mẫu số cho doanh thu công ty.

### 1.5 References

1. IEEE Std 830-1998, *Recommended Practice for Software Requirements Specifications*.
2. Carnegie Mellon University, *Software Requirements Specification Template*.
3. SEC EDGAR: https://www.sec.gov/edgar/search/ (Microsoft CIK 789019; Alphabet CIK 1652044).
4. SEC EDGAR API: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
5. SEC chính sách truy cập tự động (User-Agent, giới hạn tốc độ): https://www.sec.gov/os/webmaster-faq#developers
6. Microsoft Investor Relations: https://www.microsoft.com/en-us/Investor/
7. Alphabet Investor Relations: https://abc.xyz/investor/
8. Yahoo Finance qua `yfinance`: https://github.com/ranaroussi/yfinance
9. Stooq (nguồn giá đối chiếu): https://stooq.com/
10. Vercel Docs (Cron Jobs, Functions, Git Integration): https://vercel.com/docs
11. Đề cương môn học: http://dangtrankhanh.net/teaching/VLU-PTDLDN/BusinessDataAna-253.html
12. Tài liệu "Thiết kế lại bài toán AICOR" (Nhóm 7); slide gốc "Nhom_7___1_.pptx".

Các URL ở mục 1.5 là điểm tham chiếu để người thực hiện mở kiểm tra; chúng không phải dữ liệu của hệ thống. Dữ liệu của hệ thống chỉ được lấy qua crawler (mục 3.7) và qua kiểm tra liên kết (CR-10).

### 1.6 Tổng quan đề tài (5W)

| Câu hỏi | Trả lời |
|---|---|
| **Who** | Nhóm 7 (3 thành viên) xây dựng. Người dùng chính là nhà đầu tư cá nhân; ngoài ra sinh viên, giảng viên, nhà báo công nghệ. |
| **What** | Ứng dụng web phân tích hiệu quả đầu tư cổ phiếu và hiệu quả kinh doanh của Microsoft, Alphabet, kèm khảo sát liên hệ với đầu tư AI. |
| **Where** | Trình duyệt web; frontend và dữ liệu tĩnh triển khai trên Vercel; thu thập chạy trên GitHub Actions. Đối tượng phân tích: MSFT và GOOGL niêm yết tại Mỹ. |
| **When** | 9 tuần (Phụ lục D). Dữ liệu theo quý từ Q1/2022 đến quý mới nhất. |
| **Why** | Nhà đầu tư thường chỉ xem giá hoặc báo cáo tài chính riêng lẻ. AICOR đặt hai góc nhìn cạnh nhau, mỗi con số mở được về hồ sơ gốc. |

### 1.7 Bài toán hướng đến

**Bài toán chính**

> Đánh giá hiệu quả đầu tư cổ phiếu và hiệu quả kinh doanh của Microsoft và Alphabet theo quý, đồng thời xem hoạt động đầu tư AI có đi cùng với kết quả kinh doanh và hiệu suất cổ phiếu hay không.

**Bài toán con và giả thuyết (α = 0,05; chỉ cho thấy tương quan/khác biệt, không chứng minh nhân quả)**

| Mã | Bài toán con | H0 | Phép kiểm định mặc định | Tính năng | Yêu cầu |
|---|---|---|---|---|---|
| BT1 | Đầu tư MSFT hoặc GOOGL trong một khoảng thời gian thì lời bao nhiêu, có vượt thị trường không? | Lợi suất vượt benchmark trung bình bằng 0 | Lợi suất vượt benchmark theo tháng: one-sample t hoặc Wilcoxon signed-rank | F1, F2, F8 | FR-01..15, FR-48 |
| BT2 | Doanh thu, lợi nhuận, dòng tiền biến động ra sao, công ty nào tăng trưởng tốt hơn? | Tăng trưởng doanh thu YoY trung bình của MSFT bằng GOOGL | Paired t hoặc Wilcoxon signed-rank trên các quý lịch cùng kỳ | F3, F4, F8 | FR-16..23, FR-48 |
| BT3 | R&D và CapEx thay đổi thế nào theo thời gian? | Hệ số xu hướng của R&D Intensity (và CapEx Intensity) bằng 0 | Hồi quy OLS theo thời gian, sai số HAC (Newey–West) | F3, F8 | FR-17, FR-48 |
| BT4 | R&D/CapEx tăng thì kết quả kinh doanh các quý sau (độ trễ 1–4) có đi cùng không? | Corr(RD_Growth(t), RevenueGrowth(t+k)) = 0, k = 0..4 | Pearson hoặc Spearman theo Shapiro–Wilk; hiệu chỉnh Holm | F5, F8 | FR-24, 25, 48..54 |
| BT5 | Kết quả kinh doanh có liên hệ với hiệu suất cổ phiếu không? | Corr(RevenueGrowth(t), StockReturn(t+k)) = 0, k = 0..4 | Như BT4 | F5, F6, F8 | FR-26, 48..54 |

### 1.8 Điểm đặc biệt của đề tài (đề xuất để nhóm duyệt; bắt buộc chốt trước khi nộp)

| # | Điểm đặc biệt | So sánh với công cụ khác | Tính năng |
|---|---|---|---|
| 1 | Mỗi con số trên giao diện có nút "Xem nguồn" mở đúng hồ sơ SEC hoặc trang giá gốc; CI kiểm tra liên kết định kỳ | Các dashboard tài chính phổ biến hiển thị số liệu nhưng ít khi dẫn tới hồ sơ gốc ở từng ô | F7, F11 |
| 2 | Đặt hai góc nhìn (lợi suất cổ đông và hiệu quả doanh nghiệp) cạnh nhau với kiểm định thống kê có hiệu chỉnh đa kiểm định và cảnh báo n nhỏ | Công cụ thường chỉ vẽ giá hoặc chỉ liệt kê báo cáo tài chính | F5, F8 |
| 3 | Pipeline tái lập được: dữ liệu đóng băng thành snapshot có phiên bản, kết quả kiểm định gắn phiên bản và ngày | Phần lớn đồ án/dashboard không lưu phiên bản dữ liệu | F7, F8 |

---

## 2. Overall Description

### 2.1 Product Perspective

AICOR là sản phẩm mới, độc lập, thay thế hướng tiếp cận ban đầu (điểm E = Out − In) bằng mô hình hai nhánh:

- **Nhánh A – Investor Return:** lợi nhuận cổ đông nhận được.
- **Nhánh B – Business Performance:** kết quả và hiệu quả sử dụng vốn của doanh nghiệp.
- **Lớp kết nối – AI & Stock Analysis:** mối liên hệ theo thời gian giữa hai nhánh.

Hai nhánh không phải cùng một dòng tiền; giao diện phải thể hiện rõ điều này.

**Kiến trúc ba lớp, không có máy chủ chạy liên tục:**

```
[GitHub Actions - cron]
  Collection : crawler Python  -> data/raw/*.csv (append-only) + data/raw/_cache
  Verify     : verify_links, reconcile -> data/verified/*
  Computation: pandas/statsmodels -> data/db/aicor.sqlite + public/data/*.json
  Commit     : bot commit "data: snapshot vYYYYMMDD.N" lên nhánh main
        |
        v   (Vercel Git Integration tự build khi có commit)
[Vercel]
  Display    : React (Vite) đọc /data/*.json cùng nguồn gốc
  /api/health: Vercel Function đọc manifest, báo tuổi dữ liệu
  Vercel Cron: gọi /api/health hằng ngày; nếu dữ liệu quá hạn thì gọi GitHub workflow_dispatch
```

"Service ngầm" trong tài liệu này gồm hai thành phần: (1) workflow cron của GitHub Actions thực hiện thu thập và tính toán; (2) Vercel Cron kiểm tra độ tươi dữ liệu và kích hoạt lại workflow khi trễ.

### 2.2 Product Features

| Mã | Tính năng | Giai đoạn |
|---|---|---|
| F1 | Máy tính đầu tư cổ phiếu | 1 – MVP |
| F2 | Biểu đồ giá, lợi suất, so sánh benchmark | 1 – MVP |
| F3 | Phân tích tài chính doanh nghiệp (6 chỉ số cốt lõi) | 1 – MVP |
| F4 | So sánh MSFT–GOOGL, FCF, ROIC, ROE, Cloud | 2 |
| F5 | Phân tích đầu tư AI và kết quả kinh doanh (độ trễ 1–4 quý) | 2 (nâng từ 3) |
| F6 | Hỗ trợ quyết định, trạng thái có giải thích | 2 (nâng từ 3) |
| F7 | Crawler, kiểm tra liên kết, pipeline tự động, nhật ký đồng bộ | 1 – MVP |
| F8 | Kiểm định giả thuyết BT1–BT5 | 1 (BT1–BT3); 2 (BT4–BT5) |
| F9 | Xuất dữ liệu và biểu đồ (CSV, PNG) | 2 |
| F10 | Lưu và so sánh kịch bản | 2 |
| F11 | Trang Phương pháp & Nguồn dữ liệu | 1 – MVP |

Sáu chỉ số cốt lõi MVP: Stock Total Return, Revenue Growth, Net Income Growth, Free Cash Flow, R&D / Revenue, CapEx / Revenue.

### 2.3 User Classes and Characteristics

| Lớp người dùng | Đặc điểm | Ưu tiên |
|---|---|---|
| Nhà đầu tư cá nhân mới | Ít kiến thức tài chính, cần giải thích thuật ngữ | Cao |
| Nhà đầu tư có kinh nghiệm | Quan tâm FCF, ROIC, benchmark, độ trễ | Cao |
| Sinh viên, giảng viên, nhà báo | Kiểm tra nguồn và phương pháp | Trung bình |
| Quản trị viên (nhóm phát triển) | Giám sát pipeline, `sync_log` | Thấp |

### 2.4 Operating Environment

- Trình duyệt: Chrome, Edge, Firefox, Safari (hai phiên bản chính gần nhất), máy tính và điện thoại.
- Frontend: React 18+, TypeScript, Vite, host trên Vercel.
- Pipeline: Python 3.11+, GitHub Actions (Ubuntu runner).
- Lưu trữ: CSV, SQLite, JSON trong repository.

### 2.5 Design and Implementation Constraints

- Chỉ dùng dữ liệu công khai, miễn phí; tuân thủ giới hạn tốc độ SEC và điều khoản nguồn giá.
- Khóa API (nếu có) chỉ trong GitHub Secrets và Vercel Environment Variables.
- Dữ liệu thô append-only, không ghi đè.
- **Ranh giới tính toán:** chỉ calculator đầu tư (FR-03..FR-08) và chọn khoảng thời gian hiển thị được tính trong trình duyệt. Mọi chỉ số tài chính, tương quan, kiểm định tính ở pipeline.
- Microsoft kết thúc năm tài chính tháng 6, Alphabet tháng 12: lưu ngày kết thúc kỳ thực tế và quy đổi quý lịch.
- Ngôn ngữ giao diện: tiếng Việt; mã nguồn và comment tiếng Anh.
- Gói Vercel miễn phí có giới hạn về tần suất Cron và thời gian chạy Function; người thực hiện phải đọc giới hạn hiện hành trong tài liệu Vercel trước khi cấu hình (DP-05).
- 9 tuần, 3 thành viên.

### 2.6 User Documentation

- Trang "Giới thiệu & Phương pháp" trong ứng dụng.
- Tooltip cho mỗi chỉ số.
- `README.md` ở repository: chạy pipeline cục bộ, cấu trúc dữ liệu, triển khai Vercel.

### 2.7 Assumptions and Dependencies

**Giả định:** 10-Q/10-K, giá, cổ tức của MSFT và GOOGL có đủ cho 2022–nay; tên chỉ tiêu XBRL ổn định giữa các kỳ (nếu đổi, cập nhật `concept_map.yaml`).

**Phụ thuộc:** SEC EDGAR, Yahoo Finance (`yfinance`, không chính thức), Stooq, GitHub Actions, Vercel. 10-Q có thể chậm vài tuần sau khi quý kết thúc.

---

## 3. System Features

### 3.1 Stock Investment Calculator (F1) – Ưu tiên: Cao

**Stimulus/Response**

1. Người dùng chọn cổ phiếu, nhập vốn, ngày mua, ngày đánh giá (tùy chọn phí).
2. Hệ thống tra giá tại hai ngày trong `prices.json`, tính toán trong trình duyệt.
3. Hiển thị kết quả và biểu đồ giá trị khoản đầu tư theo thời gian với hiệu ứng vẽ dần.
4. Nếu ngày chọn không phải ngày giao dịch, dùng phiên kế tiếp và thông báo.

| Mã | Yêu cầu |
|---|---|
| FR-01 | Cho phép chọn MSFT hoặc GOOGL. |
| FR-02 | Cho nhập vốn (USD, > 0), ngày mua, ngày đánh giá (> ngày mua). |
| FR-03 | `Shares = (I0 − Fees) / P0`, chấp nhận cổ phiếu lẻ. |
| FR-04 | `Vt = Shares × Pt + Dt`. |
| FR-05 | `Profit = Vt − I0`; `ROI = Profit / I0 × 100%`. |
| FR-06 | `Annualized = (1 + ROI)^(365/Days) − 1`, ROI dạng thập phân. |
| FR-07 | Tính `Dt` từ cổ tức thực tế trong thời gian nắm giữ; không cộng hai lần khi dùng giá điều chỉnh. |
| FR-08 | Hiển thị `Excess = Stock Return − Benchmark Return`. |
| FR-09 | Hiển thị ghi chú: chưa tính thuế, tỷ giá; chỉ minh họa. |
| FR-10 | Báo lỗi rõ khi đầu vào không hợp lệ hoặc ngoài khoảng dữ liệu. |

**Ví dụ kiểm chứng (dùng làm unit test, số giả định không phải dữ liệu thị trường):** vốn 1.000, giá mua 100, giá đánh giá 130, cổ tức 20 → 10 cổ phiếu, giá trị cuối 1.320, lợi nhuận 320, ROI 32%. Phải có nhãn "minh họa" khi hiển thị ví dụ này (UI-06).

### 3.2 Stock Performance Charts (F2) – Ưu tiên: Cao

| Mã | Yêu cầu |
|---|---|
| FR-11 | Hiển thị giá theo thời gian; chế độ chuẩn hóa giá đầu kỳ = 100. |
| FR-12 | Chọn benchmark SPY hoặc QQQ. |
| FR-13 | Hiển thị giá trị giả lập khoản đầu tư theo thời gian. |
| FR-14 | Hiển thị ROI theo khoảng nắm giữ 1, 3, 5 năm khi đủ dữ liệu. |
| FR-15 | Tooltip giá trị khi rê chuột/chạm, có đường ngắm (crosshair) đồng bộ giữa các biểu đồ. |

### 3.3 Company Financial Performance (F3, F4) – Sáu chỉ số cốt lõi: Cao; ROIC, ROE, Cloud: Trung bình

| Mã | Yêu cầu |
|---|---|
| FR-16 | Tính và hiển thị Revenue Growth YoY, Net Income Growth, Operating Margin, Net Profit Margin theo quý. |
| FR-17 | Tính R&D Intensity và CapEx Intensity (chia doanh thu cùng kỳ). |
| FR-18 | `FCF = CFO − CapEx`; `FCF Margin = FCF / Revenue`. |
| FR-19 | Nên tính `ROE = Net Income / Average Equity`. |
| FR-20 | Nên tính `ROIC = NOPAT / Average Invested Capital`; `NOPAT = Operating Income × (1 − Tax Rate)`; định nghĩa vốn đầu tư theo mục C.2. |
| FR-21 | Nên hiển thị doanh thu và biên lợi nhuận phân khúc Intelligent Cloud (MSFT), Google Cloud (Alphabet) kèm ghi chú phạm vi không tương đương. |
| FR-22 | Quy đổi kỳ tài chính về quý lịch khi so sánh; hiển thị ngày kết thúc kỳ thực tế. |
| FR-23 | Hiển thị ghi chú: R&D, CapEx là chỉ báo cấp công ty, không đồng nghĩa toàn bộ dành cho AI. |

### 3.4 AI Investment Analysis (F5) – Ưu tiên: Trung bình

| Mã | Yêu cầu |
|---|---|
| FR-24 | Tính `RD_Growth`, `CapEx_Growth` theo YoY (cách 4 quý). |
| FR-25 | Tính tương quan giữa `RD_Growth`/`CapEx_Growth` tại t với `RevenueGrowth`, `FCFGrowth`, `OperatingMargin` tại t+k, k ∈ {0..4}. |
| FR-26 | `StockReturn_t = (AdjPrice_t − AdjPrice_t−1) / AdjPrice_t−1` theo quý lịch; mốc giá là phiên giao dịch cuối cùng không muộn hơn ngày cuối quý; tính `Corr(RD_Growth_t, StockReturn_t+k)`. |
| FR-27 | Hiển thị n cạnh mỗi hệ số; cảnh báo khi n < 30. |
| FR-28 | Hiển thị timeline sự kiện AI (`ai_event`) phủ lên biểu đồ; mỗi sự kiện có `source_url`. |
| FR-29 | Gắn nhãn mỗi chỉ báo AI là `Reported`, `Proxy` hoặc `Estimated`, phân biệt trực quan. |
| FR-30 | Không dùng tên "AI ROI"; luôn hiển thị cảnh báo "tương quan, không phải nhân quả". |
| FR-30a | Pipeline phải báo n hiệu dụng sau khi mất quan sát do YoY/độ trễ và chạy kiểm tra dừng (ADF) trên mỗi chuỗi; nếu không dừng, dùng sai phân bậc 1 và ghi rõ trên giao diện. |

### 3.5 Stock Decision Support (F6) – Ưu tiên: Trung bình

| Mã | Yêu cầu |
|---|---|
| FR-31 | Bảng so sánh: Stock Return, Revenue Growth, Operating Margin, FCF Growth, R&D Intensity, CapEx Intensity, Valuation (P/E, EPS), Risk. |
| FR-32 | Nên tính Volatility và Maximum Drawdown. |
| FR-33 | Gán trạng thái "Tích cực", "Trung lập", "Cần thận trọng" cho từng nhóm tiêu chí kèm lý do, điều kiện, ngày cập nhật. Ngưỡng nằm trong `config/thresholds.yaml`. |
| FR-34 | Không khuyến nghị mua/bán chỉ dựa trên một chỉ số. |
| FR-35 | Hiển thị nhãn "Không phải khuyến nghị đầu tư". |
| FR-36 | Cảnh báo khi CapEx tăng nhưng FCF suy giảm, hoặc định giá cao. |

### 3.6 Executive Overview – Ưu tiên: Cao

| Mã | Yêu cầu |
|---|---|
| FR-37 | Thẻ KPI: Stock Return và Revenue Growth của MSFT và GOOGL ở kỳ mới nhất có dữ liệu. |
| FR-38 | Biểu đồ giá chuẩn hóa và biểu đồ so sánh hiệu quả kinh doanh. |
| FR-39 | Hiển thị thời điểm cập nhật gần nhất và tuổi dữ liệu. |

### 3.7 Data Collection Pipeline và Crawler (F7) – Ưu tiên: Cao

**Stimulus/Response:** cron kích hoạt → crawler lấy dữ liệu từ nguồn chính thức → ghi CSV append-only kèm bằng chứng nguồn → `verify` kiểm tra liên kết và đối chiếu → tính chỉ số → ghi SQLite/JSON → cập nhật `manifest.json`, `sync_log` → commit → Vercel build.

| Mã | Yêu cầu |
|---|---|
| FR-40 | Lấy giá, cổ tức, chia tách MSFT, GOOGL, SPY, QQQ qua `yfinance`. |
| FR-41 | Lấy R&D, CapEx, doanh thu, lợi nhuận, dòng tiền, tài sản, vốn chủ, nợ từ SEC EDGAR; phát hiện hồ sơ mới. |
| FR-42 | Tuân thủ giới hạn tốc độ SEC (không quá 10 yêu cầu/giây, nên giữ ≤ 5) và khai báo `User-Agent` có tên và email liên hệ thật. |
| FR-43 | Ghi dữ liệu thô append-only; mỗi bản ghi có `source_url`. |
| FR-44 | Ghi `sync_log` (thời điểm, nguồn, trạng thái, số bản ghi); xử lý lỗi (thử lại có lùi dần, không làm hỏng dữ liệu cũ). |
| FR-45 | Kiểm tra thiếu, trùng, sai đơn vị; đánh dấu quý thiếu hoặc độ tin cậy thấp. |
| FR-46 | Tính toán chỉ số một lần, xuất SQLite/JSON cho giao diện. |
| FR-47 | Giá: chạy mỗi ngày sau khi thị trường Mỹ đóng cửa. Hồ sơ SEC: kiểm tra mỗi 6 giờ trong tháng sau khi quý kết thúc, các thời điểm khác mỗi ngày. Cho phép chạy thủ công (`workflow_dispatch`). |

**Yêu cầu crawler và chống bịa dữ liệu**

| Mã | Yêu cầu |
|---|---|
| CR-01 | Nguồn chính cho số liệu tài chính là SEC EDGAR: `https://data.sec.gov/submissions/CIK##########.json` (phát hiện hồ sơ) và `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` (số liệu XBRL). CIK đệm 0 đủ 10 chữ số. |
| CR-02 | Mỗi giá trị tài chính phải lưu: `accession_number`, `form` (10-Q/10-K), `filing_date`, `period_end`, `xbrl_tag`, `unit`, `source_url` trỏ tới trang chỉ mục hồ sơ `https://www.sec.gov/Archives/edgar/data/<CIK>/<accession không dấu gạch>/`, `fetched_at`, `response_sha256`. |
| CR-03 | Ánh xạ chỉ tiêu ↔ thẻ XBRL đặt trong `config/concept_map.yaml` (ví dụ doanh thu, thu nhập hoạt động, lợi nhuận ròng, chi phí R&D, chi mua tài sản cố định, dòng tiền hoạt động). Khi thẻ không tồn tại cho một kỳ, ghi `missing`, không suy diễn. |
| CR-04 | Quý 4 không có 10-Q. Giá trị Q4 = giá trị năm (10-K) − tổng Q1..Q3, gắn `derived=true`, và chỉ dùng trong kiểm định khi cấu hình cho phép. |
| CR-05 | Nguồn giá chính: `yfinance`. Nguồn đối chiếu: Stooq CSV (`https://stooq.com/q/d/l/?s=<mã>.us&i=d`) hoặc nguồn miễn phí tương đương. Nếu `yfinance` lỗi, chuyển sang nguồn đối chiếu và gắn `price_source`. |
| CR-06 | Đối chiếu IR: trang Investor Relations của hai công ty chỉ dùng để đối chiếu thủ công mẫu 5 chỉ số (NFR-12), không là nguồn crawler tự động. |
| CR-07 | Crawler không được có hằng số số liệu tài chính viết cứng, không dùng LLM để sinh hoặc điền số. Số liệu chỉ đến từ phản hồi HTTP lưu kèm hash. |
| CR-08 | Mọi phản hồi gốc được cache dưới `data/raw/_cache/<sha256>` (hoặc lưu tóm tắt trích xuất) để kiểm tra lại; dùng `If-None-Match`/ETag nếu máy chủ hỗ trợ. |
| CR-09 | Quy tắc Reported/Proxy/Estimated: số lấy trực tiếp từ hồ sơ = `Reported`; chỉ báo đại diện (ví dụ CapEx làm proxy hạ tầng AI) = `Proxy`; số từ mô hình/ước tính ngoài = `Estimated` kèm nguồn ước tính. |
| CR-10 | **Kiểm tra liên kết (`verify_links`):** với mỗi `source_url` duy nhất, thực hiện HTTP GET (tôn trọng giới hạn tốc độ); yêu cầu mã 200; với hồ sơ SEC, xác nhận `accession_number` xuất hiện trong nội dung và `period_end` khớp; với số liệu XBRL, xác nhận lại giá trị bằng cách gọi `companyconcept` (hoặc đọc lại `companyfacts`) và so khớp tuyệt đối. Bản ghi không qua kiểm tra bị gắn `quality_flag=missing` và `verified=false`. |
| CR-11 | Kết quả `verify_links` ghi vào `data/verified/link_report.json` (URL, mã HTTP, thời điểm, kết quả); CI thất bại nếu tỷ lệ liên kết hỏng của các giá trị cốt lõi > 0. |
| CR-12 | Chạy `verify_links` lại hằng tuần (lịch riêng) để phát hiện liên kết chết; kết quả hiển thị tại trang Phương pháp (FR-63). |
| CR-13 | Danh sách ngoại lệ (allowlist) tên miền: `sec.gov`, `data.sec.gov`, `finance.yahoo.com`/`yfinance`, `stooq.com`, `microsoft.com`, `abc.xyz`. Crawler từ chối URL ngoài danh sách. |
| CR-14 | Sự kiện AI (`ai_event`) chỉ được nhập từ thông cáo chính thức hoặc 8-K/10-Q có URL; không nhập từ tin đồn. Mỗi sự kiện cần người nhập (`entered_by`) và người kiểm chéo (`reviewed_by`). |

### 3.8 Hypothesis Testing (F8) – Ưu tiên: Cao (BT1–BT3 ở MVP; BT4–BT5 giai đoạn 2)

| Mã | Yêu cầu |
|---|---|
| FR-48 | Kiểm định H0 cho BT1–BT5 ở α = 0,05 (cấu hình được). |
| FR-49 | Kiểm tra chuẩn (Shapiro–Wilk) trước; dùng t-test/Pearson khi phù hợp, Wilcoxon/Spearman khi không. |
| FR-50 | Hiển thị thống kê kiểm định, p-value, n, khoảng tin cậy 95%, kết luận "bác bỏ"/"không bác bỏ" H0 bằng tiếng Việt dễ hiểu. |
| FR-51 | Hiệu chỉnh Holm khi kiểm định nhiều độ trễ k. |
| FR-52 | Chỉ chạy trên dữ liệu đạt kiểm tra chất lượng (DR-04); quý bị loại phải được liệt kê cùng lý do. |
| FR-53 | Cảnh báo khi n < 30 rằng kết quả chỉ mang tính tham khảo. |
| FR-54 | Lưu kết quả cùng phiên bản dữ liệu và ngày chạy; giao diện chỉ hiển thị. |

### 3.9 Data Export (F9) – Ưu tiên: Trung bình

| Mã | Yêu cầu |
|---|---|
| FR-55 | Xuất bảng chỉ số, kết quả calculator, kết quả kiểm định ra CSV. |
| FR-56 | Nên xuất biểu đồ ra PNG. |
| FR-57 | Tệp xuất kèm nguồn, ngày cập nhật, phiên bản dữ liệu. |

### 3.10 Saved Scenarios (F10) – Ưu tiên: Trung bình

| Mã | Yêu cầu |
|---|---|
| FR-58 | Lưu kịch bản (cổ phiếu, vốn, ngày, kết quả) trong trình duyệt (localStorage, bọc try/catch), không gửi máy chủ. |
| FR-59 | So sánh song song từ 2 kịch bản theo giá trị cuối, ROI, lợi suất quy năm. |
| FR-60 | Đổi tên và xóa kịch bản. |

### 3.11 Methodology & Data Sources Page (F11) – Ưu tiên: Cao

| Mã | Yêu cầu |
|---|---|
| FR-61 | Liệt kê công thức mọi chỉ số và quy ước (quý lịch, giá điều chỉnh, số công bố lần đầu hay điều chỉnh). |
| FR-62 | Liệt kê nguồn, `source_url`, ngày cập nhật gần nhất. |
| FR-63 | Hiển thị phiên bản dữ liệu, kết quả kiểm tra chất lượng (số quý thiếu, tỷ lệ `verified`, kết quả `link_report`). |
| FR-64 | Giải thích giả thuyết, mức ý nghĩa, giới hạn diễn giải. |
| FR-65 | Mỗi con số trên các trang khác có nút "Xem nguồn" mở `source_url` ở tab mới (tương ứng CR-02). |

---

## 4. External Interface Requirements

### 4.1 User Interfaces

| Mã | Yêu cầu |
|---|---|
| UI-01 | 5 trang phân tích (Executive Overview, Investor Return, Company Financial Performance, AI Investment Analysis, Stock Decision Support) và 1 trang Phương pháp & Nguồn dữ liệu. |
| UI-02 | Thanh điều hướng cố định, hiển thị trạng thái đồng bộ (thời điểm và tuổi dữ liệu). |
| UI-03 | Toàn bộ nhãn tiếng Việt; thuật ngữ có tooltip. |
| UI-04 | Biểu đồ có tooltip, chú giải, trục ghi đơn vị; không truyền đạt thông tin chỉ bằng màu. |
| UI-05 | Responsive từ 360 px. |
| UI-06 | Số liệu minh họa có nhãn "minh họa", tách khỏi dữ liệu thật, không dùng trong kiểm định. |
| UI-07 | Trang AI Investment và Decision Support có cảnh báo cố định về tương quan, nhân quả, khuyến nghị. |
| UI-08 | **Animation:** chuyển trang mượt (fade/slide ≤ 300 ms); số trên thẻ KPI đếm tăng dần; đường biểu đồ vẽ dần khi vào màn hình; cột biểu đồ mọc lên. Dùng Framer Motion (hoặc tương đương). |
| UI-09 | Tôn trọng `prefers-reduced-motion`: tắt hoặc giảm animation khi người dùng yêu cầu. |
| UI-10 | **Tương tác biểu đồ:** crosshair đồng bộ, brush chọn khoảng thời gian, zoom/reset, bật tắt chuỗi qua chú giải, chuyển chế độ giá tuyệt đối/chuẩn hóa. |
| UI-11 | Bộ lọc toàn cục (công ty, benchmark, khoảng thời gian, quý) giữ trong URL query để chia sẻ và tải lại được. |
| UI-12 | Trang AI Investment có thanh trượt độ trễ k = 0..4; heatmap tương quan chuyển động mượt khi đổi k; mỗi ô hiển thị r, p đã hiệu chỉnh, n. |
| UI-13 | Bảng chỉ số sắp xếp, tìm kiếm, hiển thị thanh nhỏ (sparkline) theo quý; nút "Xem nguồn" từng dòng. |
| UI-14 | Chế độ sáng/tối, nhớ lựa chọn; đạt tương phản WCAG AA ở cả hai chế độ. |
| UI-15 | Trạng thái tải dùng skeleton; lỗi dữ liệu hiển thị thông báo và dữ liệu cũ nhất còn hợp lệ, không để trang trống. |
| UI-16 | Điểm hiệu năng Lighthouse (Performance) ≥ 85 trên di động ở trang chủ sau khi build sản xuất. |

### 4.2 Hardware Interfaces
Không có.

### 4.3 Software Interfaces

| Mã | Giao diện | Mục đích |
|---|---|---|
| SI-01 | SEC EDGAR (`data.sec.gov` JSON, `sec.gov/Archives`) | Hồ sơ, số liệu XBRL |
| SI-02 | `yfinance` | Giá, cổ tức, chia tách |
| SI-03 | Stooq CSV | Giá đối chiếu |
| SI-04 | Trang IR Microsoft, Alphabet | Đối chiếu thủ công |
| SI-05 | GitHub Actions, Secrets | Lập lịch, lưu khóa |
| SI-06 | SQLite, JSON, CSV | Lưu trữ và trao đổi |
| SI-07 | React + thư viện biểu đồ (Recharts hoặc ECharts) + Framer Motion | Dashboard |
| SI-08 | Vercel (Git Integration, Functions, Cron) | Triển khai, kiểm tra sức khỏe |
| SI-09 | GitHub REST API `workflow_dispatch` | Vercel Function kích hoạt lại pipeline |

### 4.4 Communications Interfaces

- HTTPS cho mọi truy cập.
- Frontend lấy JSON tĩnh cùng nguồn gốc bằng HTTP GET; chia nhỏ theo trang (NFR-04).
- Không có kênh thời gian thực.

---

## 5. Other Nonfunctional Requirements

### 5.1 Performance Requirements

| Mã | Yêu cầu |
|---|---|
| NFR-01 | Trang đầu hiển thị nội dung chính ≤ 3 giây trên băng thông rộng thông thường. |
| NFR-02 | Calculator trả kết quả ≤ 1 giây. |
| NFR-03 | Một lần chạy pipeline đầy đủ ≤ 30 phút (GitHub Actions); pipeline tăng dần (chỉ lấy phần mới) ≤ 10 phút. |
| NFR-04 | Tổng dữ liệu tải về cho một trang ≤ 5 MB (nén). |
| NFR-04a | Animation giữ ≥ 50 khung hình/giây trên thiết bị tầm trung; không chặn luồng chính > 50 ms. |

### 5.2 Safety Requirements

| Mã | Yêu cầu |
|---|---|
| NFR-05 | Mọi kết quả kèm tuyên bố: chỉ cung cấp thông tin phân tích, không phải tư vấn tài chính. |
| NFR-06 | Cảnh báo hiệu suất quá khứ không đảm bảo kết quả tương lai. |
| NFR-07 | Không hiển thị số liệu giả lập như dữ liệu thị trường thực. |

### 5.3 Security Requirements

| Mã | Yêu cầu |
|---|---|
| NFR-08 | Khóa API chỉ trong GitHub Secrets/Vercel Env; không có trong repository hay nhật ký. |
| NFR-09 | Không thu thập thông tin cá nhân; dữ liệu calculator chỉ xử lý trong trình duyệt. |
| NFR-10 | HTTPS toàn bộ. |
| NFR-11 | Thoát ký tự dữ liệu hiển thị (chống XSS); không dùng `dangerouslySetInnerHTML` với dữ liệu ngoài. |
| NFR-11a | Vercel Function `/api/health` và endpoint kích hoạt workflow bảo vệ bằng bí mật dùng chung (`CRON_SECRET`); token GitHub có quyền tối thiểu (chỉ `actions:write` trên repository này). |

### 5.4 Software Quality Attributes

| Thuộc tính | Yêu cầu |
|---|---|
| Độ chính xác | NFR-12: tính tay ≥ 5 mẫu (ROI, Revenue Growth, FCF, R&D Intensity, ROIC) khớp hệ thống (sai số ≤ 0,01). |
| Truy vết | NFR-13: mỗi giá trị truy được về `source_url`, kỳ báo cáo và `accession_number`. |
| Tái lập | NFR-14: cùng dữ liệu thô cho cùng kết quả (cố định seed, phiên bản thư viện trong `requirements.lock`). |
| Độ tin cậy | NFR-15: khi nguồn lỗi, giữ dữ liệu cũ, hiển thị trạng thái đồng bộ thất bại, không hiển thị rỗng. |
| Bảo trì | NFR-16: mã chia module theo ba lớp; công thức đặt một nơi (`pipeline/metrics/formulas.py`). |
| Khả năng sử dụng | NFR-17: người mới hoàn thành một giả lập ≤ 2 phút không cần hướng dẫn. |
| Truy cập | NFR-18: tương phản WCAG AA; điều hướng bằng bàn phím được. |
| Di động | NFR-19: chạy đúng trên trình duyệt ở mục 2.4. |
| Kiểm thử | NFR-20: độ phủ kiểm thử đơn vị ≥ 80% cho `pipeline/metrics` và `pipeline/stats`. |

---

## 6. Other Requirements

### 6.1 Data Requirements

**DR-01 – Quy tắc xử lý**

1. USD, triệu USD cho tài chính.
2. Tài chính theo quý; giá theo ngày.
3. Giá ngày → lợi suất quý lịch khi phân tích cùng báo cáo tài chính (FR-26).
4. Lưu `period_end` thực tế và quý lịch quy đổi (MSFT năm tài chính tháng 6; Alphabet tháng 12).
5. Phân biệt `Reported`, `Proxy`, `Estimated`.
6. Không trộn dữ liệu quý và năm khi chưa quy đổi.
7. Dùng `adjusted_close` hoặc chuỗi Total Return.

**DR-02 – Từ điển dữ liệu** (bổ sung trường so với v1.1 được in đậm)

`stock_price`: ticker, trade_date, open, high, low, close, adjusted_close, volume, dividend, split_factor, **price_source, source_url, fetched_at**.

`investor_portfolio` (đầu vào giả lập, chỉ ở trình duyệt): portfolio_id, ticker, initial_investment, purchase_date, purchase_price, shares, evaluation_date, evaluation_price, dividends_received, transaction_fees, tax_paid.

`company_financials`: company, period_end, fiscal_year, fiscal_quarter, **calendar_quarter**, revenue, operating_income, net_income, rd_expense, capex, cash_from_operations, total_assets, total_equity, total_debt, income_tax_expense, currency, source_url, **accession_number, form, xbrl_tag_map_version, derived, response_sha256, fetched_at**, filing_date, is_restated, verified, quality_flag (ok/low/missing).

`segment_financials`: company, period_end, segment_name, segment_revenue, segment_operating_income, segment_operating_margin, source_url, **accession_number**.

`ai_investment_indicators`: company, period_end, rd_expense, capex, cloud_revenue, ai_event, ai_indicator_type (Reported/Proxy/Estimated), ai_indicator_value, source_url, **entered_by, reviewed_by**.

`benchmark`: benchmark_ticker, date, adjusted_close, return, **price_source, source_url**.

`sync_log` (mới): run_id, started_at, finished_at, source, status, records_added, error_message.

`link_report` (mới): url, checked_at, http_status, matched_accession, matched_value, result.

`test_results` (mới): bt_code, snapshot_version, run_date, test_name, statistic, p_value, p_adjusted, n, ci_low, ci_high, decision, excluded_quarters.

**DR-03 – Nguồn dữ liệu**

| Nhóm | Nguồn | Cách dùng |
|---|---|---|
| Hồ sơ và số liệu tài chính | SEC EDGAR (`data.sec.gov`, `sec.gov/Archives`) | Crawler chính |
| Báo cáo quý | Microsoft IR, Alphabet IR | Đối chiếu thủ công |
| Giá, cổ tức | Yahoo Finance (`yfinance`) | Crawler chính |
| Giá đối chiếu | Stooq | Đối chiếu ≥ 30 ngày ngẫu nhiên mỗi mã |
| Benchmark | SPY, QQQ qua cùng nguồn giá | Lợi suất so sánh |

**DR-04 – Độ chính xác (phục vụ kiểm định)**

1. Mọi số liệu trong phân tích/kiểm định là số thật, có `source_url`; số minh họa không nằm trong tập kiểm định.
2. Giá trị cốt lõi (revenue, operating_income, net_income, rd_expense, capex, cash_from_operations) phải `verified` qua CR-10 và đối chiếu thủ công mẫu với hồ sơ gốc.
3. Giá cổ phiếu đối chiếu ≥ 2 nguồn trên ≥ 30 ngày giao dịch ngẫu nhiên/mã; sai lệch sau điều chỉnh ≤ 0,1%.
4. Kiểm tra logic: `FCF = CFO − CapEx`; đơn vị nhất quán; không doanh thu hoặc R&D âm bất thường; tổng 4 quý ≈ số năm 10-K (sai lệch làm tròn ≤ 0,5%).
5. Phân biệt công bố lần đầu và điều chỉnh (`is_restated`); kiểm định dùng số công bố **lần đầu** (mục C.2).
6. Mặc định chỉ dùng `Reported`; `Proxy`/`Estimated` chỉ khi gắn nhãn rõ.
7. Đóng băng snapshot có phiên bản (`vYYYYMMDD.N`) và ngày.
8. Quý thiếu hoặc `quality_flag ≠ ok` bị loại và ghi rõ (FR-52).

### 6.2 Legal and Ethical Requirements

- Tôn trọng điều khoản nguồn dữ liệu; ghi nguồn.
- Không trình bày như tư vấn đầu tư.
- `yfinance` là thư viện không chính thức; dùng cho mục đích học thuật và nêu rõ trên trang Phương pháp.

### 6.3 Testing Requirements

- Kiểm thử đơn vị công thức; tính tay ≥ 5 chỉ số (NFR-12).
- Tình huống: quý thiếu, API lỗi, ngày không giao dịch, chia tách cổ phiếu, Q4 suy ra, MSFT quy đổi quý.
- Kiểm thử hợp đồng dữ liệu: JSON xuất ra khớp schema (JSON Schema/Zod).
- Kiểm thử giao diện (Playwright): điều hướng, calculator, bộ lọc, nút "Xem nguồn".
- Kiểm tra hiệu năng Lighthouse (UI-16), tải trang (NFR-01).

### 6.4 Deployment Requirements

| Mã | Yêu cầu |
|---|---|
| DP-01 | Repository GitHub duy nhất (monorepo): `pipeline/`, `web/`, `api/`, `data/`, `config/`, `docs/`. |
| DP-02 | Vercel kết nối repository bằng Git Integration; Root Directory là `web/` hoặc dùng `vercel.json`; build `npm run build`; mỗi commit dữ liệu từ bot tạo bản triển khai mới. |
| DP-03 | `.github/workflows/collect.yml` (cron + `workflow_dispatch`): cài phụ thuộc có cache, chạy `python -m pipeline.run --mode incremental`, commit thay đổi trong `data/` và `web/public/data/` bằng tài khoản bot; dùng `concurrency` để không chạy chồng. |
| DP-04 | `.github/workflows/ci.yml`: lint, kiểm thử Python và web, kiểm tra schema JSON, chạy `verify_links` trên mẫu, build web. |
| DP-05 | Vercel Cron cấu hình trong `vercel.json` gọi `/api/health` hằng ngày; Function đọc `manifest.json`, nếu `now − generated_at` vượt ngưỡng (`config/thresholds.yaml`) thì gọi `workflow_dispatch`. Người thực hiện phải đọc giới hạn Cron/Function của gói Vercel đang dùng trước khi chọn tần suất. |
| DP-06 | Biến môi trường: `SEC_USER_AGENT`, `GITHUB_TOKEN_DISPATCH`, `CRON_SECRET`, `ALPHAVANTAGE_KEY` (nếu dùng); liệt kê trong `.env.example` không chứa giá trị thật. |
| DP-07 | Quy trình rollback: dùng Vercel "Promote previous deployment" hoặc `git revert` commit dữ liệu lỗi; snapshot cũ được giữ ≥ 10 bản. |

---

## Appendix A: Glossary

| Thuật ngữ | Định nghĩa |
|---|---|
| AICOR | AI & Stock Investment Intelligence |
| Adjusted Close | Giá đóng cửa đã điều chỉnh chia tách và cổ tức |
| Accession number | Mã định danh duy nhất của một hồ sơ nộp SEC |
| Benchmark | Chỉ số tham chiếu (SPY, QQQ) |
| CapEx | Chi tiêu vốn |
| CFO | Dòng tiền từ hoạt động kinh doanh |
| FCF | CFO − CapEx |
| HAC | Sai số chuẩn vững với tự tương quan và phương sai thay đổi (Newey–West) |
| Holm | Hiệu chỉnh đa kiểm định từng bước của Holm |
| NOPAT | Lợi nhuận hoạt động sau thuế |
| ROE, ROI, ROIC | Lợi nhuận trên vốn chủ, trên vốn đầu tư ban đầu, trên vốn đầu tư |
| R&D | Nghiên cứu và phát triển |
| XBRL | Định dạng dữ liệu tài chính có thẻ trong hồ sơ SEC |
| YoY | So với cùng kỳ năm trước (cách 4 quý) |
| Reported/Proxy/Estimated | Số công bố / chỉ số đại diện / số ước tính |
| Vibe coding | Lập trình với trợ lý AI theo từng bước, có kiểm tra tiêu chí chấp nhận |
| DoD | Definition of Done, tiêu chí hoàn thành |

## Appendix B: Analysis Models

**B.1 Mô hình tổng thể**

```
INPUT: giá, cổ tức, hồ sơ SEC (XBRL), R&D, CapEx, phân khúc Cloud
   |
   +--> Nhánh A: Investor Return      -> giá trị danh mục, ROI, vượt benchmark
   +--> Nhánh B: Business Performance -> tăng trưởng, biên, FCF, ROIC
   +--> Lớp kết nối: AI & Stock Analysis -> tương quan trễ 0..4 quý, kiểm định
            |
OUTPUT: Dashboard tương tác & Decision Support
```

**B.2 Luồng dữ liệu**

```
SEC / Yahoo / Stooq -> crawler -> CSV append-only + hash + source_url
   -> verify_links + reconcile -> làm sạch, quy đổi quý
   -> metrics + stats -> SQLite + JSON (snapshot vYYYYMMDD.N)
   -> git commit -> Vercel build -> React dashboard
```

**B.3 Công thức**

```
Shares              = (I0 − Fees) / P0
Vt                  = Shares × Pt + Dt
Profit              = Vt − I0
ROI                 = Profit / I0 × 100%
Annualized Return   = (1 + ROI)^(365/Days) − 1
Excess Return       = Stock Return − Benchmark Return
Revenue Growth YoY  = (Rev_t − Rev_t−4) / Rev_t−4
Operating Margin    = Operating Income / Revenue
R&D Intensity       = R&D / Revenue
CapEx Intensity     = CapEx / Revenue
FCF                 = CFO − CapEx
FCF Margin          = FCF / Revenue
NOPAT               = Operating Income × (1 − Tax Rate)
Tax Rate            = Income Tax Expense / Pre-tax Income (giới hạn trong [0, 0.5])
ROIC                = NOPAT / Average Invested Capital
Invested Capital    = Total Debt + Total Equity − Cash & Marketable Securities
ROE                 = Net Income / Average Equity
RD_Growth_t         = (RD_t − RD_t−4) / RD_t−4
StockReturn_t       = (AdjP_t − AdjP_t−1) / AdjP_t−1   (mốc cuối quý lịch)
Corr(X_t, Y_t+k),   k = 0..4
```

(Tax Rate và Invested Capital ở dạng đã chốt tại C.2; nếu nhóm đổi, cập nhật tại `formulas.py` và Phụ lục này cùng lúc.)

## Appendix C: Issues List và quyết định đã chốt

### C.1 Vấn đề còn mở

| # | Vấn đề | Trạng thái |
|---|---|---|
| 4 | Số quan sát theo quý ít (16–19) | Ghi rõ giới hạn; cảnh báo n < 30 |
| 5 | Cloud MSFT và Google Cloud không tương đương | Ghi chú trên giao diện |
| 7 | Khả thi giai đoạn 2 trong 9 tuần | Đánh giá lại ở mốc M5 |
| 9 | Mục 1.8 | Đề xuất đã có, chờ nhóm duyệt |
| 11 | Kiểm định thiếu sức mạnh với n nhỏ | Ghi rõ giới hạn |

### C.2 Quyết định đã chốt (có thể đổi nếu nhóm không đồng ý, nhưng phải cập nhật đồng bộ)

| # | Quyết định | Lý do |
|---|---|---|
| 1 | Mã chính của Alphabet: **GOOGL** (Class A); GOOG chỉ đối chiếu | Thanh khoản cao, thường dùng |
| 2 | Invested Capital = Total Debt + Total Equity − Cash & Marketable Securities, áp dụng như nhau cho hai công ty | Nhất quán, tính được từ XBRL |
| 3 | Quy đổi quý: dùng `period_end` làm gốc; quý lịch = quý chứa `period_end` (MSFT Q4 FY kết thúc 30/6 ↔ Q2 lịch) | Tránh lệch kỳ |
| 6 | Bỏ điểm E = Out − In khỏi sản phẩm | Không có cơ sở tài chính; giữ giải thích trong tài liệu lịch sử |
| 8 | Không dùng nguồn "chi tiêu AI ước tính" bên thứ ba trong MVP; chỉ `Reported` và `Proxy` (R&D, CapEx, Cloud) | Tránh số khó kiểm chứng |
| 10 | Kiểm định dùng số công bố lần đầu (`is_restated=false`) | Phản ánh thông tin tại thời điểm công bố |

## Appendix D: Lịch thực hiện (9 tuần)

| Giai đoạn | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | T9 |
|---|---|---|---|---|---|---|---|---|---|
| 1. Đặc tả và chuẩn bị (M0) | ■ | ■ | | | | | | | |
| 2. Crawler và pipeline (M1–M3) | | ■ | ■ | ■ | | | | | |
| 3. Kiểm chứng dữ liệu (M3) | | | ■ | ■ | ■ | | | | |
| 4. Chỉ số và kiểm định (M4) | | | | | ■ | ■ | | | |
| 5. Web, animation, triển khai (M5–M7) | | | | | | ■ | ■ | ■ | |
| 6. Kiểm thử, báo cáo (M8) | | | | | | | | ■ | ■ |

| Giai đoạn | Công việc | Bàn giao | Phụ trách |
|---|---|---|---|
| 1 (T1–2) | Chốt phạm vi, giả thuyết, công thức; tạo repo; schema; wireframe | SRS, repo, schema, wireframe | Cả nhóm |
| 2 (T2–4) | Crawler EDGAR, yfinance, Stooq; workflow; `verify_links` | Dữ liệu thô tự cập nhật | Thành viên 1 (Dương Kỳ Tiến) |
| 3 (T3–5) | Đối chiếu số liệu, mã hóa sự kiện AI | Bảng đã `verified` | Thành viên 2 (Tiền Tấn Tài); TV1 kiểm chéo |
| 4 (T5–6) | Chỉ số, tương quan, kiểm định | `metrics.json`, `tests.json` | Thành viên 2; TV1 gắn workflow |
| 5 (T6–8) | Dashboard, calculator, animation, Vercel | Web chạy trên Vercel | Thành viên 3 (Trương Thanh Tuấn); TV1 xuất JSON |
| 6 (T8–9) | Kiểm thử, SRS, slide, thuyết trình | Bản nộp cuối | Cả nhóm |

Các giai đoạn gối đầu nhau. Lịch gắn với mốc đề cương (Phụ lục H): GL1 đề xuất, GL2 thiết kế hệ thống, GL3 kiểm tra tiến độ, GFP cuối kỳ.

---

## Appendix E: Lộ trình Vibe Code

**Quy tắc làm việc với trợ lý AI (áp dụng mọi milestone)**

1. Mỗi milestone là một nhánh Git và một Pull Request; chỉ gộp khi toàn bộ DoD đạt.
2. Đưa SPEC này (hoặc phần liên quan) vào ngữ cảnh; yêu cầu trợ lý trích dẫn mã yêu cầu (FR/CR/DR) trong commit.
3. Cấm trợ lý tự điền số liệu tài chính. Nếu thiếu số, trợ lý phải để trống và gắn cờ (CR-07).
4. Viết kiểm thử trước hoặc cùng lúc với mã; chạy kiểm thử sau mỗi thay đổi.
5. Không chuyển milestone khi DoD chưa đạt; nếu mơ hồ, trợ lý hỏi lại thay vì giả định.

**Bảng milestone**

| M | Mục tiêu | Yêu cầu liên quan | DoD (kiểm chứng được) |
|---|---|---|---|
| M0 | Khởi tạo monorepo, lint, CI trống, schema JSON, `.env.example`, wireframe | DP-01, DP-06 | `ci.yml` xanh; cấu trúc theo Phụ lục F; schema đạt `check-jsonschema` |
| M1 | Crawler SEC: submissions + companyfacts cho MSFT, GOOGL; cache; rate limiter; `concept_map.yaml` | CR-01..04, CR-07, CR-08, FR-41, FR-42 | Chạy cục bộ cho ra `data/raw/company_financials.csv` ≥ 12 quý mỗi công ty; mọi dòng có `accession_number`, `source_url`, `response_sha256`; kiểm thử với phản hồi giả (fixture) |
| M2 | Crawler giá: yfinance + Stooq; đối chiếu giá | CR-05, FR-40, DR-04.3 | Bảng `stock_price` và `benchmark`; báo cáo đối chiếu ≥ 30 ngày/mã, sai lệch ≤ 0,1% hoặc ghi cờ |
| M3 | `verify_links`, `reconcile`, `quality_flag`, `sync_log`; mã hóa sự kiện AI | CR-10..14, FR-43..45, DR-04 | `link_report.json` sinh ra; CI thất bại khi một giá trị cốt lõi có liên kết hỏng; đối chiếu thủ công ≥ 5 chỉ số khớp |
| M4 | `metrics` và `stats`: chỉ số, quý lịch, tương quan, kiểm định BT1–BT5, Holm, ADF | FR-16..18, 24..27, 30a, 46, 48..54 | Kiểm thử đơn vị đạt; ví dụ calculator 1.000/100/130/20 ra 320 và 32%; `tests.json` khớp schema; chạy lại cho kết quả giống hệt |
| M5 | React app: layout, router, calculator, trang Overview, Investor, Financial; đọc JSON | FR-01..15, 37..39, UI-01..07 | Playwright đạt; NFR-02; mọi số có nút "Xem nguồn" mở đúng `source_url` |
| M6 | Animation và tương tác: KPI đếm số, chart vẽ dần, crosshair, brush, URL filter, heatmap độ trễ, dark mode, reduced motion | UI-08..UI-15, FR-28, 29 | Kiểm tra thủ công theo checklist; Lighthouse ≥ 85 (UI-16); `prefers-reduced-motion` tắt animation |
| M7 | Decision Support, Methodology, Export, Scenarios; Vercel deploy + `/api/health` + Cron + workflow_dispatch | FR-31..36, 55..65, DP-02..07, NFR-11a | Triển khai Vercel thành công từ Git; commit dữ liệu của bot kích hoạt build; Cron gọi `/api/health` thành công; thử cho dữ liệu quá hạn thì workflow được kích hoạt |
| M8 | Kiểm thử cuối, hiệu năng, tài liệu, slide, quay video | NFR-01, 12, 20; mục 6.3 | Toàn bộ DoD trước đó giữ nguyên; README đầy đủ; checklist truy vết (Phụ lục G) không còn ô trống |

**Prompt mẫu cho từng milestone** (dán kèm SPEC)

- **M1:** "Triển khai milestone M1 theo SPEC. Viết `pipeline/crawlers/sec.py` lấy submissions và companyfacts của CIK 789019 và 1652044 bằng `requests` với User-Agent từ biến môi trường `SEC_USER_AGENT`, giới hạn ≤ 5 yêu cầu/giây, cache theo hash. Ánh xạ thẻ XBRL qua `config/concept_map.yaml`. Không viết cứng bất kỳ con số tài chính nào. Với kỳ thiếu thẻ, ghi `quality_flag=missing`. Viết kiểm thử dùng fixture JSON nhỏ nằm trong `tests/fixtures/`."
- **M2:** "Triển khai M2: crawler giá bằng yfinance cho MSFT, GOOGL, SPY, QQQ và Stooq CSV để đối chiếu. Sinh báo cáo lệch giá trên 30 ngày ngẫu nhiên (seed cố định) mỗi mã. Nếu yfinance lỗi, chuyển nguồn và ghi `price_source`."
- **M3:** "Triển khai `verify_links`: mỗi `source_url` duy nhất được GET, kiểm mã 200, kiểm `accession_number` trong nội dung, và đọc lại giá trị XBRL để so khớp tuyệt đối. Ghi `link_report.json`. Thất bại thì hạ `verified=false`. Thêm allowlist miền theo CR-13."
- **M4:** "Triển khai `metrics` theo Phụ lục B.3 và `stats` theo mục 3.8 dùng `scipy` và `statsmodels` (Shapiro–Wilk, Pearson/Spearman, Wilcoxon, OLS HAC, ADF, Holm). Xuất `tests.json` kèm `snapshot_version`. Viết kiểm thử so khớp tính tay."
- **M5–M6:** "Dựng React + Vite + TypeScript + Tailwind + Recharts + Framer Motion theo UI-01..UI-16. Mọi dữ liệu đọc từ `/data/*.json`, kiểm tra bằng Zod theo schema. Không tự tính chỉ số ngoài calculator. Mỗi con số có nút 'Xem nguồn'. Tôn trọng `prefers-reduced-motion`."
- **M7:** "Cấu hình `vercel.json` (cron gọi `/api/health`), viết `api/health.ts` đọc `manifest.json` và gọi GitHub `workflow_dispatch` khi dữ liệu quá hạn, bảo vệ bằng `CRON_SECRET`. Viết `collect.yml` và `ci.yml` theo DP-03, DP-04."

**Định nghĩa "không bịa dữ liệu" khi nghiệm thu:** chọn ngẫu nhiên 10 con số hiển thị trên web; với mỗi số, bấm "Xem nguồn", mở hồ sơ SEC hoặc trang giá, xác nhận giá trị trùng. Chỉ nghiệm thu khi 10/10 trùng.

## Appendix F: Cấu trúc repository và quy ước

```
aicor/
├─ .github/workflows/{ci.yml, collect.yml, verify_weekly.yml}
├─ api/health.ts                      # Vercel Function
├─ config/{concept_map.yaml, thresholds.yaml, allowlist.yaml}
├─ data/{raw/, raw/_cache/, verified/, db/aicor.sqlite, snapshots/}
├─ docs/{SPEC.md, REVIEW.md, slides/}
├─ pipeline/
│  ├─ crawlers/{sec.py, prices.py}
│  ├─ verify/{links.py, reconcile.py}
│  ├─ metrics/formulas.py
│  ├─ stats/tests.py
│  └─ run.py                          # CLI: --mode full|incremental
├─ tests/{fixtures/, test_*.py}
├─ web/
│  ├─ public/data/*.json              # xuất từ pipeline
│  ├─ src/{pages/, components/, lib/, schemas/}
│  └─ vite.config.ts
├─ vercel.json
├─ requirements.lock
└─ README.md
```

Quy ước: Python theo `ruff` và `pytest`; TypeScript chế độ `strict`, `eslint`, `vitest`, `playwright`; commit theo `type(scope): nội dung [FR-xx]`; mọi JSON xuất ra có trường `schema_version`, `snapshot_version`, `generated_at`.

## Appendix G: Ma trận truy vết

| Bài toán | Yêu cầu chính | Kiểm thử/nghiệm thu |
|---|---|---|
| BT1 | FR-01..15, 48 | Unit test calculator; `tests.json` BT1; Playwright calculator |
| BT2 | FR-16..23, 48 | Tính tay Revenue Growth; `tests.json` BT2 |
| BT3 | FR-17, 48 | Hồi quy xu hướng kiểm tra bằng dữ liệu cố định trong fixture |
| BT4 | FR-24, 25, 27, 30a, 48..54 | Tương quan so khớp thư viện tham chiếu; kiểm tra Holm |
| BT5 | FR-26, 48..54 | Như BT4; kiểm tra mốc giá cuối quý lịch |
| Dữ liệu | CR-01..14, DR-04 | `link_report.json`; mẫu 10/10 số trùng nguồn |
| Triển khai | DP-01..07 | Vercel build tự động; Cron gọi thành công |
| Giao diện | UI-01..16 | Playwright; Lighthouse; checklist animation |
