# Kế hoạch hoàn thiện crawl real data và preprocess

**Ngày:** 2026-11-06
**Phạm vi:** Raw crawl → verify → preprocess → dashboard/SQLite handoff
**Đặc tả:** [`SPEC.md`](../../SPEC.md), trọng tâm FR-40..FR-47, CR-01..CR-14 và DR-01..DR-04
**Nguyên tắc:** Giữ nguồn thật và schema hiện tại; không tự tạo hoặc nội suy số liệu; failure không được làm mất handoff hợp lệ trước đó.

## 1. Tóm tắt và hiện trạng

Pipeline đã có crawler SEC, Yahoo Finance, Nasdaq, Alpha Vantage có điều kiện, AI events; có raw cache/run archive, semantic verification, reconcile, quality report, JSON dashboard, CSV `DataProcessedView`, SQLite và bộ acceptance. Baseline tại thời điểm lập kế hoạch: `python -m pytest -q` đạt **66 passed**, snapshot hiện có `v20261105.4`, `data_as_of=2026-11-05`, 4,427 facts, 48 filings, 5,960 price rows, 461 segment rows, 38 financial quarters.

Hai khoảng trống cần đóng trước khi gọi giai đoạn này hoàn tất:

1. **Lineage bị rơi ở preprocess:** raw facts có `response_sha256`/`evidence_url`/`fetched_at`, nhưng `MetricValue` và JSON/CSV tài chính chưa giữ các trường này. Các giá trị Q4/YTD derived cũng chưa chỉ rõ đầy đủ các fact đầu vào/accession và phép tính.
2. **SQLite handoff chưa an toàn khi lỗi:** `build_sqlite` xóa database cũ trước khi tạo database mới. Lỗi giữa quá trình ghi có thể làm mất handoff đang dùng, trái NFR-15.

Full live crawl cần `SEC_USER_AGENT` có email liên hệ thật do chủ dự án cung cấp. Điều kiện này đã được đáp ứng cho lần chạy nghiệm thu bên dưới; thông tin liên hệ chỉ được dùng trong môi trường của lần chạy, không lưu trong repository.

## 2. Mục tiêu và tiêu chí hoàn thành

- Mỗi financial metric được xuất có thể truy về source URL, evidence URL, accession, fact ID, fetch timestamp và SHA-256 của phản hồi gốc.
- Metric derived chỉ được xác nhận khi mọi thành phần đầu vào đã được xác minh; output phải nêu thành phần/nguồn đầu vào, không chỉ gắn URL của một fact.
- Tạo SQLite mới theo cách thay thế nguyên tử; lỗi build giữ nguyên file SQLite hợp lệ trước đó.
- JSON/CSV contracts hiện hữu không bị phá vỡ; trường provenance mới chỉ bổ sung.
- Unit và regression tests bao phủ các đường trực tiếp, YTD, Q4, tổng component và lỗi SQLite.
- Không có test mặc định nào phụ thuộc network hay bịa giá trị để chạy production crawl.
- Live crawl/acceptance mới chỉ được đánh dấu hoàn tất sau khi có SEC contact thật và lệnh chạy end-to-end qua acceptance gate.

## 3. Ràng buộc triển khai

- Nguồn thật vẫn là SEC EDGAR, Yahoo Finance và Nasdaq theo allowlist hiện có; Alpha Vantage vẫn conditional khi có key hợp lệ.
- Không đổi công thức tài chính, cửa sổ kỳ, nguồn, ticker, ngưỡng reconcile hay UI JSON contract hiện hành.
- Không ghi đè hay làm sạch dữ liệu/thay đổi ngoài phạm vi.
- Kiểm tra acceptance không được diễn giải “chưa có key” thành adjusted-close cross-check đã xác minh.
- Không ghi credential hay contact giả vào code, tài liệu, evidence hoặc output.

## 4. Kế hoạch thực hiện

### Phase 1 — Chuẩn hóa provenance xuyên suốt preprocess

#### Plan 1.1 — Giữ raw-response lineage trong từng metric
- **Yêu cầu:** CR-02, CR-08, CR-10, DR-02, DR-04.1
- **Tệp:** `pipeline/crawlers/sec.py`, `pipeline/preprocess/facts.py`, `pipeline/run.py`
- **Thiết kế:** Truyền `fact_id`, `evidence_url`, `response_sha256`, `fetched_at` từ SEC raw fact vào `MetricValue` và JSON serialize. Xuất các thuộc tính tương ứng trong wide CSV mà không thay đổi các cột cũ.

#### Plan 1.2 — Ghi rõ dependency lineage cho giá trị derived
- **Yêu cầu:** CR-04, DR-01.6, DR-04.8
- **Tệp:** `pipeline/preprocess/facts.py`
- **Thiết kế:** Q4 phải nêu annual source và Q1–Q3; Q2/Q3 YTD phải nêu YTD fact và các quý bị trừ; phép cộng total-debt phải giữ lineage từng thành phần. Mỗi dependency mang fact ID, accession, source/evidence URL, response hash, fetch time, giá trị và đơn vị. `verified` vẫn fail-closed theo toàn bộ inputs.

### Phase 2 — Bảo vệ SQLite handoff

#### Plan 2.1 — Build SQLite staging rồi atomic replace
- **Yêu cầu:** FR-46, FR-44, NFR-15
- **Tệp:** `pipeline/run.py`, `tests/test_run.py`
- **Thiết kế:** Tạo SQLite tạm trong cùng thư mục/volume, ghi và đóng connection xong mới thay thế DB đích. Lỗi phải dọn file tạm, ném lỗi lên caller và giữ nguyên DB đích. Không thay đổi tên bảng hoặc schema handoff.

#### Plan 2.2 — Lưu run archive ngoài vòng đời GitHub runner
- **Yêu cầu:** FR-43, CR-08, NFR-15
- **Tệp:** `.github/workflows/hourly-crawl.yml`, `README.md`
- **Thiết kế:** Upload `data/raw/runs/<run_id>/` thành GitHub Actions artifact sau khi crawl hoàn tất, kể cả khi acceptance sau đó fail để phục vụ chẩn đoán. Dùng tên artifact duy nhất theo `run_id`, retention 7 ngày; không commit run archive/cache lớn vào Git.

### Phase 3 — Kiểm thử và nghiệm thu

#### Plan 3.1 — Regression tests cho lineage và failure safety
- **Yêu cầu:** CR-02, CR-04, CR-10, FR-44, FR-46, NFR-15
- **Tệp:** `tests/test_facts.py`, `tests/test_run.py`
- **Thiết kế:** Kiểm tra field provenance trên metric trực tiếp; component provenance của YTD/Q4/aggregation; lỗi ghi DB không phá DB cũ; build thành công tạo DB mới với các bảng hiện tại.

#### Plan 3.2 — Làm checksum acceptance ổn định qua Windows line endings
- **Yêu cầu:** FR-45, FR-46
- **Tệp:** `scripts/acceptance_check.py`, `tests/test_acceptance_check.py`
- **Thiết kế:** Canonicalize CRLF thành LF trước khi kiểm tra checksum JSON do pipeline ghi LF. Đây là khác biệt working-tree Windows (`core.autocrlf`) so với blob/artifact Linux, không phải sửa checksum manifest hoặc bỏ qua checksum.

#### Plan 3.3 — Xác nhận toàn pipeline mà không giả lập live success
- **Yêu cầu:** FR-40..FR-47, DR-04
- **Tệp/command:** test suite, snapshot/manifest hiện hành, `python -m pipeline.run --mode full`, `python -m scripts.acceptance_check`
- **Thiết kế:** Chạy focused tests rồi toàn bộ pytest; kiểm tra hợp đồng snapshot cục bộ. Chỉ chạy full live crawl/acceptance khi `SEC_USER_AGENT` hợp lệ đã được cung cấp; xác nhận mọi source/status, archives, checksums, reconcile, quality, JSON contracts và SQLite.

## 5. Task breakdown

### Foundational
- [x] T001 [Plan:1.1] Đối chiếu SPEC/plan hiện có với các trường lineage thực tế trong `pipeline/crawlers/sec.py`, `pipeline/preprocess/facts.py` và JSON dashboard; ghi rõ hai khoảng trống cần xử lý.
- [x] T002 [Plan:3.1] Chạy baseline `python -m pytest -q` trước thay đổi để có mốc regression (66 passed).

### Implementation
- [x] T003 [Plan:1.1] Bổ sung fact ID, evidence URL, response SHA-256 và fetched-at vào `MetricValue`, serialize JSON và wide CSV trong `pipeline/preprocess/facts.py` và `pipeline/run.py`.
- [x] T004 [Plan:1.2] Gắn provenance đầy đủ từng input và mô tả phép tính vào YTD/Q4/component-derived metrics trong `pipeline/preprocess/facts.py`; bảo toàn fail-closed verification.
- [x] T005 [Plan:3.1] Thêm test cho provenance metric trực tiếp và derived (YTD/Q4/aggregation) trong `tests/test_facts.py`.
- [x] T006 [Plan:2.1] Chuyển `build_sqlite` sang staged database + atomic replace trong `pipeline/run.py`.
- [x] T007 [Plan:3.1] Thêm test success/failure của SQLite handoff, bảo đảm database cũ không mất nếu build thất bại trong `tests/test_run.py`.
- [x] T008 [Plan:2.2] Upload immutable raw run archive thành GitHub Actions artifact có tên theo run ID và retention giới hạn trong `.github/workflows/hourly-crawl.yml`; cập nhật hướng dẫn lưu trữ trong `README.md`.
- [x] T009 [Plan:3.2] Chuẩn hóa newline khi acceptance đối chiếu checksum JSON trên Windows và thêm regression test trong `scripts/acceptance_check.py` và `tests/test_acceptance_check.py`.

### Verification
- [x] T010 [Plan:3.3] Chạy focused tests và toàn bộ `python -m pytest -q`; xử lý các regression do thay đổi.
- [x] T011 [Plan:3.3] Kiểm tra snapshot/manifest hiện có, source provenance và SQLite contract; báo cáo giới hạn live crawl nếu chưa có SEC contact thật.

## 6. Requirement mapping

| Requirement | Ý định | Plan items | Bằng chứng triển khai |
|---|---|---|---|
| CR-02, CR-08 | Giữ accession, source/evidence, hash và thời điểm fetch | 1.1, 1.2 | Raw fact → `MetricValue` → `financials.json`/CSV |
| CR-04, DR-01.6 | Q4 suy ra annual trừ Q1–Q3 và được đánh dấu rõ | 1.2 | `MetricValue.components` có nguồn annual và từng quý |
| CR-10, DR-04.1 | Chỉ dùng fact đã xác minh | 1.1, 1.2, 3.1 | Direct/derived regression tests và verified propagation |
| FR-44, NFR-15 | Ghi lỗi rõ và không làm hỏng handoff trước đó | 2.1, 3.1 | SQLite staging/failure-safety test |
| FR-43, CR-08 | Giữ raw run archive để audit sau khi runner kết thúc | 2.2 | GitHub Actions artifact `aicor-raw-<run_id>` |
| FR-45, FR-46 | Kiểm tra output/manifest contracts bền vững qua hệ điều hành | 3.2 | Checksum JSON canonical LF trên Windows và Linux |
| FR-46 | Xuất JSON/SQLite handoff cho dashboard | 1.1, 2.1, 3.3 | JSON provenance + SQLite schema/count checks |
| FR-40..FR-47, DR-04 | Crawl, verify, preprocess, acceptance theo nguồn thật | 2.2, 3.3 | Full run/acceptance khi SEC contact thật sẵn sàng |

## 7. Kiểm thử và gate

1. `python -m pytest tests/test_facts.py tests/test_run.py -q`
2. `python -m pytest -q`
3. Kiểm tra snapshot hợp đồng: 38 financial quarters, manifest/checksums, raw run archive, source sync log, SQLite tables/counts.
4. Full live run (chỉ khi có `SEC_USER_AGENT` thật): `python -m pipeline.run --mode full`, sau đó `python -m scripts.acceptance_check`.
5. Không đánh dấu live acceptance là PASS nếu thiếu contact thật, nguồn cốt lõi chưa verified, hoặc adjusted-close điều kiện chưa được ghi đúng trạng thái.

## 8. Giới hạn còn lại

- `ALPHAVANTAGE_API_KEY` chưa được cấu hình; adjusted-close cross-check vẫn phải là `unverified`.
- Workflow đã được kiểm tra cú pháp và wiring upload raw archive, nhưng retention artifact chỉ được xác nhận sau lần chạy GitHub Actions thực tế tiếp theo.
- Cache gốc và archive không được commit trực tiếp vào repository; archive của lần crawl live được giữ trong workspace hiện tại và artifact workflow sẽ có retention 7 ngày.

## 9. Kết quả thực thi

- `python -m pytest tests/test_run.py tests/test_facts.py tests/test_acceptance_check.py -q`: **15 passed**.
- `python -m pytest -q`: **70 passed**, một warning precision-loss hiện hữu trong test thống kê.
- `python -m compileall -q pipeline scripts tests`: **PASS**.
- Workflow YAML parse và raw archive upload wiring: **PASS**.
- Full live crawl: snapshot `v20261105.5`, `data_as_of=2026-11-05`, run `run_20261106T075305Z_10dd44eb`; 4,427 facts, 48 filings, 5,960 price rows, 461 segment rows và 38 financial quarters.
- Live acceptance: **10/10** source samples và **32/32** dashboard contracts PASS; 2,223/2,223 link/fact checks, 0 missing metric cells, verified ratio `1.0`, 19 reconcile checks không có lỗi, 6/6 AI events được xác minh.
- Raw archive manifest chứa 13 file; tất cả file hiện diện. SQLite handoff giữ nguyên counts của verified manifest.
- Provenance được giữ qua JSON/CSV; giá trị tổng hợp như total debt truy vết qua component fact IDs. SQLite staging replacement, lỗi staging, newline JSON checksum trên Windows và LF CSV writer có regression coverage.
- Alpha Vantage không có key nên adjusted-close check được giữ đúng trạng thái `unverified`.
- Không mở rộng scope sang sửa API/UI hoặc đổi nguồn crawl. SEC contact không được persist vào code, tài liệu hay evidence.
