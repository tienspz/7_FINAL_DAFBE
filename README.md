# AICOR — Phân tích dữ liệu MSFT & GOOGL

Pipeline dữ liệu và bộ artifact dashboard cho hai công ty Microsoft (MSFT) và Alphabet (GOOGL), phục vụ bài phân tích tài chính — đầu tư. Mọi số liệu hiển thị đều truy vết được về nguồn gốc.

> Đây là dự án học thuật, **không phải khuyến nghị đầu tư**. Các kết luận thống kê có cỡ mẫu nhỏ (`n` nhỏ) và cần được đọc cùng phần giới hạn trong `methodology.json`.

## Phạm vi

- Cửa sổ phân tích: **2022-Q1 → 2026-Q3**, 19 quý cho mỗi công ty (38 quý).
- Báo cáo tài chính: SEC `companyfacts`/`companyconcept` và XBRL instance của 10-Q/10-K.
- Giá: Yahoo Finance chart API qua `yfinance` (nguồn chính); **Nasdaq historical API** đối chiếu close chưa điều chỉnh cho 30 phiên gần nhất của MSFT, GOOGL, SPY, QQQ.
- Adjusted close: đối chiếu Alpha Vantage **chỉ khi có key thật** trong `ALPHAVANTAGE_API_KEY`; không dùng `apikey=demo`.
- Mỗi fact tài chính lưu `source_url`, `accession_number`, `response_sha256`, `fetched_at`.
- EPS GOOGL trước split 20:1 (kỳ kết thúc trước 2022-06-30) được điều chỉnh về hệ giá sau split; giá trị gốc vẫn được giữ trong `reported_value` và `split_adjustment`.
- Sự kiện AI (CR-14) chỉ lấy từ trang chính thức của Google/Microsoft; mỗi sự kiện phải có `evidence_quote` xuất hiện nguyên văn trong trang, đúng ngày công bố, kèm `content_sha256`, `entered_by`, `reviewed_by`. Sự kiện không vượt kiểm tra sẽ bị loại và dashboard hiển thị empty state.

## Cấu trúc

```text
config/
  allowlist.yaml        CR-13: domain được phép, quyết định duyệt 2026-11-05
  ai_events.yaml        CR-14: seed sự kiện AI từ trang chính thức
  concept_map.yaml      Tag XBRL, split adjustment
  source_registry.yaml  S15/S18/S19/S20 và negative controls
pipeline/
  crawlers/nasdaq.py    Secondary close + artifact có hash
  crawlers/alphavantage.py  Adjusted close có điều kiện key
  crawlers/ai_events.py Kiểm tra quote/ngày/hash trước khi hiển thị
  http.py               CachedHttpClient + enforce allowlist CR-13
scripts/
  acceptance_check.py   10 nguồn trực tiếp + 31 contract dashboard
  ci_sync_data.py       Fingerprint ngữ nghĩa và commit dữ liệu có kiểm soát
tests/                  Unit/regression tests
data/
  raw/sec/              Filings, facts, segments (có thể tái tạo)
  raw/prices/           Corporate actions, artifact Nasdaq/Alpha Vantage
  verified/             Báo cáo chất lượng, reconcile, link, AI event report
web/public/data/        JSON dashboard + manifest/checksum
docs/                   Kế hoạch và bằng chứng nghiệm thu
.github/workflows/      Crawl tự động hằng giờ
```

Các thư mục sinh tự động như `data/raw/_cache`, `data/db`, `data/snapshots`, CSV giá theo ngày và `data/verified/prices_processed.csv` không được commit.

## Chạy local

Yêu cầu Python 3.14 (hoặc phiên bản tương thích) và Git.

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m pipeline.run --mode full
python scripts/acceptance_check.py
```

`python -m pipeline.run --mode full` crawl raw rồi preprocess trong **cùng một lần chạy**: SEC filings/facts/segments, giá yfinance, close Nasdaq, adjusted close có điều kiện, sự kiện AI, reconcile, quality report, rồi ghi JSON dashboard + SQLite handoff.

Có thể đặt User-Agent riêng cho SEC (khuyến nghị khi chạy thường xuyên):

```bash
# PowerShell
$env:SEC_USER_AGENT = "AICOR research project (contact: you@example.com)"
# Bash
export SEC_USER_AGENT="AICOR research project (contact: you@example.com)"
```

Muốn bật đối chiếu adjusted close, đặt key thật (không dùng key demo):

```bash
# PowerShell
$env:ALPHAVANTAGE_API_KEY = "<real-key>"
# Bash
export ALPHAVANTAGE_API_KEY="<real-key>"
```

## GitHub Actions — crawl hằng giờ

Workflow [`.github/workflows/hourly-crawl.yml`](.github/workflows/hourly-crawl.yml):

- Chạy theo lịch `17 * * * *` (mỗi giờ, phút 17) và hỗ trợ `workflow_dispatch`.
- `concurrency` bảo đảm không có hai lần crawl chồng lấn.
- Cài dependency pinned từ `requirements.txt`, chạy unit tests, crawl đầy đủ (raw + preprocess), rồi nghiệm thu 10/10 nguồn và toàn bộ contract.
- `permissions: contents: write` để bot có thể commit dữ liệu.
- Bot chỉ commit khi **fingerprint ngữ nghĩa** thay đổi và tối đa **một lần mỗi ngày UTC**; commit có `[skip ci]` và workflow bỏ qua thay đổi dữ liệu để tránh vòng lặp.
- Có thể bắt buộc commit khi chạy tay bằng input `force_commit`.
- Secret tùy chọn: `SEC_USER_AGENT`, `ALPHAVANTAGE_API_KEY`. Khi thiếu key Alpha Vantage, check adjusted close được ghi `unverified` thay vì fail.

## Nghiệm thu

Lần chạy gần nhất (snapshot `v20261104.11`, `data_as_of=2026-11-04`):

- **10/10** nguồn trực tiếp khớp; **31/31** contract dashboard pass.
- **Secondary close**: 30/30 phiên khớp Nasdaq cho cả MSFT, GOOGL, SPY, QQQ; sai lệch lớn nhất 0,0015% (ngưỡng 0,1%).
- **Adjusted close**: `unverified` cho cả 4 mã vì chưa có key Alpha Vantage thật.
- **AI events**: 6/6 sự kiện được kiểm chứng từ trang chính thức (3 Google, 3 Microsoft), 0 bị loại.
- 38/38 quý, 0 missing metric cell, tỷ lệ verified `1.0`.
- 84/84 link hợp lệ; 19 reconcile check (12 ok, 3 low, 0 fail, 4 unverified); 78 kết quả BT1–BT5.

Bằng chứng: [`docs/evidence/acceptance_2026-11-04.json`](docs/evidence/acceptance_2026-11-04.json), [`docs/evidence/pending_completion_2026-11-05.json`](docs/evidence/pending_completion_2026-11-05.json). Bằng chứng điều chỉnh EPS GOOGL: [`docs/evidence/googl_eps_split_2026-11-05.json`](docs/evidence/googl_eps_split_2026-11-05.json).

## Giới hạn đã biết

- Adjusted close chưa được xác minh chéo vì chưa có Alpha Vantage key thật; demo key bị loại.
- Nasdaq API là nguồn không chính thức, không SLA; đối chiếu chỉ 30 phiên gần nhất.
- Sự kiện AI được duyệt bằng kiểm tra bằng chứng tự động (quote + ngày + hash), **không phải review biên tập của con người**; chúng chỉ là bối cảnh, không phải tín hiệu đầu tư.
- Stooq vẫn bị chặn bởi JavaScript challenge; negative control R1 giữ nguyên để ghi nhận.
- Một số chỉ tiêu có `quality_flag=low` (chủ yếu do kỳ fiscal không trùng quý dương lịch hoặc dữ liệu suy ra); chi tiết trong `quality_report.json`.
- Toàn bộ phân tích dùng cỡ mẫu nhỏ; không đưa ra khuyến nghị đầu tư.
