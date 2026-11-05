# KẾ HOẠCH GIAI ĐOẠN DỮ LIỆU — RAW & PREPROCESS

**Dự án:** AICOR — AI & Stock Investment Intelligence  
**Nhóm:** 7 (3 thành viên)  
**Ngày lập kế hoạch:** 2026-11-04  
**Trạng thái:** Draft để nhóm chốt trước khi bắt đầu M1  
**Phạm vi:** M1–M3 (thu thập, kiểm chứng, tiền xử lý) + bàn giao dữ liệu cho M4 (metrics/stats)  
**Tài liệu gốc:** `SPEC.md` — phiên bản 2.0

---

## 0. TÓM TẮT ĐIỀU HÀNH

### 0.1 Mục tiêu giai đoạn

Tạo ra một tập dữ liệu **có thể kiểm chứng từng ô** cho MSFT và GOOGL, từ Q1/2022 đến quý gần nhất có hồ sơ SEC hợp lệ, đủ để:

1. Tính toán hai nhánh: **Investor Return** (giá, cổ tức, benchmark) và **Business Performance** (doanh thu, lợi nhuận, dòng tiền, R&D, CapEx, ROE/ROIC).
2. Chạy kiểm định **BT1–BT5** trên số liệu thật.
3. Nuôi 6 trang dashboard: Executive Overview, Investor Return, Company Financial Performance, AI Investment Analysis, Stock Decision Support, Methodology & Data Sources.
4. Mỗi con số hiển thị có `source_url` mở được, có `accession_number` và `response_sha256`; không có số liệu tự điền.

### 0.2 Các phát hiện phải xử lý ngay

| # | Phát hiện | Ảnh hưởng | Quyết định đề xuất |
|---|---|---|---|
| 1 | **Stooq CSV không dùng được cho crawler server-side.** Endpoint `https://stooq.com/q/d/l/?s=msft.us&i=d` trả HTTP 200 nhưng chỉ là trang thử thách JavaScript, 796 byte, `Content-Type: text/html`, không có CSV. | Không thể dùng Stooq làm nguồn giá đối chiếu như CR-05/DR-04.3 dự kiến. | Thay bằng **Nasdaq historical API** cho giá đóng cửa chưa điều chỉnh; **Alpha Vantage** chỉ dùng cho adjusted close khi có API key và đã kiểm chứng. **Lưu ý:** `api.nasdaq.com` và `alphavantage.co` hiện **ngoài allowlist CR-13**; phải cập nhật `config/allowlist.yaml` và được nhóm duyệt trước khi crawler dùng. Nếu không, ghi rõ DR-04.3 chưa đạt. |
| 2 | **GOOGL đổi thẻ XBRL doanh thu.** Từ Q1/2022–Q1/2025 dùng `RevenueFromContractWithCustomerExcludingAssessedTax`; từ Q2/2025 dùng `Revenues`. | Nếu concept map chỉ khai báo một thẻ, chuỗi doanh thu bị đứt từ 2025-Q2. | `concept_map.yaml` phải hỗ trợ **tag priority theo từng kỳ**, không chỉ một thẻ cố định. Pipeline phải phát hiện tag switch và ghi log. |
| 3 | **MSFT đổi cấu trúc phân khúc từ Q3/2026.** 10-Q Q1 FY2027 dùng `AgentsAndInfraMember` và `DevicesAndConsumerMember`; các kỳ trước dùng `IntelligentCloudMember`, `ProductivityAndBusinessProcessesMember`, `MorePersonalComputingMember`. | FR-21 ("Intelligent Cloud") không còn dữ liệu cho quý mới nhất; không được tự ánh xạ tên cũ sang tên mới. | Thêm trường `segment_scheme`, đánh dấu `comparable=false` tại điểm gãy; dashboard hiển thị ghi chú cấu trúc thay đổi. Cần cập nhật SPEC FR-21 hoặc chấp nhận chỉ hiển thị lịch sử. |
| 4 | **GOOGL lệch cơ sở cổ phiếu trước/sau split 20:1.** Q1/2022 công bố EPS pha loãng 24,62 USD/cổ phiếu (pre-split); từ 2022-07-18 giao dịch post-split, Q2/2022 công bố 1,21 USD/cổ phiếu. Nếu trộn trực tiếp, Q4 = FY − Q1..Q3 và trailing EPS/P/E bị sai. | Q4/2022 EPS âm giả tạo (−22,33) và P/E trailing sai. | Chỉ điều chỉnh các kỳ kết thúc **trước 2022-06-30** (Q1/2022) với hệ số 20; lưu `reported_value=24,62`, `split_adjustment=20`, `quality_flag=low`; Q4 dùng Q1 đã điều chỉnh. Q2/2022 giữ nguyên vì đã post-split. |

### 0.3 Nguyên tắc bất biến

1. **Không bịa số.** Không có hằng số tài chính viết cứng trong pipeline; không dùng LLM để sinh/điền số (CR-07).
2. **Không suy diễn khi thiếu.** Thiếu thẻ → `missing`, không nội suy, không thay bằng 0.
3. **HTTP 200 chưa đủ.** Phải kiểm tra `Content-Type`, nội dung, tiêu đề trang, `accession_number`, giá trị XBRL và tính hợp lệ của dữ liệu.
4. **Số công bố lần đầu.** Kiểm định dùng `is_restated=false` (C.2 #10); bản điều chỉnh chỉ lưu để audit.
5. **Mọi ô có nguồn.** `source_url` (người dùng bấm được) + `evidence_url` (máy kiểm tra) + `response_sha256`.
6. **Tái lập.** Cùng input → cùng output; `snapshot_version` dạng `vYYYYMMDD.N`; seed cố định cho lấy mẫu đối chiếu.

### 0.4 Năm việc làm ngay (trước khi code crawler)

1. **Chốt allowlist CR-13 (D1/D4):** có thêm `api.nasdaq.com`, `alphavantage.co`, `blog.google` hay không. Đây là việc chặn T2.2/T2.6; không chốt thì mặc định chỉ dùng yfinance và ghi DR-04.3 chưa đạt.
2. **Chốt D2/D3/D5:** cách hiển thị segment MSFT sau điểm gãy, định nghĩa cash cho ROIC, và P/E–EPS thuộc MVP hay phase 2.
3. **Tạo 4 file config:** `concept_map.yaml` (có tag switch GOOGL), `segment_map.yaml` (2 scheme MSFT), `source_registry.yaml`, `allowlist.yaml`.
4. **Dựng SEC client + crawler đầu tiên:** submissions → filings, companyfacts → facts; chạy bằng fixture trước, rồi mới gọi mạng thật.
5. **Dựng `verify_links` với 3 negative test bắt buộc:** Stooq → `blocked`, Microsoft Source 404 → `broken`, Microsoft IR "Default" → `soft404`; sau đó mới mở rộng sang price/segment.

---

## 1. ĐỌC SPEC: 5W VÀ PHẠM VI DỮ LIỆU

### 1.1 Tóm tắt 5W

| Câu hỏi | Trả lời | Hệ quả cho dữ liệu |
|---|---|---|
| **Who** | Nhóm 7 (3 thành viên: Dương Kỳ Tiến, Tiền Tấn Tài, Trương Thanh Tuấn). Người dùng: nhà đầu tư cá nhân, sinh viên, giảng viên, nhà báo công nghệ; quản trị viên là nhóm phát triển. | Ưu tiên giải thích thuật ngữ, nút "Xem nguồn", cảnh báo n nhỏ; dashboard không được khuyến nghị mua/bán. |
| **What** | Ứng dụng web phân tích hiệu quả đầu tư cổ phiếu và hiệu quả kinh doanh của Microsoft (MSFT) và Alphabet (GOOGL), kèm lớp liên hệ với đầu tư AI. | Dữ liệu phải có cả giá/cổ tức/benchmark và báo cáo tài chính/XBRL; không trộn hai nhánh. |
| **Where** | Trình duyệt; frontend + dữ liệu tĩnh trên Vercel; thu thập trên GitHub Actions. Đối tượng: MSFT, GOOGL niêm yết tại Mỹ; benchmark SPY, QQQ. | Raw và preprocess chạy trên Ubuntu runner; output JSON tĩnh; không có server chạy liên tục. |
| **When** | 9 tuần (Phụ lục D). Dữ liệu quý từ Q1/2022 đến quý mới nhất có 10-Q/10-K. Tại ngày kiểm tra 2026-11-04, quý mới nhất là **2026-Q3** (period_end 2026-09-30). | Tập phân tích: 19 quý lịch (2022-Q1 → 2026-Q3). Raw cần lấy sớm hơn để tính Q4, trailing EPS và ROI 5 năm. |
| **Why** | Nhà đầu tư thường chỉ xem giá hoặc báo cáo tài chính riêng lẻ. AICOR đặt hai góc nhìn cạnh nhau, mỗi con số mở được về hồ sơ gốc. | Chất lượng nguồn và khả năng truy vết là yêu cầu chức năng, không phải "phụ lục". |

### 1.2 Bài toán con và dữ liệu tối thiểu

| Mã | Câu hỏi | Dữ liệu tối thiểu | Phép kiểm định (M4) | Dashboard |
|---|---|---|---|---|
| **BT1** | Đầu tư MSFT/GOOGL lời bao nhiêu, có vượt benchmark không? | Giá daily, cổ tức, adjusted close, SPY/QQQ; lợi suất tháng | One-sample t hoặc Wilcoxon signed-rank trên excess return tháng | Investor Return; Executive KPI |
| **BT2** | Doanh thu, lợi nhuận, dòng tiền biến động ra sao; công ty nào tăng tốt hơn? | Revenue, net income, CFO theo quý lịch; YoY | Paired t / Wilcoxon trên các quý cùng kỳ | Company Financial Performance; Executive |
| **BT3** | R&D và CapEx thay đổi thế nào? | R&D, CapEx, revenue; R&D Intensity, CapEx Intensity | OLS trend + HAC (Newey–West) | Financial; AI Analysis |
| **BT4** | R&D/CapEx tăng có đi cùng kết quả kinh doanh quý sau không? | RD_Growth, CapEx_Growth, RevenueGrowth, FCFGrowth, OperatingMargin; lag 0–4 | Pearson/Spearman + Holm + ADF | AI Investment Analysis |
| **BT5** | Kết quả kinh doanh có liên hệ với hiệu suất cổ phiếu không? | RevenueGrowth, StockReturn quý; lag 0–4 | Như BT4 | AI Analysis; Investor |

**Cảnh báo n nhỏ:** 19 quý lịch; sau YoY còn 15 quan sát; với lag 4 còn 11. BT4/BT5 **không đủ n ≥ 30**. Dashboard phải hiển thị `n` và nhãn "chỉ mang tính tham khảo" (FR-27, FR-53), không được che giấu.

### 1.3 Chức năng dashboard liên quan

| Trang | Chức năng | Dữ liệu chính |
|---|---|---|
| Executive Overview | KPI Stock Return + Revenue Growth, giá chuẩn hóa, so sánh kinh doanh, tuổi dữ liệu (FR-37..39) | prices, company_financials, manifest |
| Investor Return | Calculator, biểu đồ giá, benchmark, ROI 1/3/5 năm, excess return (FR-01..15) | prices, dividends, benchmark |
| Company Financial Performance | 6 chỉ số cốt lõi, FCF, ROIC/ROE, Cloud segment (FR-16..23) | company_financials, segment_financials |
| AI Investment Analysis | RD/CapEx growth, heatmap lag 0–4, n, ADF, timeline sự kiện, nhãn Reported/Proxy (FR-24..30a) | company_financials, segments, ai_events, tests |
| Stock Decision Support | Bảng so sánh, volatility, max drawdown, trạng thái, cảnh báo (FR-31..36) | prices, financials, thresholds |
| Methodology & Data Sources | Công thức, nguồn, link report, quality report, snapshot, giới hạn (FR-61..65) | manifest, link_report, quality_report |
| Calculator/Scenarios/Export | Lưu kịch bản localStorage, xuất CSV/PNG (FR-55..60) | prices + dữ liệu trình duyệt |

### 1.4 Ràng buộc dữ liệu bắt buộc

- **DR-01:** USD, triệu USD cho tài chính; quý lịch; adjusted close; không trộn quý/năm.
- **DR-04:** số thật có `source_url`; core metrics phải `verified`; giá đối chiếu ≥ 2 nguồn trên ≥ 30 ngày/mã, sai lệch ≤ 0,1%; Q4 derive phải kiểm tra; snapshot có phiên bản.
- **CR-02:** mỗi giá trị tài chính lưu `accession_number`, `form`, `filing_date`, `period_end`, `xbrl_tag`, `unit`, `source_url`, `fetched_at`, `response_sha256`.
- **CR-07/CR-08:** không hardcode số; cache phản hồi gốc theo SHA-256.
- **CR-10/CR-11:** `verify_links` kiểm tra HTTP + accession + giá trị; ghi `link_report.json`; CI fail nếu core link hỏng.
- **CR-13:** allowlist domain: `sec.gov`, `data.sec.gov`, `finance.yahoo.com`/`yfinance`, `stooq.com`, `microsoft.com`, `abc.xyz`.
- **CR-14:** `ai_event` chỉ từ thông cáo chính thức/8-K/10-Q có URL; có `entered_by`, `reviewed_by`.

---

## 2. KẾT QUẢ KIỂM CHỨNG NGUỒN — 2026-11-04

> Bằng chứng chi tiết: `docs/evidence/source_verification_2026-11-04.json`.  
> Phương pháp: HTTP GET với `User-Agent` khai báo; SEC giữ ≤ 5 yêu cầu/giây; kiểm tra status, `Content-Type`, kích thước, nội dung, tiêu đề, giá trị/accession; không dùng LLM.

### 2.1 Nguồn ĐẠT về dữ liệu (một số còn chờ allowlist)

| ID | Nguồn / endpoint | Kết quả kiểm tra | Kết luận |
|---|---|---|---|
| S1 | `https://data.sec.gov/submissions/CIK0000789019.json` (MSFT) | HTTP 200; 185.425 byte; JSON; CIK `789019`; tickers `["MSFT"]`; 6 hồ sơ 10-Q/10-K gần nhất | **ĐẠT** — dùng phát hiện hồ sơ |
| S2 | `https://data.sec.gov/submissions/CIK0001652044.json` (GOOGL) | HTTP 200; 152.246 byte; JSON; CIK `1652044`; tickers `GOOGL/GOOG/GOOGM/GOOGN`; 6 hồ sơ gần nhất | **ĐẠT** |
| S3 | `https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json` | HTTP 200; 4.938.072 byte; `us-gaap` 562 thẻ; `dei` 3 thẻ | **ĐẠT** — nguồn facts chính |
| S4 | `https://data.sec.gov/api/xbrl/companyfacts/CIK0001652044.json` | HTTP 200; 3.249.987 byte; `us-gaap` 550 thẻ | **ĐẠT** |
| S5 | `https://data.sec.gov/api/xbrl/companyconcept/CIK0000789019/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json` | HTTP 200; 21.222 byte; 136 facts; fact mới nhất period_end 2026-09-30, val 92.279.000.000, form 10-Q, accn `0001193125-26-436133` | **ĐẠT** — dùng kiểm tra lại giá trị |
| S6 | `https://data.sec.gov/api/xbrl/companyconcept/CIK0001652044/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json` | HTTP 200; 13.881 byte; 87 facts; fact mới nhất 2025-03-31, val 90.234.000.000 | **ĐẠT nhưng có tag switch** — từ 2025-Q2 phải dùng `Revenues` |
| S7 | `https://www.sec.gov/Archives/edgar/data/789019/000119312526436133/` | HTTP 200; 30.004 byte; `accession_number` xuất hiện trong body | **ĐẠT** — `source_url` cho UI |
| S8 | `https://www.sec.gov/Archives/edgar/data/1652044/000165204426000084/` | HTTP 200; 30.430 byte; accession trong body | **ĐẠT** |
| S9 | `https://www.sec.gov/Archives/edgar/data/789019/000119312526436133/index.json` | HTTP 200; 9.611 byte; JSON danh sách file | **ĐẠT** — dùng tìm instance XML |
| S10 | `https://www.sec.gov/Archives/edgar/data/789019/000119312526436133/msft-20260930_htm.xml` | HTTP 200; 7.251.916 byte; có `StatementBusinessSegmentsAxis`; segment mới `AgentsAndInfraMember`, `DevicesAndConsumerMember` | **ĐẠT** — nguồn segment |
| S11 | `https://www.sec.gov/Archives/edgar/data/1652044/000165204426000084/goog-20260930_htm.xml` | HTTP 200; 3.161.339 byte; có `GoogleCloudMember`, `GoogleServicesMember`, `AllOtherSegmentsMember` | **ĐẠT** |
| S12 | `https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630_htm.xml` | HTTP 200; 10.948.157 byte; segment cũ `IntelligentCloudMember` | **ĐẠT** — xác nhận điểm gãy segment |
| S13 | `yfinance` 1.7.0 — `Ticker.history` cho MSFT/GOOGL/SPY/QQQ | 1.214 phiên/mã; 2022-01-03 → 2026-11-03; có `Adj Close`, `Dividends`, `Stock Splits`; GOOGL có split 20:1 ngày 2022-07-18 | **ĐẠT** — nguồn giá chính (không chính thức) |
| S14 | `https://query1.finance.yahoo.com/v8/finance/chart/MSFT?...` | HTTP 200; 132.495 byte; JSON; có timestamp, adjclose, dividends, splits | **ĐẠT** — evidence/fallback cùng nhà cung cấp |
| S15 | `https://api.nasdaq.com/api/quote/MSFT/historical?assetclass=stocks&fromdate=2022-01-03&todate=2026-11-03&limit=2000` | HTTP 200; 136.883 byte; 1.214 dòng; close khớp yfinance (MSFT 520,99; GOOGL 280,03; SPY 754,35; QQQ 685,28) | **ĐẠT dữ liệu — CHỜ ALLOWLIST** — nguồn đối chiếu giá close |
| S16 | `https://www.microsoft.com/en-us/Investor/` | HTTP 200; 308.025 byte; HTML | **ĐẠT ở mức reachable** — chỉ đối chiếu thủ công (CR-06), không crawler |
| S17 | `https://abc.xyz/investor/` | HTTP 200; 167.549 byte; HTML | **ĐẠT ở mức reachable** — chỉ đối chiếu thủ công |

> **Lưu ý governance:** S15 (Nasdaq) đạt về dữ liệu nhưng **chưa được phép dùng** vì `api.nasdaq.com` nằm ngoài allowlist CR-13. S13 (yfinance) đã có trong allowlist. S14 (Yahoo chart API) cùng nhà cung cấp với yfinance, chỉ dùng làm evidence/fallback, không tính là nguồn độc lập.

### 2.2 Nguồn KHÔNG ĐẠT / CHƯA ĐỦ ĐIỀU KIỆN

| ID | Nguồn / endpoint | Kết quả kiểm tra | Quyết định |
|---|---|---|---|
| R1 | `https://stooq.com/q/d/l/?s=msft.us&i=d` | HTTP 200 nhưng 796 byte, `Content-Type: text/html`; body là trang yêu cầu JavaScript ("This site requires JavaScript to verify your browser"), **không có CSV** | **LOẠI** khỏi crawler server-side. Không được ghi "đã đối chiếu Stooq". |
| R2 | `https://news.microsoft.com/2023/01/23/microsoft-and-openai-announce-multiyear-multibillion-dollar-investment/` | HTTP **404**; title "Page not found - Source" | **LOẠI** — ví dụ điển hình của URL đoán sai; không đưa vào registry. |
| R3 | `https://www.microsoft.com/en-us/investor/earnings` | HTTP 200; 115.049 byte; title "Default"; nội dung HTML ban đầu không có dữ liệu tài chính cụ thể | **KHÔNG DÙNG** làm nguồn số tự động; chỉ mở thủ công nếu cần. |
| R4 | `https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=MSFT&outputsize=compact&apikey=demo` | HTTP 200 nhưng body là thông báo "demo API key ..."; **không có dữ liệu MSFT** | **CHƯA ĐỦ ĐIỀU KIỆN** — chỉ dùng khi có key thật và chạy lại qualification. |
| R5 | `https://blog.google/technology/ai/google-gemini-ai/` (redirect → `blog.google/innovation-and-ai/technology/ai/google-gemini-ai/`) | HTTP 200; 389.101 byte; title "Introducing Gemini: Google's most capable AI model yet" | **CHỜ QUYẾT ĐỊNH** — domain `blog.google` chưa có trong allowlist CR-13. Không tự thêm. |

### 2.3 Bài học: HTTP 200 ≠ có dữ liệu

Ba ví dụ phải đưa vào test của `verify_links`:

1. **Stooq:** 200 + HTML challenge → phải trả `result=blocked`, không phải `ok`.
2. **Microsoft IR "Default":** 200 + title vô nghĩa → phải trả `result=soft404` hoặc `invalid_content`.
3. **Microsoft Source 404:** status 404 + title "Page not found" → `result=broken`.

`verify_links` phải kiểm tra **ngữ nghĩa**, không chỉ status:

- `Content-Type` đúng kỳ vọng (JSON cho API, HTML cho trang hồ sơ).
- Với SEC index: `accession_number` có trong body; `period_end` khớp; `form` khớp.
- Với XBRL: gọi lại `companyconcept` hoặc đọc lại `companyfacts`; so khớp **tuyệt đối** giá trị, kỳ, tag.
- Với HTML: title không thuộc `{"", "Default", "Page not found", "404", "Access Denied"}`; body chứa tên công ty + accession/kỳ hoặc tiêu đề sự kiện; độ dài text tối thiểu; phát hiện soft-404.
- Với trang giá: nếu là JS challenge/consent wall → `blocked`; dùng API làm evidence.

### 2.4 Quyết định thay thế nguồn

| Nhu cầu | Nguồn chính | Nguồn đối chiếu | Trạng thái |
|---|---|---|---|
| Giá daily, cổ tức, split, adjusted close | yfinance (S13) | Nasdaq API cho **close chưa điều chỉnh** (S15); Alpha Vantage cho **adjusted close** nếu có key | Dữ liệu đạt; **chờ mở allowlist** cho Nasdaq/Alpha Vantage. Adjusted close: **chưa xác minh chéo** cho đến khi có key |
| Benchmark SPY/QQQ | yfinance | Nasdaq API (ETF) | Dữ liệu đạt; **chờ mở allowlist**; adjusted close như trên |
| Tài chính quý | SEC companyfacts/companyconcept (S3–S6) | SEC archive index + XBRL instance (S7–S12) | ĐẠT |
| Segment | SEC XBRL instance (S10–S12) | Đối chiếu consolidated totals | ĐẠT nhưng có điểm gãy MSFT |
| Sự kiện AI | 8-K/10-Q hoặc thông cáo chính thức | Người nhập + người kiểm chéo (CR-14) | **Chưa có sự kiện nào được duyệt** — không bịa |
| IR | Microsoft IR / Alphabet IR | Đối chiếu thủ công 5 chỉ số (NFR-12) | Chỉ thủ công |

#### 2.4.1 Khoảng trống allowlist CR-13 — phải chốt trước M2

CR-13 hiện chỉ cho phép: `sec.gov`, `data.sec.gov`, `finance.yahoo.com`/`yfinance`, `stooq.com`, `microsoft.com`, `abc.xyz`.

| Nguồn đề xuất | Có trong allowlist? | Việc phải làm |
|---|---|---|
| `api.nasdaq.com` / `nasdaq.com` | **Không** | Thêm vào `config/allowlist.yaml` + ghi lý do thay thế Stooq; nếu không, không được crawler gọi. |
| `alphavantage.co` | **Không** | Thêm khi có key; nếu không, không dùng và ghi adjusted close là `unverified`. |
| `blog.google` | **Không** | Chỉ thêm nếu nhóm chấp nhận dùng blog chính thức cho `ai_event`; nếu không, dùng 8-K/10-Q. |
| `news.microsoft.com` | Thuộc `microsoft.com` (subdomain) | Vẫn phải kiểm tra nội dung; URL đã thử bị 404 nên không dùng. |

**Quy tắc:** Không được lách allowlist bằng cách gọi URL qua proxy hoặc đổi domain. Nếu nhóm không duyệt mở rộng allowlist, phương án hợp lệ duy nhất là:
- Giá: yfinance (đã có trong allowlist) + ghi rõ **chưa có nguồn thứ 2** → DR-04.3 chưa đạt.
- Adjusted close: chỉ yfinance → ghi `unverified`.
- AI events: chỉ SEC 8-K/10-Q + `microsoft.com`/`abc.xyz`.

> **Không được tuyên bố "đã đối chiếu Stooq"** trong báo cáo, slide hay trang Methodology. Nếu cần, ghi: "Stooq bị chặn bởi JavaScript challenge tại thời điểm kiểm tra; đề xuất thay bằng Nasdaq API sau khi mở allowlist".

---

## 3. KIẾN TRÚC DỮ LIỆU RAW → VERIFIED → PREPROCESS → OUTPUT

### 3.1 Sơ đồ

```
SEC EDGAR ─┐
yfinance ──┼─> crawler ─> data/raw/_cache/<sha256> + CSV append-only
Nasdaq ────┘                         │
                                     v
                          verify_links + reconcile + quality
                                     │
                                     v
                          data/verified/*.json + data/db/aicor.sqlite
                                     │
                                     v
                          preprocess (quarterly wide table)
                                     │
                                     v
                          web/public/data/*.json (snapshot vYYYYMMDD.N)
                                     │
                                     v
                          React dashboard + /api/health
```

### 3.2 Nguyên tắc lưu trữ

| Nguyên tắc | Cách thực hiện |
|---|---|
| Append-only | Mỗi lần chạy ghi file snapshot mới hoặc append dòng mới với `run_id`; không sửa dòng cũ. |
| Cache phản hồi gốc | `data/raw/_cache/<sha256>` chứa nguyên bytes; `_index.jsonl` ánh xạ hash → URL/status/headers/fetched_at. |
| Chống trùng | Khóa tự nhiên: `(cik, tag, unit, start, end, accn)`; `fact_id` = SHA-256 của khóa + value. |
| Tái lập | Sort key cố định; seed cố định cho lấy mẫu đối chiếu; pin version trong `requirements.lock`. |
| Không ghi đè | Giá adjusted close có thể bị Yahoo điều chỉnh lại sau cổ tức → lưu snapshot theo `as_of`; preprocess chọn snapshot mới nhất cho toàn bộ chuỗi. |
| Lỗi nguồn | Giữ dữ liệu cũ; ghi `sync_log` trạng thái `failed`; không xóa dữ liệu tốt (NFR-15). |

### 3.3 Cấu trúc thư mục đề xuất

```
config/
  concept_map.yaml          # tag XBRL, unit, duration mode, priority theo kỳ
  segment_map.yaml          # member → segment name/scheme
  source_registry.yaml      # nguồn đạt/loại/chờ, URL, ghi chú
  thresholds.yaml
  allowlist.yaml
pipeline/
  crawlers/
    sec_submissions.py
    sec_facts.py
    sec_segments.py
    prices.py
  verify/
    links.py
    reconcile.py
    quality.py
  preprocess/
    calendar.py
    normalize.py
    derive_q4.py
    prices.py
    segments.py
    build_outputs.py
  metrics/formulas.py
  stats/tests.py
  run.py                    # --mode full|incremental
data/
  raw/
    _cache/<sha256>
    _cache/_index.jsonl
    sec/
      filings.csv
      facts.csv
      segments.csv
    prices/
      prices_<as_of>.csv
      corporate_actions.csv
    manual/
      ai_events.csv
      ir_checks.csv
  verified/
    link_report.json
    reconcile_report.json
    quality_report.json
    source_registry.json
    manifest.json
  db/aicor.sqlite
  snapshots/vYYYYMMDD.N/
web/public/data/
  manifest.json
  overview.json
  investor.json
  financials.json
  ai_analysis.json
  decision.json
  methodology.json
  tests.json
  prices/{MSFT,GOOGL,SPY,QQQ}.json
```

> Cấu trúc này là mở rộng của Phụ lục F, không thay đổi các đường dẫn bắt buộc (`data/raw`, `data/verified`, `data/db`, `web/public/data`).

### 3.4 Schema raw

#### `data/raw/sec/filings.csv`

```
run_id, cik, ticker, company_name, accession_number, form, filing_date, report_date,
primary_document, is_amendment, source_url, evidence_url, http_status, fetched_at,
response_sha256, parser_version
```

#### `data/raw/sec/facts.csv`

```
run_id, fact_id, cik, ticker, taxonomy, xbrl_tag, unit, period_start, period_end,
value_raw, value_usd, form, fiscal_year, fiscal_period, filed_date, accession_number,
frame, source_url, evidence_url, http_status, fetched_at, response_sha256,
is_original, is_restated, restatement_of_fact_id, parser_version
```

- `value_raw`: giá trị gốc trong XBRL (USD).
- `value_usd`: giá trị chuẩn hóa sang USD; output dashboard dùng triệu USD (`value_usd / 1e6`).
- `is_original=true`: fact lấy từ hồ sơ công bố lần đầu cho kỳ đó.
- `is_restated=true`: fact từ hồ sơ sau có giá trị khác; chỉ lưu audit, không dùng kiểm định.

#### `data/raw/sec/segments.csv`

```
run_id, cik, ticker, accession_number, period_start, period_end, segment_scheme,
segment_name, segment_member, metric, value_usd, dimensions_json, source_url,
evidence_url, fetched_at, response_sha256, parser_version
```

#### `data/raw/prices/prices_<as_of>.csv`

```
run_id, as_of, ticker, instrument_type, trade_date, open, high, low, close, adj_close,
volume, dividends, stock_splits, price_source, source_url, evidence_url, fetched_at,
response_sha256, parser_version
```

#### `data/raw/prices/corporate_actions.csv`

```
run_id, ticker, action_date, action_type, value, source, source_url, evidence_url,
fetched_at, response_sha256
```

#### `data/raw/manual/ai_events.csv`

```
event_id, company, event_date, title, event_type, description, source_url, source_type,
official_domain, evidence_quote, evidence_sha256, entered_by, reviewed_by, review_date,
status
```

- Chỉ `status=verified` mới xuất ra dashboard.
- Không có sự kiện nào verified → timeline rỗng, ghi "Chưa có sự kiện được kiểm chứng"; **không tạo sự kiện mẫu**.

#### `data/raw/manual/ir_checks.csv`

```
check_id, company, metric, period_end, sec_value, ir_value, ir_url, checked_by,
checked_at, diff, result
```

### 3.5 Schema verified

#### `link_report.json`

```json
{
  "schema_version": "1.0",
  "snapshot_version": "v20261104.1",
  "generated_at": "2026-11-04T16:17:27Z",
  "summary": {"total": 0, "ok": 0, "broken": 0, "blocked": 0, "soft404": 0, "skipped": 0},
  "items": [{
    "url": "...",
    "domain": "sec.gov",
    "source_type": "sec_filing_index",
    "checked_at": "...",
    "http_status": 200,
    "content_type": "text/html; charset=UTF-8",
    "page_title": "...",
    "content_sha256": "...",
    "content_length": 30004,
    "matched_accession": "...",
    "matched_period_end": "2026-09-30",
    "matched_value": 92279000000,
    "result": "ok",
    "reason": ""
  }]
}
```

#### `quality_report.json`

```json
{
  "schema_version": "1.0",
  "snapshot_version": "v20261104.1",
  "summary": {
    "companies": ["MSFT", "GOOGL"],
    "quarters_expected": 19,
    "quarters_present": 19,
    "missing": 0,
    "low": 0,
    "verified_ratio": 1.0
  },
  "companies": [{
    "ticker": "MSFT",
    "quarters": [{
      "calendar_key": "2026-Q3",
      "period_end": "2026-09-30",
      "metrics": {
        "revenue": {
          "value": 92279,
          "unit": "million USD",
          "source_url": "...",
          "accession_number": "...",
          "xbrl_tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
          "form": "10-Q",
          "filed_date": "2026-10-28",
          "derived": false,
          "verified": true,
          "quality_flag": "ok",
          "reason": ""
        }
      }
    }]
  }]
}
```

#### `manifest.json`

```json
{
  "schema_version": "1.0",
  "snapshot_version": "v20261104.1",
  "generated_at": "...",
  "data_as_of": "2026-11-03",
  "latest_quarter": "2026-Q3",
  "companies": ["MSFT", "GOOGL"],
  "files": {"overview": "overview.json", "...": "..."},
  "row_counts": {"facts": 0, "prices": 0, "segments": 0},
  "source_versions": {"yfinance": "1.7.0", "pandas": "3.0.3"},
  "link_report_summary": {"ok": 0, "broken": 0},
  "quality_summary": {"missing": 0, "low": 0},
  "checksums": {"overview.json": "sha256:..."}
}
```

### 3.6 `source_url` và `evidence_url`

| Loại | `source_url` (người dùng bấm) | `evidence_url` (máy kiểm tra) |
|---|---|---|
| SEC filing | `https://www.sec.gov/Archives/edgar/data/<CIK>/<accession_no_dash>/` | `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/<tag>.json` hoặc `companyfacts` |
| SEC segment | Trang index hồ sơ | URL instance XML (`..._htm.xml`) |
| Giá yfinance | `https://finance.yahoo.com/quote/<ticker>/history/` | Yahoo chart API URL hoặc file cache CSV |
| Giá Nasdaq | `https://www.nasdaq.com/market-activity/stocks/<ticker>/historical` | Nasdaq API URL |
| AI event | URL bài viết/thông cáo | Cùng URL + `evidence_quote` + `content_sha256` |

- UI "Xem nguồn" luôn mở `source_url` ở tab mới (FR-65).
- `verify_links` dùng `evidence_url` để kiểm tra giá trị; nếu `evidence_url` là file cache, kiểm tra hash và nội dung.

### 3.7 Rate limit, retry, User-Agent

| Nguồn | Giới hạn | Retry | Ghi chú |
|---|---|---|---|
| SEC | ≤ 5 yêu cầu/giây (SPEC cho phép ≤ 10, khuyến nghị ≤ 5) | 3 lần, backoff 1/2/4 s; tôn trọng `Retry-After` | `SEC_USER_AGENT` phải có tên + email thật; không dùng email giả trong production |
| Nasdaq | ≤ 1 yêu cầu/giây | 3 lần | Endpoint công khai không SLA; cache |
| Yahoo/yfinance | ≤ 1 yêu cầu/giây | 3 lần | Không chạy song song nhiều ticker |
| Alpha Vantage | Theo quota key (free tier hiện hành) | 1 lần | Chỉ dùng khi có key; đọc quota trước |

### 3.8 `sync_log` và idempotency

Mỗi lần chạy ghi:

```
run_id, started_at, finished_at, source, mode, status, records_added,
records_skipped, error_message, snapshot_version
```

- `status`: `success` / `partial` / `failed`.
- Không xóa dữ liệu cũ khi lỗi; ghi `partial` và giữ snapshot trước.
- Chạy lại cùng input phải cho cùng output (trừ `fetched_at`); test idempotency.

---

## 4. PREPROCESS CHI TIẾT

### 4.1 Các bước P0–P10

| Bước | Việc làm | Output | Gate |
|---|---|---|---|
| P0 | Validate schema/hash raw; kiểm tra không thiếu file | `raw_validation.json` | Fail nếu hash sai hoặc thiếu cột |
| P1 | Chọn hồ sơ gốc, phát hiện amendment/restatement | `filings_resolved.csv` | Mỗi kỳ có đúng 1 fact gốc |
| P2 | Chuẩn hóa unit, duration, tag | `facts_normalized.csv` | Không còn unit lạ; duration hợp lệ |
| P3 | Chuyển YTD → quý (GOOGL CFO/CapEx) | `facts_quarterly.csv` | Tổng 4 quý khớp năm |
| P4 | Suy ra Q4 từ 10-K | `facts_q4.csv` | Residual ≤ 0,5% |
| P5 | Map `period_end` → quý lịch | `facts_calendar.csv` | 19 quý, không trùng |
| P6 | Ghép bảng wide theo công ty/quý | `company_financials.csv` | Mỗi ô có metadata nguồn |
| P7 | Tính chỉ số (revenue growth, margins, FCF, R&D/CapEx intensity, ROE, ROIC) | `metrics_quarterly.csv` | Công thức khớp tính tay |
| P8 | Xử lý giá: daily, monthly, quarterly, benchmark, split/dividend | `prices_processed.csv` | Đối chiếu ≥ 30 ngày/mã |
| P9 | Segment: parse XBRL, scheme, kiểm tra tổng | `segment_financials.csv` | Tổng segment ≈ consolidated |
| P10 | Xuất JSON + manifest + quality/link report | `web/public/data/*.json` | Schema validation + 10/10 nguồn |

### 4.2 Lịch quý: MSFT và GOOGL

**Quy tắc:** dùng `period_end` làm gốc; quý lịch = quý chứa `period_end` (C.2 #3). Không dùng nhãn fiscal để so sánh trực tiếp.

| Công ty | Fiscal Q1 | Fiscal Q2 | Fiscal Q3 | Fiscal Q4 | Quy đổi |
|---|---|---|---|---|---|
| MSFT | Jul–Sep | Oct–Dec | Jan–Mar | Apr–Jun | Fiscal Q1 → calendar Q3; Q2 → Q4; Q3 → Q1; Q4 → Q2 |
| GOOGL | Jan–Mar | Apr–Jun | Jul–Sep | Oct–Dec | Fiscal = calendar |

- Lưu đồng thời: `fiscal_year`, `fiscal_quarter`, `period_end`, `calendar_year`, `calendar_quarter`, `calendar_key`.
- Nếu `period_end` lệch vài ngày so với cuối quý (ví dụ 13-week period), vẫn gán vào quý chứa `period_end`; ghi `period_end_offset_days`.
- Không trộn dữ liệu năm vào quý khi chưa quy đổi (DR-01.6).

### 4.3 Chọn fact gốc và chống restatement

1. Với mỗi `(cik, tag, unit, period_start, period_end)`, sắp xếp theo `filed_date` tăng dần.
2. Fact đầu tiên = `is_original=true`, dùng cho phân tích.
3. Fact sau có giá trị khác > `max(0.5%, 1 triệu USD)` = `is_restated=true`; lưu `restatement_of_fact_id`, `restatement_delta`.
4. Amendment `10-Q/A`, `10-K/A` xử lý như restatement; không dùng cho phân tích "công bố lần đầu" (C.2 #10).
5. Nếu không có fact gốc nhưng có fact sau: dùng fact sau với `quality_flag=low`, ghi `original_missing=true`; dashboard hiển thị ghi chú.
6. Không trộn fact từ 10-K (annual) vào quý nếu chưa derive Q4.

### 4.4 Tag switch của GOOGL

- `concept_map.yaml` khai báo:

```yaml
GOOGL:
  revenue:
    unit: USD
    duration: quarter
    priority:
      - tag: Revenues
        valid_from: "2025-04-01"
      - tag: RevenueFromContractWithCustomerExcludingAssessedTax
        valid_to: "2025-03-31"
```

- Nhưng priority chỉ là gợi ý; pipeline phải chọn **tag thực sự xuất hiện trong hồ sơ gốc của kỳ đó**.
- Nếu cả hai tag cùng có fact cho một kỳ:
  - So sánh giá trị; nếu lệch > 0,5% → `quality_flag=low`, ghi `tag_conflict`.
  - Chọn tag có `accn` trùng hồ sơ gốc; nếu không xác định, dùng priority.
- Ghi `tag_switch=true` tại kỳ chuyển; dashboard Methodology hiển thị ghi chú.
- Kiểm tra tự động: chuỗi revenue không có gap; Q2/2025 phải có giá trị.

### 4.5 YTD → quý (GOOGL CFO/CapEx)

GOOGL 10-Q thường báo lũy kế:

| Kỳ | Tag | Cách lấy quý |
|---|---|---|
| Q1 | YTD Q1 | = YTD Q1 |
| Q2 | YTD Q1–Q2 | = YTD Q2 − YTD Q1 |
| Q3 | YTD Q1–Q3 | = YTD Q3 − YTD Q2 |
| Q4 | 10-K annual | = Annual − YTD Q3 |

- Áp dụng cho `NetCashProvidedByUsedInOperatingActivities`, `PaymentsToAcquirePropertyPlantAndEquipment`.
- Không áp dụng cho revenue, R&D, operating income, net income nếu đã có fact quý trực tiếp; nếu chỉ có YTD, áp dụng cùng quy tắc.
- Kiểm tra: `Q1+Q2+Q3+Q4 ≈ Annual` (sai lệch làm tròn ≤ 0,5%).
- MSFT: 10-Q có cả YTD và quý; chọn duration quý (80–100 ngày) cho Q1–Q3; Q4 = annual − tổng Q1–Q3.

### 4.6 Suy ra Q4

Công thức:

```
Q4 = FY (10-K) − (Q1 + Q2 + Q3)
```

- Chỉ cho flow metrics: revenue, operating income, net income, R&D, CapEx, CFO, income tax, EPS diluted.
- Không cho balance sheet (instant): dùng giá trị tại `period_end` của 10-K.
- `derived=true`, `derivation_method="FY - Q1..Q3"`, `component_accessions=[...]`.
- Kiểm tra:
  - `abs((Q1+Q2+Q3+Q4) − FY) / FY ≤ 0,5%` → `ok`.
  - `0,5% < ... ≤ 2%` → `quality_flag=low` (làm tròn), vẫn dùng.
  - `> 2%` → `quality_flag=missing`, loại khỏi kiểm định; ghi lý do.
- Q4 MSFT fiscal → calendar Q2; Q4 GOOGL → calendar Q4.
- Không suy ra Q4 2026 của GOOGL (chưa có 10-K FY2026 tại 2026-11-04); quý mới nhất là 2026-Q3.

### 4.7 Bảng wide và công thức

Index: `(ticker, calendar_key)`.

Cột tối thiểu:

```
revenue, operating_income, net_income, rd_expense, capex, cfo,
total_assets, total_equity, total_debt, cash_and_st_investments,
income_tax_expense, pretax_income, eps_diluted,
source metadata cho từng cột
```

Công thức (Appendix B.3):

```
Revenue Growth YoY = (Rev_t − Rev_t−4) / Rev_t−4
Operating Margin   = Operating Income / Revenue
Net Profit Margin  = Net Income / Revenue
R&D Intensity      = R&D / Revenue
CapEx Intensity    = CapEx / Revenue
FCF                = CFO − CapEx
FCF Margin         = FCF / Revenue
ROE                = Net Income / Average Equity
Tax Rate           = Income Tax Expense / Pretax Income, clamp [0, 0.5]
NOPAT              = Operating Income × (1 − Tax Rate)
Invested Capital   = Total Debt + Total Equity − Cash & Marketable Securities
ROIC               = NOPAT / Average Invested Capital
EPS (trailing 4Q)  = sum(EPS diluted 4 quý)
P/E (trailing)     = Price at quarter-end / EPS trailing 4Q
```

Quy ước đề xuất (cần chốt):

- `Total Debt = LongTermDebtCurrent + LongTermDebtNoncurrent`.
- `Cash & Marketable Securities = CashCashEquivalentsAndShortTermInvestments` (tag chuẩn có cho cả hai công ty).
- `Average Equity` = trung bình `total_equity` đầu kỳ và cuối kỳ; quý đầu tiên có thể null nếu thiếu quý trước.
- `P/E` dùng GAAP diluted EPS; nếu quý có one-time gain lớn (ví dụ GOOGL 2026-Q2), hiển thị ghi chú, **không tự loại**.
- **GOOGL split 20:1 (2022-07-18):** chỉ điều chỉnh EPS cho các kỳ kết thúc **trước 2022-06-30**. Q1/2022: `value=1,231`, `reported_value=24,62`, `split_adjustment=20`, `quality_flag=low`. Q2/2022 đã công bố post-split (1,21) nên **không** chia lại. Nhờ vậy Q4/2022 = FY 4,56 − Q1 1,231 − Q2 1,21 − Q3 1,06 = 1,059 và trailing EPS 2022-Q4 = 4,56, P/E trailing dương và hợp lý. Bằng chứng SEC: `docs/evidence/googl_eps_split_2026-11-05.json`.
- Nếu thiếu bất kỳ thành phần nào → null + `quality_flag=missing` + lý do; không ước lượng.

### 4.8 Giá, cổ tức, split, benchmark

**Nguồn:** yfinance (`Ticker.history`, `auto_adjust=False`, `actions=True`); đối chiếu close với Nasdaq API **sau khi `api.nasdaq.com` được thêm vào allowlist CR-13**.

**Khoảng lấy:**

- Giá daily: từ `2020-12-01` đến ngày chạy, để đủ ROI 5 năm và mốc Q4/2021 cho lợi suất Q1/2022.
- Tài chính: từ `2021-01-01` (đủ trailing EPS, Q4 FY2022 của MSFT); hiển thị từ 2022-Q1.

**Xử lý:**

1. Chuẩn hóa tên cột: `Open, High, Low, Close, Adj Close, Volume, Dividends, Stock Splits`.
2. `trade_date` = ngày giao dịch; kiểm tra không trùng, không ngày tương lai.
3. `price_source=yfinance`; `source_url` = trang Yahoo Finance history; `evidence_url` = Yahoo chart API hoặc cache CSV; `response_sha256` = hash file CSV.
4. Split: lưu `stock_splits`; test GOOGL 20:1 ngày 2022-07-18:
   - Kiểm tra continuity: giá trước/sau split điều chỉnh đúng hệ số 20.
   - Calculator dùng giá đã điều chỉnh split (yfinance `Close` là split-adjusted), nên số cổ phiếu là "synthetic split-adjusted shares"; ghi chú trong Methodology.
5. Dividends:
   - Calculator: dùng `Close` (split-adjusted, chưa dividend-adjusted) + `Dividends` thực tế; `Vt = Shares × Pt + Dt`.
   - Charts/total return: dùng `Adj Close` (đã gồm cổ tức); **không cộng thêm Dt** (tránh double count, FR-07).
   - Ghi rõ hai chế độ trong tooltip/Methodology.
6. Monthly returns cho BT1: mốc giá là phiên cuối cùng của tháng; tính `(AdjP_t − AdjP_t−1)/AdjP_t−1`.
7. Quarterly returns cho BT5: phiên cuối cùng ≤ ngày cuối quý lịch (FR-26).
8. Benchmark: SPY, QQQ; adjusted close; cùng quy tắc mốc thời gian.
9. Volatility: độ lệch chuẩn daily returns × sqrt(252) (ghi rõ quy ước).
10. Max drawdown: trên chuỗi adjusted close; `min(P_t / cummax(P_t) − 1)`.

**Đối chiếu giá:**

- Chọn ngẫu nhiên ≥ 30 ngày giao dịch/mã với seed cố định (ví dụ `20261104`).
- So sánh yfinance `Close` với Nasdaq API close (chưa điều chỉnh) sau khi bỏ ký hiệu `$` và dấu `,`.
- Sai lệch tuyệt đối ≤ 0,1% → `ok`; ngược lại `low`/`broken`, ghi rõ.
- Adjusted close: nếu có Alpha Vantage key, so sánh `Adj Close` trên ≥ 30 ngày; nếu không, ghi `adj_close_secondary=unverified` trong Methodology; **không tuyên bố đã đối chiếu 2 nguồn**.
- Stooq: không dùng; ghi lý do.

### 4.9 Segment và điểm gãy MSFT

**Nguồn:** XBRL instance của từng 10-Q/10-K (`..._htm.xml`), không dùng `companyfacts` vì companyfacts không chứa dimension segment.

**Cách parse:**

1. Tải `index.json` của hồ sơ, tìm file `*_htm.xml`.
2. Parse context → period + dimensions.
3. Lọc fact có `us-gaap:StatementBusinessSegmentsAxis`.
4. Với GOOGL, loại context có thêm `srt:ProductOrServiceAxis` để lấy tổng segment (Google Services, Google Cloud, Other Bets).
5. Lưu `segment_scheme`:
   - `msft_legacy_3`: `ProductivityAndBusinessProcessesMember`, `IntelligentCloudMember`, `MorePersonalComputingMember` (đến 10-K FY2026, period_end 2026-06-30).
   - `msft_new_2`: `AgentsAndInfraMember`, `DevicesAndConsumerMember` (từ 10-Q Q1 FY2027, period_end 2026-09-30).
   - `goog_3`: `GoogleServicesMember`, `GoogleCloudMember`, `AllOtherSegmentsMember`.
6. `comparable=false` tại điểm gãy MSFT; không ánh xạ `Intelligent Cloud` sang segment mới.
7. Kiểm tra tổng segment ≈ consolidated revenue/operating income; sai lệch > 0,5% → `quality_flag=low`.
8. Q4 segment: chỉ derive trong cùng scheme; nếu thiếu Q1–Q3 cùng scheme → null.

**Dashboard:**

- Financial Performance: card "Cloud/MSFT segments" hiển thị dữ liệu lịch sử; tại 2026-Q3 có ghi chú "Microsoft đổi cấu trúc phân khúc; không so sánh trực tiếp".
- Nếu SPEC FR-21 vẫn yêu cầu "Intelligent Cloud", cần cập nhật SPEC hoặc chấp nhận chỉ hiển thị đến 2026-Q2. Đây là **quyết định mở**.

### 4.10 AI events và AI indicators

**AI indicators:**

- `rd_expense`, `capex`, `cloud_revenue` lấy từ SEC.
- Nhãn:
  - `Reported`: số trực tiếp từ hồ sơ (revenue, R&D, CapEx, Cloud revenue).
  - `Proxy`: dùng R&D/CapEx làm đại diện cho đầu tư AI; ghi rõ không phải toàn bộ dành cho AI (FR-23).
  - `Estimated`: **không dùng trong MVP** (C.2 #8).
- Không dùng ước tính chi tiêu AI của bên thứ ba.

**AI events:**

- Nhập tay vào `ai_events.csv`; mỗi sự kiện phải có `source_url`, `source_type`, `evidence_quote`, `entered_by`, `reviewed_by`.
- Chỉ chấp nhận:
  - 8-K/10-Q/10-K trên `sec.gov`.
  - Thông cáo chính thức trên `microsoft.com` hoặc `abc.xyz`.
  - Domain khác (`blog.google`, `news.microsoft.com`) chỉ khi nhóm cập nhật `allowlist.yaml` và có quyết định.
- Từ chối: trang chủ, trang 404/soft-404, login wall, bài viết không nêu ngày/sự kiện, tin đồn, nguồn bên thứ ba.
- Nếu chưa có sự kiện verified: timeline rỗng + thông báo; không dùng sự kiện giả để demo.
- Sự kiện AI **không được dùng làm biến trong kiểm định BT4/BT5**; chỉ là timeline ngữ cảnh (tránh khẳng định nhân quả).

### 4.11 Quality flags và chính sách missing

| Flag | Khi nào | Hành vi |
|---|---|---|
| `ok` | Có fact gốc, unit đúng, verified, không bất thường | Dùng |
| `low` | Q4 residual 0,5–2%; tag switch; có restatement; thiếu quý trước cho average; segment lệch; giá fallback | Dùng nhưng hiển thị cảnh báo; vẫn có thể loại khỏi test nếu cấu hình yêu cầu |
| `missing` | Thiếu tag, unit sai, HTTP lỗi, link fail, Q4 residual > 2%, giá không đối chiếu được | **Không dùng**; hiển thị "không có dữ liệu"; liệt kê lý do |
| `excluded` | Bị loại khỏi kiểm định do `missing`/`low` theo cấu hình | Ghi vào `excluded_quarters` |

- Không nội suy, không điền 0, không thay bằng số năm, không dùng LLM.
- Nếu một core metric thiếu ở một quý: dashboard hiển thị khoảng trống + tooltip lý do; test loại quý đó và ghi rõ.

### 4.12 Output JSON contracts

Tất cả file có `schema_version`, `snapshot_version`, `generated_at` (Phụ lục F).

| File | Nội dung chính | Trang dùng |
|---|---|---|
| `manifest.json` | snapshot, data_as_of, row counts, link/quality summary | Navbar, Methodology, `/api/health` |
| `overview.json` | KPI cards, normalized price series, business comparison | Executive Overview |
| `investor.json` | daily/monthly prices, calculator inputs, ROI windows, excess return test | Investor Return |
| `financials.json` | quarterly metrics + source metadata, segment data | Company Financial Performance |
| `ai_analysis.json` | RD/CapEx growth, correlation by lag, n, p, p_adj, ADF, events, labels | AI Investment Analysis |
| `decision.json` | comparison table, volatility, max drawdown, statuses, thresholds version | Stock Decision Support |
| `methodology.json` | formulas, sources, link report, quality report, limitations | Methodology |
| `tests.json` | BT1–BT5 results, snapshot, run_date, excluded quarters | AI Analysis, Decision, Methodology |
| `prices/{ticker}.json` | daily series theo mã, đủ cho chart/calculator | Investor, Overview |

**Ví dụ `financials.json` (rút gọn):**

```json
{
  "schema_version": "1.0",
  "snapshot_version": "v20261104.1",
  "generated_at": "2026-11-04T16:17:27Z",
  "companies": ["MSFT", "GOOGL"],
  "quarters": [{
    "ticker": "MSFT",
    "calendar_key": "2026-Q3",
    "period_end": "2026-09-30",
    "fiscal_year": 2027,
    "fiscal_quarter": "Q1",
    "metrics": {
      "revenue": {
        "value": 92279,
        "unit": "million USD",
        "source_url": "https://www.sec.gov/Archives/edgar/data/789019/000119312526436133/",
        "accession_number": "0001193125-26-436133",
        "xbrl_tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "form": "10-Q",
        "filed_date": "2026-10-28",
        "derived": false,
        "verified": true,
        "quality_flag": "ok"
      }
    }
  }]
}
```

**Ví dụ `ai_analysis.json` (rút gọn):**

```json
{
  "schema_version": "1.0",
  "snapshot_version": "v20261104.1",
  "correlations": [{
    "x": "RD_Growth",
    "y": "RevenueGrowth",
    "lag": 2,
    "r": 0.0,
    "p_value": 0.0,
    "p_adjusted": 0.0,
    "n": 13,
    "method": "spearman",
    "stationarity": "differenced",
    "note": "n < 30: chỉ tham khảo"
  }],
  "events": []
}
```

> Các giá trị `r/p` ở trên chỉ là placeholder schema, **không phải số liệu**. Pipeline M4 mới tính; không được đưa placeholder vào dashboard.

---

## 5. MA TRẬN ÁNH XẠ: NGUỒN → BT1–BT5 → DASHBOARD → FR

### 5.1 Bảng tổng

| Dataset / field | BT | Dashboard | Yêu cầu |
|---|---|---|---|
| `prices` daily: `close`, `adj_close`, `dividends`, `stock_splits` | BT1, BT5 | Investor Return: calculator, price chart, ROI 1/3/5 năm; Overview: normalized chart; Decision: volatility/drawdown | FR-01..15, FR-26, FR-32, FR-37..39; CR-05; DR-02 |
| `benchmark` SPY/QQQ: `adj_close`, `return` | BT1 | Investor Return: chọn benchmark, Excess Return; Overview | FR-08, FR-12; DR-03 |
| `company_financials.revenue` | BT2, BT4, BT5 | Financial: Revenue Growth; Overview KPI; Decision table; AI correlation | FR-16, 24..26, 31, 37; CR-01..04; DR-02/04 |
| `company_financials.net_income` | BT2 | Financial: Net Income Growth, Net Margin; Decision | FR-16, 31 |
| `company_financials.operating_income` | BT2, BT4 | Financial: Operating Margin; AI correlation | FR-16, 25 |
| `company_financials.cfo`, `capex` | BT2, BT3, BT4 | Financial: FCF, FCF Margin, CapEx Intensity; Decision; AI | FR-17, 18, 24, 25, 31 |
| `company_financials.rd_expense` | BT3, BT4 | Financial: R&D Intensity; AI | FR-17, 24, 25 |
| `company_financials.total_equity`, `total_debt`, `cash_and_st_investments` | BT2 (context) | Financial: ROE, ROIC; Decision | FR-19, 20 |
| `company_financials.eps_diluted` + `prices.close` | BT1/BT2 (context) | Decision: EPS, P/E trailing | FR-31 |
| `segment_financials` | BT2 (context) | Financial: Cloud/segment card | FR-21 |
| `tests` BT1–BT5 | BT1–BT5 | AI heatmap; Decision; Methodology | FR-48..54 |
| `link_report`, `quality_report` | all | Methodology; navbar freshness | FR-63; CR-10..12 |
| `ai_events` | context only | AI timeline | FR-28; CR-14 |
| `sync_log`, `manifest` | all | Navbar status; Methodology; `/api/health` | FR-39, FR-44; DP-05 |

### 5.2 Chi tiết từng trang

#### Executive Overview (FR-37..39)

- **KPI Stock Return**: giá adjusted close, khoảng 1 năm gần nhất; kèm benchmark.
- **KPI Revenue Growth**: revenue YoY quý mới nhất; kèm `period_end` và nguồn.
- **Biểu đồ giá chuẩn hóa**: MSFT/GOOGL/SPY/QQQ, gốc = 100 tại ngày bắt đầu.
- **Biểu đồ so sánh kinh doanh**: revenue growth, operating margin, FCF margin theo quý.
- **Data freshness**: `manifest.generated_at`, `data_as_of`, tuổi dữ liệu; nếu lỗi hiển thị dữ liệu cũ + trạng thái.

#### Investor Return (FR-01..15)

- Calculator: chọn MSFT/GOOGL, vốn, ngày mua, ngày đánh giá, phí; tính trong browser từ `prices/{ticker}.json`.
- Price chart + normalized mode; benchmark SPY/QQQ; ROI 1/3/5 năm; excess return.
- Tooltip/crosshair; xử lý ngày không giao dịch → phiên kế tiếp.
- Nguồn: mỗi điểm cuối có `source_url`; nút "Xem nguồn" mở Yahoo Finance history.
- Ghi chú: chưa tính thuế/tỷ giá; chỉ minh họa (FR-09).

#### Company Financial Performance (FR-16..23)

- 6 chỉ số cốt lõi: Stock Total Return, Revenue Growth, Net Income Growth, FCF, R&D/Revenue, CapEx/Revenue.
- Bổ sung: Operating Margin, Net Margin, FCF Margin, ROE, ROIC (nếu đủ dữ liệu).
- Bảng theo quý, sparkline, sort/search; mỗi dòng có "Xem nguồn".
- Cloud/segment card: GOOGL Google Cloud; MSFT legacy/new với ghi chú gãy cấu trúc.
- Ghi chú: R&D/CapEx là chỉ báo cấp công ty, không đồng nghĩa toàn bộ dành cho AI (FR-23).

#### AI Investment Analysis (FR-24..30a)

- RD_Growth, CapEx_Growth YoY.
- Heatmap correlation: X = RD_Growth/CapEx_Growth; Y = RevenueGrowth/FCFGrowth/OperatingMargin; lag 0–4.
- Mỗi ô: `r`, `p` đã Holm, `n`; cảnh báo n < 30.
- ADF: nếu không dừng → sai phân bậc 1; ghi rõ.
- Timeline sự kiện AI: chỉ sự kiện verified; mỗi sự kiện có `source_url`.
- Nhãn Reported/Proxy/Estimated; cảnh báo "tương quan, không phải nhân quả" (FR-30).

#### Stock Decision Support (FR-31..36)

- Bảng so sánh: Stock Return, Revenue Growth, Operating Margin, FCF Growth, R&D Intensity, CapEx Intensity, Valuation (P/E, EPS), Risk.
- Volatility, Max Drawdown.
- Trạng thái "Tích cực/Trung lập/Cần thận trọng" theo `thresholds.yaml`, kèm lý do, điều kiện, ngày cập nhật.
- Cảnh báo khi CapEx tăng nhưng FCF giảm, hoặc định giá cao.
- Nhãn "Không phải khuyến nghị đầu tư".

#### Methodology & Data Sources (FR-61..65)

- Công thức, quy ước quý lịch, adjusted close, số công bố lần đầu/restated.
- Danh sách nguồn, `source_url`, ngày cập nhật.
- `snapshot_version`, quality report (missing/low/verified ratio), link report.
- Giải thích giả thuyết, α = 0,05, Holm, n nhỏ, giới hạn diễn giải.
- Danh sách nguồn bị loại (Stooq, Alpha Vantage demo, Microsoft IR "Default") và lý do.

### 5.3 Khi không đủ dữ liệu thì hiển thị gì?

| Tình huống | Dashboard | Không được làm |
|---|---|---|
| Thiếu một quý | Khoảng trống + tooltip "Không có dữ liệu"; quality report liệt kê | Nội suy, điền 0, dùng quý gần nhất thay thế |
| Thiếu tag XBRL | "Không có dữ liệu" + tag missing | Tự suy ra từ tag khác nếu chưa kiểm tra |
| Q4 derive lệch > 2% | Loại khỏi test; hiển thị cảnh báo | Giữ số derive như thật |
| Segment MSFT sau 2026-Q3 | Hiển thị dữ liệu cũ + ghi chú cấu trúc; hoặc ẩn card | Ánh xạ Intelligent Cloud → Agents & Infrastructure |
| AI events chưa verified | Timeline rỗng + thông báo | Tạo sự kiện mẫu |
| Adjusted close chưa có nguồn thứ 2 | Vẫn dùng yfinance nhưng ghi "chưa xác minh chéo" | Tuyên bố đã đối chiếu 2 nguồn |
| n < 30 | Hiển thị n + "chỉ tham khảo" | Ẩn n hoặc khẳng định mạnh |

### 5.4 n nhỏ — cách hiển thị

- BT1: lợi suất tháng 2022-01 → 2026-10 ≈ 58 quan sát → đủ n > 30.
- BT2: 19 quý → n = 19; paired test; cảnh báo.
- BT3: 19 quý; OLS HAC; cảnh báo.
- BT4: RD_Growth/CapEx_Growth YoY → 15 quan sát; lag 0–4 → 11–15; cảnh báo mạnh.
- BT5: RevenueGrowth → 15; lag 0–4 → 11–15; cảnh báo mạnh.
- Dashboard phải hiển thị `n` cạnh mỗi hệ số (FR-27) và nhãn "chỉ mang tính tham khảo" khi n < 30 (FR-53).

---

## 6. KIỂM CHỨNG & CHỐNG BỊA DỮ LIỆU

### 6.1 `verify_links` — kiểm tra ngữ nghĩa

Với mỗi `source_url`/`evidence_url` duy nhất:

1. GET với UA; theo dõi redirect; ghi `final_url`.
2. Status phải 200–299; nếu 404/410 → `broken`; nếu 403/429 → `blocked` (retry có backoff).
3. `Content-Type`:
   - SEC JSON: `application/json`.
   - SEC index/HTML: `text/html`.
   - Giá API: `application/json`.
4. SEC filing index:
   - `accession_number` xuất hiện trong body.
   - `period_end` khớp.
   - `form` khớp.
5. SEC XBRL:
   - Gọi lại `companyconcept` hoặc đọc lại `companyfacts`.
   - So khớp tuyệt đối `val`, `end`, `accn`, `tag`.
   - Nếu tag không tồn tại → `missing`, không phải `broken`.
6. HTML:
   - Title không rỗng, không "Default", "Page not found", "404", "Access Denied".
   - Body chứa tên công ty + accession/period hoặc tiêu đề sự kiện.
   - Phát hiện soft-404/JS challenge/consent wall → `blocked` hoặc `soft404`.
7. Giá:
   - JSON có symbol đúng, date range, giá khớp.
   - Trang HTML phải có dữ liệu hoặc dùng API evidence.
8. Ghi `content_sha256`, `http_status`, `checked_at`, `result`, `reason`.

**CI gate:**

- Core values (revenue, operating_income, net_income, rd_expense, capex, cfo) có link hỏng > 0 → **fail** (CR-11).
- Link không core hỏng > 5% → warning.
- `blocked`/`soft404` không được tính là `ok`; core bị blocked → fail.

### 6.2 `reconcile` — đối chiếu số liệu

| Check | Công thức | Ngưỡng | Hành động |
|---|---|---|---|
| Q4 residual | `abs(sum(Q1..Q4) − FY)/FY` | ≤ 0,5% ok; ≤ 2% low; > 2% missing | Flag |
| FCF identity | `FCF = CFO − CapEx` | sai số ≤ 1 triệu USD | Fail |
| Unit | USD, triệu USD | đúng | Fail nếu lạ |
| Sign | Revenue/R&D/CapEx không âm; net income có thể âm | đúng | Flag nếu bất thường |
| Segment sum | tổng segment ≈ consolidated | ≤ 0,5% | Flag |
| Price close | yfinance vs Nasdaq (sau khi mở allowlist) | ≤ 0,1% | Flag/fail |
| Adjusted close | yfinance vs Alpha Vantage (nếu có key + allowlist) | ≤ 0,1% | Flag nếu chưa có |
| Tag switch | không gap chuỗi | 0 gap | Fail |
| Filing lag | `filing_date − period_end` | ≤ 120 ngày | Flag |
| Future data | `filed_date ≤ snapshot_date` | đúng | Fail |

### 6.3 `quality_report`

- Tổng số quý kỳ vọng: 19 (2022-Q1 → 2026-Q3).
- Đếm `ok/low/missing` theo công ty/metric.
- Tỷ lệ `verified` trên core metrics.
- Danh sách quý bị loại + lý do.
- Danh sách restatement/tag switch/segment break.
- Xuất JSON + hiển thị Methodology.

### 6.4 CI gates

| Gate | Lệnh/điều kiện | Fail khi |
|---|---|---|
| Unit tests | `pytest` | Test fail |
| Schema JSON | `check-jsonschema`/Zod | Schema sai |
| Link check mẫu | `verify_links --sample` | Core link hỏng |
| Không hardcode | grep số tài chính + review | Có hằng số tài chính |
| Không LLM trong pipeline | grep import/API LLM | Có call LLM |
| Build web | `npm run build` | Build lỗi |
| Snapshot | manifest có version/checksum | Thiếu |

### 6.5 Nghiệm thu "không bịa dữ liệu" (10/10)

1. Chọn ngẫu nhiên 10 con số hiển thị trên web (ưu tiên 6 core metrics + giá + segment + EPS).
2. Bấm "Xem nguồn".
3. Mở hồ sơ SEC hoặc trang giá gốc.
4. Xác nhận giá trị, kỳ, accession khớp.
5. Ghi biên bản: số hiển thị, nguồn, người kiểm, ngày.
6. Chỉ nghiệm thu khi **10/10 khớp**.

### 6.6 Những gì bị cấm

- Viết cứng số tài chính trong pipeline/test (CR-07).
- Dùng LLM để sinh/điền số.
- Dùng Stooq và tuyên bố đã đối chiếu.
- Dùng Alpha Vantage demo key rồi coi là dữ liệu thật.
- Tạo `ai_event` không có URL/không được review.
- Ánh xạ segment cũ sang segment mới khi chưa có bảng ánh xạ chính thức.
- Điền 0/nội suy khi thiếu.
- Hiển thị số minh họa như dữ liệu thật (UI-06).

---

## 7. KẾ HOẠCH THỰC HIỆN M1–M3

### 7.1 Task breakdown

| ID | Task | Owner | Ước lượng | Phụ thuộc | DoD |
|---|---|---|---|---|---|
| T1.1 | `concept_map.yaml`, `segment_map.yaml`, `source_registry.yaml`, `allowlist.yaml` | TV1 + TV2 | 2 ngày | SPEC | Đủ tag/unit/duration/priority; review chéo |
| T1.2 | SEC client: rate limit ≤ 5/s, UA, retry, cache SHA-256, ETag | TV1 | 2 ngày | T1.1 | Test fixture; 429/5xx xử lý; cache ghi đúng |
| T1.3 | Submissions crawler → `filings.csv` | TV1 | 1 ngày | T1.2 | 6 hồ sơ gần nhất/mã; detect amendment |
| T1.4 | Companyfacts crawler → `facts.csv` | TV1 | 2 ngày | T1.2 | ≥ 12 quý/mã; mọi dòng có accession/source/hash |
| T1.5 | Tag coverage report | TV2 | 1 ngày | T1.4 | Không core tag nào thiếu mà không flag |
| T1.6 | Segment crawler (instance XML) | TV1 | 3 ngày | T1.2 | MSFT legacy/new, GOOGL Cloud; sum check |
| T1.7 | Fixtures + unit tests | TV1/TV2 | 2 ngày | T1.3–T1.6 | `pytest` xanh; không network |
| T2.1 | yfinance crawler + snapshot + hash | TV3 | 2 ngày | T1.1 | 1.214 dòng/mã từ 2022; đủ cột |
| T2.2 | Nasdaq reconciliation 30 ngày/mã (sau khi allowlist được duyệt) | TV3 | 1 ngày | T2.1 + allowlist | Sai lệch ≤ 0,1% hoặc flag |
| T2.3 | Corporate actions + split/dividend tests | TV3 | 1 ngày | T2.1 | GOOGL split 2022-07-18 pass |
| T2.4 | Price quality (missing/stale/zero volume) | TV3 | 1 ngày | T2.1 | Report + flag |
| T2.5 | Benchmark SPY/QQQ + monthly/quarterly returns | TV3 | 1 ngày | T2.1 | Khớp mẫu tính tay |
| T2.6 | Alpha Vantage qualification (conditional, sau allowlist) | TV3 | 0,5 ngày | Key + allowlist | Có key: pass; không: ghi unverified |
| T3.1 | `verify_links` semantic + negative tests | TV2 | 3 ngày | T1.3–T1.6 | `link_report.json`; Stooq/404/Default fail đúng |
| T3.2 | `reconcile` + Q4/tag switch/unit checks | TV2 | 2 ngày | T1.4, T1.6 | `reconcile_report.json`; fail đúng |
| T3.3 | `quality_flag` + `sync_log` + excluded quarters | TV2 | 1,5 ngày | T3.2 | `quality_report.json` |
| T3.4 | AI events schema + review workflow | TV2 | 1 ngày | T1.1 | Không sự kiện giả; empty state |
| T3.5 | IR manual sample 5 chỉ số/công ty | TV2 | 1 ngày | T1.4 | `ir_checks.csv`; khớp |
| T3.6 | CI: lint/test/schema/link sample/build | TV1 | 1 ngày | T3.1–T3.5 | CI xanh |
| T4.1 | Calendar mapping + Q4 derivation | TV2 | 2 ngày | T1.4 | 19 quý; residual ≤ 0,5% |
| T4.2 | YTD → quarterly GOOGL | TV2 | 1 ngày | T4.1 | Tổng 4 quý khớp năm |
| T4.3 | Tag switch resolver | TV2 | 1 ngày | T4.1 | Không gap 2025-Q2 |
| T4.4 | Wide table + 6 core metrics | TV2 | 2 ngày | T4.1–T4.3 | Khớp tính tay |
| T4.5 | ROE/ROIC/EPS/P/E | TV2 | 2 ngày | T4.4, T2.1 | Khớp tính tay; caveat |
| T4.6 | Segment break + note | TV1/TV2 | 2 ngày | T1.6, T4.1 | `segment_scheme`, `comparable=false` |
| T4.7 | JSON contracts + schema validation | TV3 | 2 ngày | T4.4–T4.6 | Schema pass; manifest |
| T4.8 | Snapshot/versioning + idempotency | TV1 | 1 ngày | T4.7 | Chạy lại giống hệt |
| T4.9 | Handoff M4: `metrics_input`, `prices_input`, `tests_input` | TV2 | 1 ngày | T4.8 | M4 đọc được; tài liệu |

**Tổng ước lượng:** ~35–40 person-day, phù hợp 3 người trong T2–T5 nếu gối đầu.

### 7.2 Lịch 9 tuần (khớp Phụ lục D)

| Tuần | Mốc | Việc chính | Bàn giao |
|---|---|---|---|
| T1 | M0 | Chốt kế hoạch, schema, concept map | Plan + config draft |
| T2 | M1 start | SEC client, submissions, companyfacts | `filings.csv`, `facts.csv` |
| T3 | M1/M2 | Segment crawler, price crawler | `segments.csv`, `prices_*.csv` |
| T4 | M2/M3 | Verify links, Nasdaq reconcile, tag switch | `link_report.json`, `reconcile_report.json` |
| T5 | M3 | Q4 derive, YTD, wide table, quality report | `company_financials.csv`, `quality_report.json` |
| T6 | M4 start | Bàn giao metrics/stats; test BT1–BT5 | `metrics_input`, `tests.json` draft |
| T7–T8 | M5–M6 | Dashboard dùng JSON; kiểm tra "Xem nguồn" | Web chạy |
| T9 | M8 | Nghiệm thu 10/10, báo cáo, slide | Bản nộp |

### 7.3 Handoff cho M4

M4 cần nhận:

1. `company_financials.csv` — wide table, mỗi ô có metadata nguồn, `quality_flag`, `verified`, `derived`.
2. `prices_processed.csv` — daily + monthly + quarterly returns; `price_source`, `source_url`.
3. `benchmark_processed.csv` — SPY/QQQ returns.
4. `segment_financials.csv` — segment scheme, `comparable`.
5. `cashflow_quarterly.csv` — CFO/CapEx đã chuyển từ YTD.
6. `excluded_quarters.csv` — quý bị loại + lý do.
7. `manifest.json` — snapshot version.
8. Tài liệu quy ước: quý lịch, adjusted close, Q4 derive, tag switch, segment break.

### 7.4 Rủi ro và cách giảm thiểu

| Rủi ro | Ảnh hưởng | Xác suất | Giảm thiểu |
|---|---|---|---|
| Stooq bị chặn | Không có nguồn giá thứ 2 như SPEC | Cao (đã xảy ra) | Dùng Nasdaq cho close **sau khi mở allowlist**; Alpha Vantage cho adjusted close nếu có key; nếu không, ghi rõ DR-04.3 chưa đạt |
| Alpha Vantage không có key/quota | Adjusted close chưa xác minh chéo | Trung bình | Xin key free; hoặc chấp nhận `adj_close_secondary=unverified` + ghi Methodology |
| yfinance đổi API/format | Pipeline giá gãy | Trung bình | Pin version; fallback Yahoo chart API/Nasdaq; snapshot |
| SEC đổi tag | Chuỗi tài chính đứt | Trung bình | Concept map + coverage report; fail closed, không điền |
| GOOGL tag switch | Mất Q2/2025 | Cao (đã xảy ra) | Resolver theo kỳ + test |
| MSFT segment break | FR-21 không đủ dữ liệu | Cao (đã xảy ra) | `segment_scheme`, `comparable=false`, ghi chú; chốt SPEC |
| Q4 derive sai | BT2–BT5 lệch | Trung bình | Residual check; loại nếu > 2% |
| Restatement | Dùng sai số | Trung bình | `is_original`, `is_restated`; audit |
| n nhỏ | Kết luận yếu | Cao | Hiển thị n + warning; không overclaim |
| IR page JS/soft-404 | Đối chiếu thủ công khó | Trung bình | Dùng SEC làm nguồn gốc; IR chỉ tham khảo |
| AI events không có nguồn | Timeline rỗng | Cao | Empty state; không bịa; review workflow |
| Dữ liệu > 5 MB/trang | NFR-04 fail | Trung bình | Tách JSON theo mã/trang; nén; chỉ series cần |

---

## 8. QUYẾT ĐỊNH CẦN CHỐT

| # | Quyết định | Đề xuất | Ảnh hưởng |
|---|---|---|---|
| D1 | Nguồn giá thứ 2 | Nasdaq API cho close; Alpha Vantage cho adjusted close nếu có key; nếu không, ghi `unverified`. **Điều kiện:** cả hai phải được thêm vào `allowlist.yaml` (CR-13) trước khi dùng | DR-04.3, Methodology |
| D2 | Cách hiển thị segment MSFT | Hiển thị lịch sử `Intelligent Cloud` đến 2026-Q2; từ 2026-Q3 hiển thị segment mới với ghi chú gãy cấu trúc; không ánh xạ | FR-21, Financial page |
| D3 | Định nghĩa cash cho ROIC | `CashCashEquivalentsAndShortTermInvestments` cho cả hai; ghi rõ loại trừ long-term investments | FR-20, ROIC |
| D4 | Allowlist cho AI events và nguồn giá | Chỉ SEC 8-K/10-Q + `microsoft.com`/`abc.xyz`; thêm `nasdaq.com`, `alphavantage.co`, `blog.google` chỉ khi nhóm đồng ý và cập nhật `allowlist.yaml` | CR-13/14 |
| D5 | P/E, EPS trong MVP hay phase 2 | Dữ liệu đã sẵn; đưa vào phase 2 cùng Decision Support (F6) | FR-31 |
| D6 | Snapshot cadence | Giá: mỗi ngày sau đóng cửa; SEC: mỗi 6 giờ trong tháng sau quý, còn lại mỗi ngày; snapshot mới khi có thay đổi | DP-03, FR-47 |
| D7 | Lưu toàn bộ companyfacts hay chỉ tag map | Cache toàn bộ JSON; `facts.csv` chỉ tag map + coverage; giảm dung lượng | CR-08, NFR-04 |
| D8 | Có dùng Stooq bằng Playwright? | **Không** trong MVP; nếu dùng phải là best-effort, không tính là verified | CR-05, DR-04.3 |

---

## PHỤ LỤC A — BẢNG BẰNG CHỨNG NGUỒN (TÓM TẮT)

| Nguồn | URL | Status | Bytes | Nội dung kiểm tra | Kết luận |
|---|---|---|---|---|---|
| SEC submissions MSFT | `data.sec.gov/submissions/CIK0000789019.json` | 200 | 185.425 | CIK/ticker/6 hồ sơ | ĐẠT |
| SEC submissions GOOGL | `data.sec.gov/submissions/CIK0001652044.json` | 200 | 152.246 | CIK/ticker/6 hồ sơ | ĐẠT |
| SEC companyfacts MSFT | `data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json` | 200 | 4.938.072 | 562 us-gaap tags | ĐẠT |
| SEC companyfacts GOOGL | `data.sec.gov/api/xbrl/companyfacts/CIK0001652044.json` | 200 | 3.249.987 | 550 us-gaap tags | ĐẠT |
| SEC companyconcept revenue MSFT | `.../companyconcept/CIK0000789019/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json` | 200 | 21.222 | 136 facts; 2026-Q3 = 92.279B | ĐẠT |
| SEC companyconcept revenue GOOGL | `.../companyconcept/CIK0001652044/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json` | 200 | 13.881 | 87 facts; dừng Q1/2025 | ĐẠT + tag switch |
| SEC index MSFT 10-Q | `sec.gov/Archives/edgar/data/789019/000119312526436133/` | 200 | 30.004 | accession trong body | ĐẠT |
| SEC index GOOGL 10-Q | `sec.gov/Archives/edgar/data/1652044/000165204426000084/` | 200 | 30.430 | accession trong body | ĐẠT |
| SEC index.json MSFT | `.../000119312526436133/index.json` | 200 | 9.611 | danh sách file | ĐẠT |
| SEC XBRL MSFT 10-Q | `.../msft-20260930_htm.xml` | 200 | 7.251.916 | segment mới | ĐẠT |
| SEC XBRL GOOGL 10-Q | `.../goog-20260930_htm.xml` | 200 | 3.161.339 | Google Cloud | ĐẠT |
| SEC XBRL MSFT 10-K | `.../msft-20260630_htm.xml` | 200 | 10.948.157 | segment cũ | ĐẠT |
| yfinance | `Ticker.history` MSFT/GOOGL/SPY/QQQ | OK | 1.214 rows/mã | Adj Close, dividends, splits | ĐẠT |
| Yahoo chart API | `query1.finance.yahoo.com/v8/finance/chart/MSFT` | 200 | 132.495 | JSON, adjclose | ĐẠT |
| Nasdaq MSFT | `api.nasdaq.com/api/quote/MSFT/historical?...` | 200 | 136.883 | 1.214 rows, close khớp | **DỮ LIỆU ĐẠT — CHỜ ALLOWLIST** |
| Nasdaq GOOGL | `.../GOOGL/historical?...` | 200 | 137.174 | 1.214 rows | **DỮ LIỆU ĐẠT — CHỜ ALLOWLIST** |
| Nasdaq SPY | `.../SPY/historical?assetclass=etf...` | 200 | 132.051 | 1.214 rows | **DỮ LIỆU ĐẠT — CHỜ ALLOWLIST** |
| Nasdaq QQQ | `.../QQQ/historical?assetclass=etf...` | 200 | 131.898 | 1.214 rows | **DỮ LIỆU ĐẠT — CHỜ ALLOWLIST** |
| Stooq CSV | `stooq.com/q/d/l/?s=msft.us&i=d` | 200 | 796 | HTML JS challenge, không CSV | **LOẠI** |
| Alpha Vantage demo | `alphavantage.co/query?...&apikey=demo` | 200 | 220 | chỉ thông báo demo key | **CHƯA ĐỦ** |
| Microsoft Source OpenAI | `news.microsoft.com/2023/01/23/...` | 404 | 125.883 | "Page not found" | **LOẠI** |
| Microsoft IR earnings | `microsoft.com/en-us/investor/earnings` | 200 | 115.049 | title "Default" | **KHÔNG DÙNG** |
| Alphabet IR earnings | `abc.xyz/investor/earnings/` | 200 | 77.539 | title hợp lệ | ĐẠT (thủ công) |
| Google Gemini blog | `blog.google/.../google-gemini-ai/` | 200 | 389.101 | title hợp lệ; domain ngoài allowlist | **CHỜ** |

---

## PHỤ LỤC B — CHECKLIST DoD GIAI ĐOẠN DỮ LIỆU

### B.1 Raw

- [ ] `filings.csv` có đủ 10-Q/10-K 2022–2026 cho MSFT/GOOGL; detect amendment.
- [ ] `facts.csv` có ≥ 12 quý/mã; mọi dòng có `accession_number`, `source_url`, `fetched_at`, `response_sha256`.
- [ ] `segments.csv` có MSFT legacy/new và GOOGL Cloud; `segment_scheme` đúng.
- [ ] `prices_*.csv` có 1.214 phiên/mã từ 2022; đủ `Adj Close`, `Dividends`, `Stock Splits`.
- [ ] `corporate_actions.csv` có GOOGL split 2022-07-18.
- [ ] `ai_events.csv` không có sự kiện nào chưa review.
- [ ] Cache `_cache/<sha256>` tồn tại cho mọi phản hồi; hash khớp.

### B.2 Preprocess

- [ ] 19 quý 2022-Q1 → 2026-Q3; không trùng, không thiếu.
- [ ] MSFT fiscal → calendar đúng; Q4 derive residual ≤ 0,5%.
- [ ] GOOGL CFO/CapEx YTD → quý đúng; tổng 4 quý khớp năm.
- [ ] GOOGL tag switch Q2/2025 không gap.
- [ ] FCF = CFO − CapEx khớp.
- [ ] R&D Intensity, CapEx Intensity, margins khớp tính tay.
- [ ] ROE/ROIC/EPS/P/E có metadata + caveat.
- [ ] GOOGL EPS Q1/2022 = 1,231 với `reported_value=24,62`, `split_adjustment=20`, `quality_flag=low`; Q2/2022 không bị chia lại; trailing EPS 2022-Q4 = 4,56.
- [ ] Segment sum ≈ consolidated; `comparable=false` tại điểm gãy MSFT.
- [ ] Mọi ô có `source_url`, `accession_number`, `xbrl_tag`, `verified`, `quality_flag`.
- [ ] Không có ô nào điền 0/ước lượng khi thiếu.

### B.3 Verification

- [ ] `link_report.json` sinh ra; core link hỏng = 0.
- [ ] Negative tests: Stooq → blocked; Microsoft Source 404 → broken; Microsoft IR "Default" → soft404.
- [ ] `reconcile_report.json` sinh ra; price diff ≤ 0,1% trên ≥ 30 ngày/mã.
- [ ] `quality_report.json` có missing/low/verified ratio.
- [ ] `manifest.json` có `schema_version`, `snapshot_version`, `generated_at`, checksum.
- [ ] 10/10 số ngẫu nhiên khớp nguồn.
- [ ] Không có hằng số tài chính trong pipeline; không LLM.
- [ ] Chạy lại cùng input → cùng output (idempotent).

### B.4 Dashboard contracts

- [ ] `overview.json`, `investor.json`, `financials.json`, `ai_analysis.json`, `decision.json`, `methodology.json`, `tests.json` đúng schema.
- [ ] Mỗi file có `schema_version`, `snapshot_version`, `generated_at`.
- [ ] Tổng dung lượng/trang ≤ 5 MB (NFR-04).
- [ ] Nút "Xem nguồn" hoạt động cho mọi số liệu.
- [ ] Trạng thái lỗi/thiếu dữ liệu hiển thị rõ, không trang trắng (UI-15).

---

## PHỤ LỤC C — CÂU HỎI MỞ CẦN NHÓM CHỐT

1. **D1:** Có xin Alpha Vantage key không, hay chấp nhận adjusted close chỉ từ yfinance và ghi "chưa xác minh chéo"?
2. **D2:** SPEC FR-21 có cập nhật để phản ánh segment MSFT mới không, hay chỉ hiển thị `Intelligent Cloud` đến 2026-Q2?
3. **D3:** Định nghĩa "Cash & Marketable Securities" dùng tag nào? Đề xuất `CashCashEquivalentsAndShortTermInvestments`.
4. **D4:** Có thêm `blog.google`/`news.microsoft.com` vào allowlist cho AI events không?
5. **D5:** P/E, EPS có nằm trong MVP hay để phase 2 (F6)?
6. **D6:** Có chấp nhận Nasdaq API (không chính thức, không SLA) làm nguồn đối chiếu chính không?
7. **D7:** Snapshot cadence: mỗi ngày hay chỉ khi có dữ liệu mới?
8. **D8:** Có cần lưu toàn bộ companyfacts JSON trong repo không, hay chỉ cache ngoài + hash?

---

## PHỤ LỤC D — TÀI LIỆU THAM CHIẾU

- `SPEC.md` — mục 1.6 (5W), 1.7 (BT1–BT5), 2.2 (F1–F11), 3.7 (CR-01..14), 3.8 (FR-48..54), 6.1 (DR-01..04), Phụ lục B.3 (công thức), Phụ lục D (lịch), Phụ lục E (milestone), Phụ lục F (cấu trúc), Phụ lục G (truy vết).
- `docs/evidence/source_verification_2026-11-04.json` — bằng chứng kiểm chứng nguồn.
- SEC EDGAR: `https://www.sec.gov/edgar/search/` (MSFT CIK 789019; GOOGL CIK 1652044).
- SEC API: `https://www.sec.gov/search-filings/edgar-application-programming-interfaces`.
- SEC Webmaster FAQ: `https://www.sec.gov/os/webmaster-faq#developers`.
- Microsoft IR: `https://www.microsoft.com/en-us/Investor/`.
- Alphabet IR: `https://abc.xyz/investor/`.
- yfinance: `https://github.com/ranaroussi/yfinance`.
- Nasdaq historical API (đối chiếu nội bộ, không chính thức): `https://api.nasdaq.com/api/quote/MSFT/historical`.
- Alpha Vantage: `https://www.alphavantage.co/documentation/`.

---

**Kết luận:** Kế hoạch này chỉ sử dụng các nguồn đã kiểm chứng thực tế tại ngày 2026-11-04. Stooq bị loại; Alpha Vantage chưa đủ điều kiện; Microsoft Source 404 là ví dụ negative; MSFT segment và GOOGL tag switch là hai điểm phải xử lý trong preprocess. Mọi số liệu xuất ra dashboard phải có `source_url`, `accession_number`, `response_sha256` và vượt qua kiểm tra 10/10 trước khi nghiệm thu.

---

## PHỤ LỤC E — CẬP NHẬT TRIỂN KHAI 2026-11-05

Mục này thay thế các dòng "CHỜ QUYẾT ĐỊNH" ở Phụ lục C cho các hạng mục đã chốt.

### E.1 Chốt allowlist CR-13 (D1, D4, D6)

| Domain | Quyết định | Phạm vi dùng | Căn cứ |
|---|---|---|---|
| `api.nasdaq.com` | **Approved** 2026-11-05 | Close chưa điều chỉnh, 30 phiên gần nhất cho MSFT/GOOGL/SPY/QQQ | Stooq chỉ trả JavaScript challenge; Nasdaq trả JSON thật khi dùng browser User-Agent |
| `blog.google` | **Approved** 2026-11-05 | Chỉ làm bằng chứng sự kiện AI | Trang chính thức của Google/Alphabet |
| `microsoft.com` (gồm `blogs.microsoft.com`) | Đã có từ trước | Bằng chứng sự kiện AI | Blog chính thức của Microsoft |
| `alphavantage.co` | **Approved có điều kiện** | Chỉ adjusted-close cross-check khi có key thật | Không chấp nhận `apikey=demo` |

`pipeline/http.py` nay **enforce** allowlist: request ra domain ngoài danh sách sẽ raise `AllowlistError` trước khi gọi mạng. Negative controls R1–R3 là ngoại lệ có chủ đích, dùng `allow_unlisted=True` và không đóng góp dữ liệu dashboard.

### E.2 Hoàn tất T2.2 — secondary close

- Crawler: `pipeline/crawlers/nasdaq.py`; artifact `data/raw/prices/nasdaq/{ticker}.json` lưu `source_url`, `http_status`, `fetched_at`, `response_sha256`, `rows`.
- So khớp 30 phiên gần nhất, ngưỡng 0,1% (`price_diff_tolerance`).
- Kết quả 2026-11-05: **30/30 phiên khớp cho cả 4 mã**; sai lệch lớn nhất: GOOGL 0,0015%, MSFT/SPY/QQQ ≤ 0,00001%.
- Reconcile: `secondary_close` chuyển từ `pending` sang `ok`; 19 check gồm 12 ok, 3 low, 0 fail, 4 unverified.

### E.3 T2.6 — adjusted close vẫn conditional

- Crawler `pipeline/crawlers/alphavantage.py` chỉ chạy khi `ALPHAVANTAGE_API_KEY` tồn tại và khác `demo`; URL lưu vào cache/report được **redact** tham số `apikey`.
- Chưa có key trong môi trường hiện tại → `secondary_adjusted_close = unverified` cho cả 4 mã; acceptance kiểm tra đúng trạng thái này thay vì giả vờ đã xác minh.
- Khi có key, cùng ngưỡng 0,1%; trạng thái sẽ là `ok`/`low`/`fail` kèm `response_sha256`.

### E.4 T3.4 — AI events CR-14

- `config/ai_events.yaml` chứa seed do con người chọn: trang chính thức, câu trích nguyên văn, ngày công bố kỳ vọng.
- `pipeline/crawlers/ai_events.py` fetch lại trang, chuẩn hoá typography, kiểm tra quote xuất hiện nguyên văn, kiểm tra `<meta article:published_time>` trùng ngày, lưu `content_sha256`.
- Bất kỳ check nào sai → event `rejected`, không vào dashboard; báo cáo ở `data/verified/ai_events_report.json`.
- Kết quả: **6/6 verified, 0 rejected** (Google Bard 2023-02-06; Gemini 1.0 2023-12-06; Gemini 1.5 2024-02-15; Microsoft–OpenAI 2023-01-23; Microsoft 365 Copilot 2023-03-16; Copilot+ PCs 2024-05-20).
- `entered_by`/`reviewed_by` là provenance rõ ràng; đây là **kiểm tra bằng chứng tự động**, không phải review biên tập của người, và được ghi như vậy trong `methodology.json` và `ai_analysis.json`.
- Empty state vẫn tồn tại cho trường hợp 0 sự kiện verified.

### E.5 Acceptance

`scripts/acceptance_check.py` nay có 31 contract check, bổ sung:

- `secondary_close_contract`: đủ 4 mã, ≥30 phiên, sai lệch ≤0,1%, có `response_sha256`.
- `adjusted_close_contract`: nếu có key thật thì MSFT/GOOGL phải ok/low kèm hash; nếu không có key thì cả 4 mã phải `unverified`.
- `ai_analysis_contract` + `ai_event_evidence`: mọi event hiển thị phải verified, có quote/hash/URL và quote thực sự có trong trang.
- `approved_allowlist_domains`: ba domain mới đã nằm trong `allowed_domains`.

Kết quả 2026-11-05: **10/10 nguồn, 31/31 contract, PASS**.

### E.6 Việc còn mở

- Chưa có Alpha Vantage key thật → adjusted close vẫn `unverified` (đúng theo thiết kế, không claim quá mức).
- Chưa có review biên tập bởi con người cho AI events; nếu nhóm cần, bổ sung bước duyệt tay và đổi `review_method` thành `human_review`.
- Nasdaq không có SLA; nếu API đổi schema, reconcile sẽ về `pending` và acceptance fail thay vì che lỗi.
