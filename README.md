# AICOR — Phân tích dữ liệu MSFT & GOOGL

Pipeline dữ liệu và bộ artifact dashboard cho hai công ty Microsoft (MSFT) và Alphabet (GOOGL), phục vụ bài phân tích tài chính — đầu tư. Mọi số liệu hiển thị đều truy vết được về nguồn gốc.

> Đây là dự án học thuật, **không phải khuyến nghị đầu tư**. Các kết luận thống kê có cỡ mẫu nhỏ (`n` nhỏ) và cần được đọc cùng phần giới hạn trong `methodology.json`.

## Phạm vi

- Cửa sổ phân tích: **2022-Q1 → 2026-Q3**, 19 quý cho mỗi công ty (38 quý).
- Báo cáo tài chính: SEC `companyfacts`/`companyconcept` và XBRL instance của 10-Q/10-K.
- Giá: Yahoo Finance chart API qua `yfinance` (nguồn chính); **Nasdaq historical API** đối chiếu close chưa điều chỉnh cho 30 phiên gần nhất của MSFT, GOOGL, SPY, QQQ.
- Adjusted close: đối chiếu Tiingo cho MSFT, GOOGL, SPY và QQQ **chỉ khi có token thật** trong `TIINGO_API_KEY`; thiếu token/rows vẫn là `unverified`.
- Mỗi fact tài chính lưu `source_url`, `accession_number`, `response_sha256`, `fetched_at`.
- EPS GOOGL trước split 20:1 (kỳ kết thúc trước 2022-06-30) được điều chỉnh về hệ giá sau split; giá trị gốc vẫn được giữ trong `reported_value` và `split_adjustment`.
- Sự kiện AI (CR-14) chỉ lấy từ trang chính thức của Google/Microsoft; mỗi sự kiện phải có `evidence_quote` xuất hiện nguyên văn trong trang, đúng ngày công bố, kèm `content_sha256`, `entered_by`, `reviewed_by`. Sự kiện không vượt kiểm tra sẽ bị loại và dashboard hiển thị empty state.

## Cấu trúc

```text
config/
  allowlist.yaml        CR-13: domain được phép, quyết định duyệt 2026-11-05
  ai_events.yaml        CR-14: seed sự kiện AI từ trang chính thức
  concept_map.yaml      Tag XBRL, split adjustment
  source_registry.yaml  S15/S18-S21 và negative controls
pipeline/
  crawlers/nasdaq.py    Secondary close + artifact có hash
  crawlers/tiingo.py   Adjusted close có điều kiện token
  crawlers/ai_events.py Kiểm tra quote/ngày/hash trước khi hiển thị
  http.py               CachedHttpClient + enforce allowlist CR-13
  sync.py               Sync log theo nguồn + raw archive bất biến theo run
scripts/
  acceptance_check.py   10 nguồn trực tiếp + 41 contract dashboard
  ci_sync_data.py       Fingerprint ngữ nghĩa và commit dữ liệu có kiểm soát
tests/                  Unit/regression tests
data/
  raw/sec/              Filings, facts, segments (có thể tái tạo)
  raw/prices/           Corporate actions, artifact Nasdaq/Tiingo
  verified/             Báo cáo chất lượng, reconcile, link, sync log
web/public/data/        JSON dashboard + manifest/checksum
web/                    React + TypeScript dashboard (Vite)
DataProcessedView/      CSV dạng bảng sinh tự động từ các JSON dashboard
docs/                   Đặc tả frontend, kế hoạch và bằng chứng nghiệm thu
.github/workflows/      Crawl tự động hằng giờ
```

Các thư mục sinh tự động như `data/raw/_cache`, `data/raw/runs`, `data/db`, `data/snapshots`, CSV giá theo ngày và `data/verified/prices_processed.csv` không được commit. Với GitHub Actions, mỗi crawl thành công upload `data/raw/runs/<run_id>/` thành artifact `aicor-raw-<run_id>` giữ trong 7 ngày; crawl local giữ archive tại môi trường chạy. `sync_log.jsonl` được giữ trong các commit dữ liệu định kỳ.

## Chạy local

Yêu cầu Python 3.14 (hoặc phiên bản tương thích) và Git.

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m pipeline.run --mode full
python -m scripts.acceptance_check
```

`python -m pipeline.run --mode full` crawl raw rồi preprocess trong **cùng một lần chạy**: SEC filings/facts/segments, giá yfinance, close Nasdaq, adjusted close có điều kiện, sự kiện AI, reconcile, quality report, rồi ghi JSON dashboard + SQLite handoff. Dữ liệu mutable SEC/Yahoo/Nasdaq/Tiingo có cache tối đa 55 phút; filing archive bất biến dùng cache lâu dài. SEC requests được giãn cách tối thiểu 0,2 giây (tối đa 5 requests/giây); yfinance lấy tuần tự, cách nhau ít nhất 1 giây. Mỗi fact XBRL được đối chiếu theo accession, kỳ, đơn vị và giá trị trước khi đưa vào số liệu đã xác minh. Raw artifact được archive theo `run_id`; `manifest.json` gắn `run_id` với handoff và sync log.

Sau khi tạo JSON dashboard, pipeline tự xuất mỗi mảng bản ghi thành một CSV trong `DataProcessedView/` (ví dụ `financials__quarters.csv` và `prices/GOOGL__rows.csv`). Các object lồng nhau được trải thành cột có tên phân cấp như `metrics.revenue`; mỗi lần chạy cập nhật CSV và dọn các CSV sinh ra trước đó mà không còn nguồn tương ứng. CSV dùng UTF-8 có BOM để Excel hiển thị tiếng Việt đúng hơn; JSON dashboard vẫn được giữ nguyên.

Nếu cần cập nhật riêng kết quả thống kê từ snapshot đã xác minh mà không crawl lại nguồn, chạy `python -m scripts.rebuild_stats`; lệnh giữ nguyên snapshot/run/date, quality mode và provenance tài chính, rồi cập nhật checksum trong cả hai manifest. Dùng `python -m scripts.rebuild_stats --check` để kiểm tra tính tái lập mà không ghi file. Đây không thay thế live crawl hoặc acceptance nguồn trực tiếp.

Mỗi financial metric trong `financials.json` và `quality_report.json` mang theo fact ID (hoặc danh sách component fact ID với metric tổng hợp), source/evidence URL, response SHA-256, thời điểm fetch, accession và trạng thái xác minh. Metric suy ra từ YTD/Q4 hoặc phép cộng component cũng ghi rõ phương pháp và các đầu vào để truy vết xuyên suốt preprocess. Wide CSV chứa cùng provenance cấp metric. SQLite được ghi vào file staging và chỉ thay thế handoff trước đó sau khi database mới vượt `integrity_check`, đủ bảng cho các tập dữ liệu có dòng, khớp số dòng đầu vào và có metadata duy nhất trong `handoff_metadata` (`schema_version`, `run_id`, `snapshot_version`, `data_as_of`, `generated_at`). Acceptance đối chiếu metadata này với manifest để phát hiện DB cũ dù số dòng trùng; lỗi build không làm mất database đang dùng.

Có thể đặt User-Agent riêng cho SEC (khuyến nghị khi chạy thường xuyên):

```bash
# PowerShell
$env:SEC_USER_AGENT = "AICOR research project (contact: <contact-address>)"
# Bash
export SEC_USER_AGENT="AICOR research project (contact: <contact-address>)"
```

Muốn bật đối chiếu adjusted close qua Tiingo, đặt API token thật:

```bash
# PowerShell
$env:TIINGO_API_KEY = "<real-token>"
# Bash
export TIINGO_API_KEY="<real-token>"
```

Token chỉ được gửi qua header `Authorization`, không nằm trong URL, cache index hay artifact. Không commit token; GitHub Actions dùng repository secret `TIINGO_API_KEY` nếu bật kiểm tra live.

## Backend service — API, realtime, tự cập nhật

`backend/` là service Python (chỉ thư viện chuẩn) phục vụ snapshot đã publish, tự kiểm tra độ tươi và làm mới dữ liệu trong nền. Service không ghi vào `web/public/data`; mọi thay đổi dữ liệu vẫn do pipeline và GitHub Actions thực hiện.

```bash
python -m backend                              # API + scheduler chạy ngầm
python -m backend --no-auto-refresh --port 8000
```

| Endpoint | Mô tả |
|---|---|
| `GET /api/health` | trạng thái service, phiên bản snapshot, `data_as_of`, tuổi dữ liệu, checksum, tiến trình refresh; `degraded` khi dữ liệu cũ hoặc `generated_at` thiếu/không parse được, `503` khi thiếu manifest |
| `GET /api/manifest` | manifest gốc kèm weak `ETag` và `If-None-Match` |
| `GET /api/latest` | freshness + manifest + `overview` + `decision`; mỗi tài liệu chỉ được nhúng sau khi khớp SHA-256 với manifest |
| `GET /api/data/<key>` | JSON đã đối chiếu SHA-256 với manifest; sai lệch trả `502` |
| `GET /api/events` | SSE: `ready`, `snapshot`, `refresh`, `refresh_finished`, `scheduler_error` |
| `GET\|POST /api/refresh` | kích hoạt crawl, bắt buộc `CRON_SECRET`; `409` khi đang chạy |

Response JSON từ 1024 byte được gzip khi client gửi `Accept-Encoding: gzip`; response nén gửi `Vary: Accept-Encoding`. Manifest và dataset dùng weak `ETag` (`W/"<sha256>"`) trên body gốc, nên `304` vẫn đúng với cả representation gzip. Khi `AICOR_ALLOWED_ORIGINS` không phải `*`, mọi response gửi `Vary: Origin`, kể cả request không có `Origin` hoặc origin bị từ chối.

Scheduler kiểm tra mỗi `AICOR_REFRESH_INTERVAL_SECONDS` (mặc định 900 giây). Khi `generated_at` cũ hơn `AICOR_STALE_AFTER_SECONDS` (mặc định 21600 giây), thiếu/không parse được, hoặc manifest thiếu, service chạy `python -m pipeline.run --mode full`; nếu có `GITHUB_TOKEN_DISPATCH` và `AICOR_GITHUB_REPOSITORY` thì gọi `workflow_dispatch` thay vì crawl local. Mỗi thời điểm chỉ một refresh chạy. `CRON_SECRET` chưa cấu hình thì endpoint refresh trả `503`, không mở công khai.

Mỗi lần refresh local, toàn bộ output của pipeline được ghi vào `AICOR_LOG_DIR` (mặc định `logs/backend-refresh-<job_id>.log`); `detail` trong `/api/health` chỉ giữ 400 ký tự cuối. Ở chế độ GitHub, `succeeded` chỉ xuất hiện khi workflow run đã thực sự kết thúc (`completed: success`): backend poll run mỗi `AICOR_GITHUB_POLL_SECONDS` và báo `failed` nếu run thất bại, bị huỷ hoặc vượt `AICOR_REFRESH_TIMEOUT_SECONDS`. Workflow GitHub commit dữ liệu vào repository chứ không tự cập nhật `AICOR_DATA_DIR` của daemon; đặt `AICOR_POST_REFRESH_COMMAND` (ví dụ `git pull --ff-only`) để đồng bộ trước khi backend đọc lại snapshot. Lệnh này chạy sau khi dispatch thành công; lỗi hoặc timeout làm refresh `failed` và không phát event `snapshot`.

Mọi event `snapshot` dùng cùng một envelope `{"snapshot": <freshness>, "changed": <bool>}`, bất kể do runner, scheduler hay heartbeat phát. Một refresh thành công phát event `snapshot` rồi `refresh_finished` mang theo `snapshot_changed` (`true`/`false`/`null`). Frontend nên so sánh `snapshot.snapshot_version` để tránh xử lý trùng.

`SIGTERM`/`SIGINT` dừng scheduler, huỷ pipeline con đang chạy (kill cả cây tiến trình) rồi đóng server. Số SSE client đồng thời bị giới hạn bởi `AICOR_MAX_SSE_SUBSCRIBERS` (mặc định 128). Nếu không có event nào trong `AICOR_SSE_HEARTBEAT_SECONDS`, server gửi một event `snapshot` với `changed=false` để client chậm tự đồng bộ lại. `HEAD` trả cùng header với `GET` nhưng không có body và không bao giờ kích hoạt refresh.

Frontend trên Vercel: trỏ `VITE_AICOR_API_BASE` về origin của service, đọc `/api/latest` với `cache: "no-store"`, và mở `EventSource(<base>/api/events)` để nhận snapshot mới mà không cần tải lại trang. Thêm domain Vercel vào `AICOR_ALLOWED_ORIGINS`; CORS chỉ chấp nhận origin trong danh sách. Vercel Cron hoặc cron ngoài có thể gọi `GET /api/refresh` với `Authorization: Bearer <CRON_SECRET>` hoặc `X-Cron-Secret` khi cần làm mới ngay. Hợp đồng HTTP/SSE và type frontend nằm trong [`docs/api/README.md`](docs/api/README.md), [`docs/api/openapi.yaml`](docs/api/openapi.yaml), [`docs/api/sse-events.schema.json`](docs/api/sse-events.schema.json) và [`docs/api/types.ts`](docs/api/types.ts). Biến môi trường liệt kê trong `.env.example`.

## Frontend — dashboard

Ứng dụng React + TypeScript trong `web/` có sáu trang: tổng quan, lợi suất
cổ đông, tài chính, đầu tư AI, quyết định và phương pháp. Frontend dùng snapshot
JSON trong `web/public/data/` làm fallback; khi backend khả dụng, Vite proxy
chuyển tiếp `/api/*` tới `http://127.0.0.1:8000`.

Chạy backend trong một terminal từ thư mục gốc (tùy chọn nếu chỉ cần dữ liệu
fallback):

```powershell
python -m backend
```

Chạy giao diện trong terminal khác:

```powershell
Set-Location web
npm ci
npm run dev
```

Mở URL Vite hiển thị trong terminal (mặc định `http://localhost:5173`). Kiểm
tra frontend:

```powershell
npm run typecheck
npm test
npm run test:e2e
npm run build
```

Xem [hướng dẫn frontend](web/README.md), [brief và đặc tả](docs/FRONTEND_BRIEF.md),
[báo cáo bàn giao](web/FINAL_REPORT.md) và [các giới hạn còn lại](web/GAPS.md)
để biết chi tiết về cách chạy, kiểm chứng và trạng thái triển khai.

### Chạy bằng container

```bash
docker build -t aicor-backend .
docker run --rm -p 8000:8000 --env-file .env aicor-backend
```

Hoặc chạy bằng Compose với volume bền cho dữ liệu và log:

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

Image chạy bằng user không phải root và có `HEALTHCHECK` gọi `/api/health`. Trong image, `AICOR_HOST=0.0.0.0` và `AICOR_DATA_DIR=/app/web/public/data`; thêm origin thật của frontend vào `AICOR_ALLOWED_ORIGINS`. `docker-compose.yml` bind cổng vào `127.0.0.1` để reverse proxy trên host phục vụ TLS; mẫu nginx/Caddy, checklist triển khai và smoke test nằm trong [`deploy/README.md`](deploy/README.md). Khi pipeline chạy trên host thay vì trong container, đổi named volume `aicor-data` thành bind mount `./web/public/data:/app/web/public/data` để backend thấy snapshot mới. Workflow `ci.yml` chạy compile và toàn bộ pytest trên mỗi push/PR; kế hoạch hoàn thiện nằm trong [`docs/plans/backend-frontend-readiness/plan.md`](docs/plans/backend-frontend-readiness/plan.md).

## GitHub Actions — crawl hằng giờ

Workflow [`.github/workflows/hourly-crawl.yml`](.github/workflows/hourly-crawl.yml):

- Chạy theo lịch `17 * * * *` (mỗi giờ, phút 17) và hỗ trợ `workflow_dispatch`.
- Nguồn mutable được làm mới khi cache quá 55 phút; các filing archive bất biến không bị tải lại mỗi giờ.
- SEC request pacing tối đa 5/giây; Yahoo ticker requests chạy tuần tự, cách nhau ít nhất một giây.
- `concurrency` bảo đảm không có hai lần crawl chồng lấn.
- Cài dependency pinned từ `requirements.txt`, chạy unit tests, crawl đầy đủ (raw + preprocess), rồi nghiệm thu 10/10 nguồn và toàn bộ contract.
- `permissions: contents: write` để bot có thể commit dữ liệu.
- Bot chỉ commit khi **fingerprint ngữ nghĩa** thay đổi và tối đa **một lần mỗi ngày UTC**; commit có `[skip ci]` và workflow bỏ qua thay đổi dữ liệu để tránh vòng lặp.
- Có thể bắt buộc commit khi chạy tay bằng input `force_commit`.
- Secret: `SEC_USER_AGENT` phải có tên dự án và email liên hệ thật; workflow dừng rõ ràng nếu chưa cấu hình bằng GitHub Secret. Tạo **repository secret** tại **Settings → Secrets and variables → Actions → New repository secret**, đặt tên chính xác `SEC_USER_AGENT` và giá trị theo dạng `AICOR research project (contact: email-liên-hệ-thật)`. Không commit giá trị này vào mã nguồn; pipeline không dùng địa chỉ liên hệ giả. Sau khi thêm secret, push tiếp theo hoặc chạy thủ công **Actions → Hourly data crawl → Run workflow** sẽ kích hoạt lại crawler. `TIINGO_API_KEY` là tùy chọn; khi thiếu token, adjusted-close check được ghi `unverified`.
- `data/verified/sync_log.jsonl` lưu thời gian, nguồn, trạng thái, số dòng và thông tin lỗi; acceptance kiểm tra sync log và checksum raw archive theo `run_id`.

## Kiểm định thống kê

- Chế độ chất lượng chính là **B** (`label_low`): giữ các quý suy ra có `identity_ok=true` và gắn nhãn; quý `low` vì lý do khác vẫn bị loại. Chế độ **A** (`exclude_low`) là phân tích độ nhạy. Đây là lựa chọn phân tích có thể đổi, không phải thay đổi dữ liệu gốc (CR-04, DR-04.8, FR-52).
- BT4/BT5 lưu hai họ Holm: họ theo lag (m=5) và họ toàn bộ BT của công ty (BT4 m=30, BT5 m=5). Quyết định dùng họ nghiêm hơn; kết quả không bền qua level/sai phân/hoán vị được ghi `fragile=true` và `exploratory=true`, không gọi là bác bỏ.
- BT3 tách `trend_on_level` (HAC) và `drift_on_difference`, thêm bootstrap khối; p hiển thị dưới 0,001 là `< 0.001`, còn `p_value_raw` giữ số thô. GOOGL `capex_intensity` không dừng sau sai phân được đánh dấu `unreliable_nonstationary=true` và không dùng để kết luận.
- Không có kết luận nhân quả; mọi kết quả có n nhỏ chỉ mang tính tham khảo, không phải khuyến nghị đầu tư.

## Nghiệm thu

Lần chạy gần nhất (snapshot `v20261106.5`, `data_as_of=2026-11-06`, run `run_20261107T122003Z_a523f1b1`):

- **10/10** mẫu nguồn trực tiếp khớp; **42/42** contract dashboard pass trong acceptance live ngày 2026-11-07.
- Pipeline live hoàn tất với 4.677 facts, 48 filings, 5.964 price rows, 461 segment rows, 38 financial quarters; 0 missing metric cell và `verified_ratio=1.0`.
- **Secondary close**: 30/30 phiên ngẫu nhiên (seed `20261104`) khớp Nasdaq cho MSFT, GOOGL, SPY, QQQ; sai lệch tương đối lớn nhất 5,8e-08 (0,0000058%).
- **Adjusted close**: Alpha Vantage free không truy cập được endpoint adjusted; pipeline chuyển sang Tiingo daily prices. Kết quả live Tiingo được ghi riêng trong evidence mới và chỉ đổi từ `unverified` khi có đủ ngày so sánh, tolerance đạt, cùng SHA-256/source URL.
- **Tiingo live cross-check (bổ sung, không phải full crawl)**: trên snapshot `v20261106.5`, 30/30 phiên của MSFT và GOOGL đều đạt tolerance 0,1%; sai lệch tương đối lớn nhất lần lượt `8,783e-06` và `7,243e-06`. Evidence: [`docs/evidence/adjusted_close_tiingo_2026-11-07.json`](docs/evidence/adjusted_close_tiingo_2026-11-07.json). Bằng chứng này chỉ xác nhận đối chiếu adjusted-close, không thay thế acceptance 10/10 nguồn của full crawl.
- **AI events**: 18/18 sự kiện được kiểm chứng tự động (10 Google, 8 Microsoft), 0 bị loại; đây là kiểm tra quote/ngày/hash tự động, không phải review biên tập.
- 2.351/2.351 link và fact checks hợp lệ; 21 reconcile check (14 ok, 3 low, 0 fail, 4 unverified); 79 kết quả BT1–BT5, có ADF, n hiệu dụng, `excluded_quarters` và so sánh chế độ A/B.

Bằng chứng live mới nhất: [`docs/evidence/acceptance_2026-11-06.json`](docs/evidence/acceptance_2026-11-06.json); evidence filename theo `data_as_of` (2026-11-06), nội dung ghi thời gian kiểm tra 2026-11-07. Các bằng chứng trước đó: [`docs/evidence/independent_recheck.json`](docs/evidence/independent_recheck.json), [`docs/evidence/quality_evidence.json`](docs/evidence/quality_evidence.json). Bằng chứng điều chỉnh EPS GOOGL: [`docs/evidence/googl_eps_split_2026-11-05.json`](docs/evidence/googl_eps_split_2026-11-05.json).

## Giới hạn đã biết

- Alpha Vantage free không thể truy cập `TIME_SERIES_DAILY_ADJUSTED`; đối chiếu adjusted-close hiện dùng Tiingo khi có `TIINGO_API_KEY`. Nếu thiếu token hoặc provider không trả đủ dữ liệu, trạng thái vẫn là `unverified`, không được tính là xác minh.
- Quý Q2/Q3 của GOOGL suy từ YTD chỉ được kiểm tra bằng identity số học (tổng các thành phần khớp số YTD); 10-Q không công bố số 3 tháng độc lập để đối chiếu.
- MSFT Intelligent Cloud còn 18/19 quý theo scheme cũ; scheme mới chỉ có 2 điểm (2025-Q3, 2026-Q3) và được đánh dấu `comparable=false`, không ghép với scheme cũ.
- GOOGL capex_intensity vẫn không dừng sau sai phân bậc 1 (ADF p≈0,99); p-value HAC với n=9 chỉ để tham khảo.
- Nasdaq API là nguồn không chính thức, không SLA; đối chiếu chỉ 30 phiên gần nhất.
- Nasdaq chỉ là nguồn đối chiếu cửa sổ gần đây, không thể thay yfinance làm nguồn giá lịch sử đầy đủ khi yfinance lỗi.
- Sự kiện AI được duyệt bằng kiểm tra bằng chứng tự động (quote + ngày + hash), **không phải review biên tập của con người**; chúng chỉ là bối cảnh, không phải tín hiệu đầu tư.
- Stooq vẫn bị chặn bởi JavaScript challenge; negative control R1 giữ nguyên để ghi nhận.
- Một số chỉ tiêu có `quality_flag=low` (chủ yếu do kỳ fiscal không trùng quý dương lịch hoặc dữ liệu suy ra); chi tiết trong `quality_report.json`.
- Toàn bộ phân tích dùng cỡ mẫu nhỏ; không đưa ra khuyến nghị đầu tư.
