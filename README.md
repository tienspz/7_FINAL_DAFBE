# AICOR — Phân tích dữ liệu MSFT & GOOGL

Pipeline dữ liệu và bộ artifact dashboard cho hai công ty Microsoft (MSFT) và Alphabet (GOOGL), phục vụ bài phân tích tài chính — đầu tư. Mọi số liệu hiển thị đều truy vết được về nguồn gốc.

> Đây là dự án học thuật, **không phải khuyến nghị đầu tư**. Các kết luận thống kê có cỡ mẫu nhỏ (`n` nhỏ) và cần được đọc cùng phần giới hạn trong `methodology.json`.

## Phạm vi

- Cửa sổ phân tích: **2022-Q1 → 2026-Q3**, 19 quý cho mỗi công ty (38 quý).
- Báo cáo tài chính: SEC `companyfacts`/`companyconcept` và XBRL instance của 10-Q/10-K.
- Giá: Yahoo Finance chart API qua `yfinance`.
- Mỗi fact tài chính lưu `source_url`, `accession_number`, `response_sha256`, `fetched_at`.
- EPS GOOGL trước split 20:1 (kỳ kết thúc trước 2022-06-30) được điều chỉnh về hệ giá sau split; giá trị gốc vẫn được giữ trong `reported_value` và `split_adjustment`.
- Sự kiện AI chưa được xác minh sẽ không xuất hiện như dữ kiện; dashboard có empty state và cảnh báo tương ứng.

## Cấu trúc

```text
config/                 Cấu hình cửa sổ phân tích, concept map, ngưỡng chất lượng
pipeline/               Crawler, preprocess, metrics, thống kê, kiểm chứng
scripts/
  acceptance_check.py   Nghiệm thu 10 nguồn trực tiếp + contract dashboard
  ci_sync_data.py       Fingerprint ngữ nghĩa và commit dữ liệu có kiểm soát
tests/                  Unit/regression tests
data/
  raw/sec/              Filings, facts, segments (có thể tái tạo)
  raw/prices/           Corporate actions; CSV giá theo ngày bị gitignore
  verified/             Báo cáo chất lượng, reconcile, link, bảng rộng
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

Kết quả crawl nằm trong `web/public/data/`; báo cáo kiểm chứng nằm trong `data/verified/`; bằng chứng nghiệm thu nằm trong `docs/evidence/`.

Có thể đặt User-Agent riêng cho SEC (khuyến nghị khi chạy thường xuyên):

```bash
# PowerShell
$env:SEC_USER_AGENT = "AICOR research project (contact: you@example.com)"
# Bash
export SEC_USER_AGENT="AICOR research project (contact: you@example.com)"
```

## GitHub Actions — crawl hằng giờ

Workflow [`.github/workflows/hourly-crawl.yml`](.github/workflows/hourly-crawl.yml):

- Chạy theo lịch `17 * * * *` (mỗi giờ, phút 17) và hỗ trợ `workflow_dispatch`.
- `concurrency` bảo đảm không có hai lần crawl chồng lấn.
- Cài dependency pinned từ `requirements.txt`, chạy unit tests, crawl đầy đủ, rồi nghiệm thu 10/10 nguồn và toàn bộ contract.
- `permissions: contents: write` để bot có thể commit dữ liệu.
- Bot chỉ commit khi **fingerprint ngữ nghĩa** thay đổi và tối đa **một lần mỗi ngày UTC**; commit có `[skip ci]` và workflow bỏ qua thay đổi dữ liệu để tránh vòng lặp.
- Có thể bắt buộc commit khi chạy tay bằng input `force_commit` (dùng cho lần xác minh đầu tiên).

`SEC_USER_AGENT` có thể được đặt bằng repository secret cùng tên. Nếu không, workflow dùng User-Agent mô tả dự án kèm liên hệ mặc định.

## Nghiệm thu

Lần chạy gần nhất (snapshot `v20261104.10`, `data_as_of=2026-11-04`):

- **10/10** nguồn trực tiếp khớp.
- **28/28** contract dashboard pass.
- 38/38 quý, 0 missing metric cell, tỷ lệ verified `1.0`.
- 84/84 link hợp lệ; 19 reconcile check, 0 fail; 78 kết quả BT1–BT5.

Bằng chứng: [`docs/evidence/acceptance_2026-11-04.json`](docs/evidence/acceptance_2026-11-04.json). Bằng chứng điều chỉnh EPS GOOGL: [`docs/evidence/googl_eps_split_2026-11-05.json`](docs/evidence/googl_eps_split_2026-11-05.json).

## Giới hạn đã biết

- Allowlist vẫn chờ quyết định cho `api.nasdaq.com`, `alphavantage.co`, `blog.google`.
- Chưa có nguồn close thứ cấp và chưa cross-check adjusted close do thiếu Alpha Vantage key.
- Chưa có sự kiện AI nào được xác minh; `ai_analysis.json` để trống phần events và hiển thị empty state.
- Một số chỉ tiêu có `quality_flag=low` (chủ yếu do kỳ fiscal không trùng quý dương lịch hoặc dữ liệu suy ra); chi tiết trong `quality_report.json`.
