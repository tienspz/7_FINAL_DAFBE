# Triển khai AICOR backend

Thư mục này chứa artifact triển khai đã kiểm tra vào repository. Host thật, DNS,
TLS, registry và secret vẫn là input của operator; không có giá trị bí mật nào
được commit.

## 1. Input cần operator cung cấp

| Input | Dùng cho | Ghi chú |
| --- | --- | --- |
| Hostname + DNS A/AAAA | `deploy/nginx.conf`, `deploy/Caddyfile` | Thay `aicor.example.com` bằng domain thật |
| TLS certificate/key | nginx | Caddy tự xin Let's Encrypt nếu DNS đã trỏ đúng |
| `CRON_SECRET` | `POST /api/refresh` | Chuỗi ngẫu nhiên dài; không đưa vào frontend |
| `AICOR_ALLOWED_ORIGINS` | CORS | Origin chính xác của frontend, phân tách bằng dấu phẩy |
| `SEC_USER_AGENT` | Pipeline local | Tên dự án + email liên hệ thật |
| `GITHUB_TOKEN_DISPATCH` + `AICOR_GITHUB_REPOSITORY` | Chế độ GitHub | Token chỉ cần `actions:write` |
| `AICOR_POST_REFRESH_COMMAND` | Chế độ GitHub | Hook đồng bộ snapshot sau khi workflow chạy xong |
| Registry credentials | Push image | `docker tag` + `docker push` do operator thực hiện |

Không dùng `AICOR_ALLOWED_ORIGINS=*` cho dashboard riêng tư. Không commit `.env`.

## 2. Chuẩn bị

```bash
cp .env.example .env
# Sửa .env: CRON_SECRET, AICOR_ALLOWED_ORIGINS, SEC_USER_AGENT, ...
docker compose build
docker compose up -d
docker compose ps
```

Compose bind backend vào `127.0.0.1:8000`; chỉ reverse proxy được public. Image
chạy bằng user `aicor` (uid 10001), có `HEALTHCHECK`, `no-new-privileges` và
drop toàn bộ Linux capabilities.

### Volume dữ liệu

Mặc định Compose dùng named volume:

- `aicor-snapshot` → `/app/web/public/data` (snapshot đã publish, backend đọc);
- `aicor-pipeline-data` → `/app/data` (raw cache, verified reports, SQLite);
- `aicor-logs` → `/app/logs` (mỗi refresh một file log).

Nếu pipeline chạy trên host (không chạy trong container), thay volume snapshot
bằng bind mount để backend thấy dữ liệu mới:

```yaml
volumes:
  - ./web/public/data:/app/web/public/data
```

Khi đó bỏ `aicor-snapshot` khỏi phần `volumes:` cuối file. Pipeline trên host
phải ghi vào đúng thư mục này.

Sao lưu định kỳ:

```bash
docker run --rm -v aicor-snapshot:/data -v "$PWD":/backup alpine \
  tar czf /backup/aicor-snapshot.tgz -C /data .
```

## 3. Reverse proxy + TLS

### nginx

```bash
sudo cp deploy/nginx.conf /etc/nginx/conf.d/aicor.conf
# Sửa server_name và đường dẫn certificate
sudo nginx -t
sudo systemctl reload nginx
```

Mẫu nginx đã gồm:

- redirect HTTP → HTTPS;
- gzip cho JSON (không gzip SSE);
- `proxy_buffering off`, `proxy_cache off`, timeout 1 giờ cho `/api/events`;
- rate limit cho API và giới hạn connection cho SSE;
- HSTS và các security header cơ bản.

### Caddy

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
# Sửa domain
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy tự động xin/gia hạn TLS; `flush_interval -1` giữ SSE không bị buffer.

## 4. Chế độ refresh

### Local pipeline (mặc định khuyến nghị)

Backend chạy `python -m pipeline.run --mode full` trong container. Cần
`SEC_USER_AGENT`; dữ liệu ghi vào volume `aicor-snapshot`, log vào `aicor-logs`.
Đây là đường production mặc định vì dữ liệu và service nằm cùng một nơi.

### GitHub Actions

Đặt `GITHUB_TOKEN_DISPATCH`, `AICOR_GITHUB_REPOSITORY`. Workflow commit dữ liệu
vào repository, **không** tự cập nhật `AICOR_DATA_DIR` của daemon. Phải đặt
`AICOR_POST_REFRESH_COMMAND` để kéo dữ liệu về trước khi backend đọc lại, ví dụ:

```dotenv
AICOR_POST_REFRESH_COMMAND=git -C /app pull --ff-only
```

Lệnh chạy sau khi workflow thành công; lỗi/timeout làm refresh `failed` và không
phát `snapshot`. Kiểm tra `GET /api/health` → `config.post_refresh_configured`.
Nếu không có hook này, `refresh_finished` có thể báo `snapshot_changed=false` dù
workflow đã chạy: dữ liệu được phục vụ vẫn là bản cũ.

## 5. Smoke test sau triển khai

```bash
BASE=https://aicor.example.com

# 1. Health và freshness
curl -fsS "$BASE/api/health" | jq '{status, version: .snapshot.snapshot_version,
  stale: .snapshot.stale, post_refresh: .config.post_refresh_configured}'

# 2. Gzip + weak ETag + Vary
curl -sD /tmp/headers -o /tmp/body.gz -H 'Accept-Encoding: gzip' \
  "$BASE/api/data/financials"
grep -Ei 'content-encoding|etag|vary' /tmp/headers

# 3. 304 với ETag vừa nhận
ETAG=$(awk 'tolower($1)=="etag:" {print $2}' /tmp/headers | tr -d '\r')
curl -s -o /dev/null -w '%{http_code}\n' -H "If-None-Match: $ETAG" \
  "$BASE/api/manifest"

# 4. SSE: phải thấy retry + ready + snapshot (Ctrl+C để thoát)
curl -N "$BASE/api/events"

# 5. Refresh (chỉ khi đã đặt CRON_SECRET)
curl -fsS -X POST -H "Authorization: Bearer $CRON_SECRET" \
  "$BASE/api/refresh?reason=deploy-smoke" | jq
```

Kỳ vọng: health `ok` (hoặc `degraded` nếu snapshot cũ), `Content-Encoding: gzip`
với dataset lớn, ETag dạng `W/"..."`, `Vary` có `Accept-Encoding` và `Origin`,
`304` cho ETag hiện tại, SSE bắt đầu bằng `ready` và có `snapshot` khi dữ liệu
đổi hoặc khi heartbeat.

## 6. Vận hành

- **Log**: `docker compose logs -f backend`; log refresh nằm trong volume
  `aicor-logs`, `detail` trên API chỉ giữ 400 ký tự cuối.
- **Restart/rollback**: `docker compose pull`/`build` rồi `docker compose up -d`.
  Volume giữ nguyên dữ liệu; rollback image không rollback snapshot.
- **Stop**: `docker compose down` (không dùng `-v` nếu muốn giữ dữ liệu).
  Backend nhận `SIGTERM`, dừng scheduler, huỷ pipeline con và đóng server.
- **Giám sát**: healthcheck Docker + `GET /api/health`; cảnh báo khi `status` là
  `degraded`/`unavailable`, khi `snapshot.stale=true`, hoặc khi
  `refresh.status=failed`.
- **Bảo mật**: chỉ mở 80/443; backend bind loopback; không log `CRON_SECRET`,
  `GITHUB_TOKEN_DISPATCH`, hay `SEC_USER_AGENT`; giới hạn SSE bằng
  `AICOR_MAX_SSE_SUBSCRIBERS` và cấu hình proxy.

## 7. Việc chưa làm (operator)

- Push image lên registry và ký/scan image.
- Cấu hình DNS, certificate, firewall của host thật.
- Chạy crawl SEC thật (cần `SEC_USER_AGENT`).
- Chạy GitHub dispatch thật (cần token + repository).
- Load test quy mô production; smoke test loopback đã có trong CI/verification.
