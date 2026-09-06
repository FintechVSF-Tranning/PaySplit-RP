# PaySplit — Tài liệu Luồng hoạt động (Flows)

Thư mục này mô tả **luồng hoạt động end-to-end** của từng module/màn hình trong hệ sinh thái PaySplit, bao gồm cả Backend (Go) và Frontend (Flutter). Mỗi file mở bằng **vấn đề và ý tưởng**, rồi bảng tổng quan, sequence/activity (Mermaid), edge cases, ghi chú chỗ dễ làm sai, và trạng thái hiện tại — cùng giọng với [`08-realtime.md`](08-realtime.md).

> **Đối chiếu ngày 06/09/2026**: BE `7f2b2a7`, FE `fb0cf0b` (bao gồm bản sửa proof `59a5aaa`). Phạm vi là mã nguồn local, API contract và test; không suy ra trạng thái production. Xem [báo cáo đối chiếu và giới hạn kiểm chứng](reports/2026-09-06-flow-sync.md).

> Nguồn tham chiếu: mã nguồn thực tế tại `PaySplit-BE/` và `PaySplit-FE/` tại thời điểm viết. Chỗ lệch với OpenAPI hay comment cũ trong code được ghi rõ, không lấy tài liệu cũ làm nguồn sự thật.

---

## 📂 Danh mục tài liệu

| # | File | Phạm vi | Nội dung chính |
|---|------|---------|----------------|
| 01 | [`01-auth.md`](01-auth.md) | Module Auth (`/auth`, `/users`) + màn hình Welcome / Register / Verify OTP / Login / Forgot & Reset Password / Profile | Một người một phiên, cửa khóa trước bcrypt, OTP chống enumeration, refresh dùng chung với SSE (`SessionRefresher`), quên/đổi mật khẩu khác phạm vi đá phiên, avatar, bank |
| 02 | [`02-group.md`](02-group.md) | Module Group (`/groups`) + màn hình Groups / Scan QR / Join by Link / Create Group / Add Members / Group Detail Hub | Anti-enumeration, khóa hàng nhóm, invite Base62, camera QR thật, 4 tab API thật, khóa/mở nộp bill, realtime user stream + vá list tại chỗ |
| 03 | [`03-bill.md`](03-bill.md) | Module Bill (`/bills`, group close) + màn hình Bill Capture / Bill Detail | Chia tiền largest remainder (không dồn creditor), OCR 202 + `ocr.updated`, khóa `version`, review `BILL_NOT_READY`, khóa/mở nộp bill, finalize-all |
| 04 | [`04-settlement.md`](04-settlement.md) | Module Settlement (`/groups/{id}/...`) + màn hình Settlement (4 tab) / VietQR Sheet / Proof Review | QR không giữ nợ, snapshot bank lúc nộp proof, QR UUIDv4 / proof UUIDv5 theo nội dung, idempotency `IDEMPOTENCY_KEY_REUSED`, nhắc nợ 24h × 3, job 72h/48h |
| 05 | [`05-notification.md`](05-notification.md) | Module Notification (`/notifications`) + Push Notification (FCM) + màn hình Notifications | Insert+enqueue trong tx nghiệp vụ, FCM phụ in-app chính, `bill_review_requested` / `new_bill`, SSE `notification.created`, resolver type-first, foreground SnackBar |
| 06 | [`06-admin.md`](06-admin.md) | Module Admin (`/admin`) + Web Admin Portal (`/admin-portal/`) | Nhúng tĩnh `//go:embed`, khóa tài khoản = thu hồi sid trong cùng tx, mask STK, warning công nợ, probe `/health*`. Auto-refresh portal đang gãy (thiếu `device_id`) |
| 07 | [`07-app-startup-network.md`](07-app-startup-network.md) | Bootstrap, Splash, GoRouter guards, Dio/`SessionRefresher` | Splash chỉ animation, một redirect, REST và SSE 401 đi chung một cửa refresh, logout gọi `POST /auth/sign-out` |
| 08 | [`08-realtime.md`](08-realtime.md) | Kênh sự kiện realtime dùng chung (`GET /users/me/events`) + ba kênh PostgreSQL `LISTEN/NOTIFY` ↔ mọi màn hình có dữ liệu sống | Một kết nối SSE cho mỗi phiên, invalidation nhỏ (chỉ báo tin, không chở dữ liệu), `pg_notify` trong transaction, thay thế kết nối theo thứ tự commit, sổ đăng ký mối quan tâm phía Flutter, vá danh sách tại chỗ, gộp 250ms, backoff và hàn dữ liệu sau `ready` |

### Báo cáo đối chiếu và nguồn lịch sử

Các báo cáo explore là snapshot cũ, có thông tin đã lỗi thời. Dùng báo cáo đối chiếu dưới đây và các flow 01–08 cho hành vi hiện tại; không dùng số dòng trong báo cáo cũ để kết luận về HEAD.

| File | Nội dung |
|---|---|
| [Đối chiếu 06/09/2026](reports/2026-09-06-flow-sync.md) | Các thay đổi đã kiểm tra, bằng chứng mã nguồn, test và giới hạn còn lại |
| [`reports/paysplit-be-explore-report.md`](reports/paysplit-be-explore-report.md) | Raw report Backend: endpoints, usecases, domain errors, edge cases, River jobs, DB schema theo từng module + đối chiếu OpenAPI |
| [`reports/paysplit-fe-explore-report.md`](reports/paysplit-fe-explore-report.md) | Raw report Frontend: routing/guards, providers/state, datasources/API calls, UI flow và edge cases theo từng feature |

---

## 🔤 Quy ước đọc diagram

- **Sequence Diagram** (Mermaid `sequenceDiagram`): thể hiện thứ tự tương tác **Người dùng → Flutter App / Web Admin → API BE → DB / Dịch vụ ngoài**. Số dòng có `autonumber`.
- **Activity Diagram** (Mermaid `flowchart TD/LR`): thể hiện nhánh quyết định của một màn hình hoặc một thuật toán.
- Ký hiệu lỗi: `4xx CODE` là mã lỗi nghiệp vụ trả về trong envelope chuẩn:

```json
// Thành công
{ "success": true, "data": { ... }, "message": "Thành công" }
// Thất bại
{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "...", "details": { } } }
```

---

## ⚙️ Hạ tầng dùng chung ảnh hưởng đến mọi luồng

Những cơ chế này **không lặp lại** trong từng file con, đọc một lần ở đây:

### 1. Middleware chuỗi request (BE — `internal/transport/http/router/router.go`)
Áp dụng cho mọi request theo thứ tự:
`RequestID → ClientIP → Prometheus Metrics → Request Logger → Recoverer → CORS → RateLimit(IP) → Timeout`

- **RateLimit toàn cục**: fixed-window theo IP. Vượt → `429 RATE_LIMITED` + header `Retry-After`.
- **RateLimitByAccountAndIP**: budget kép `account:<userID>` + `ip:<IP>` — áp dụng riêng cho `PreviewInvite` và `JoinGroup` (xem 02-group).
- **liveAuth** (middleware Auth): verify JWT access token (15m, chứa `sid`) **và** kiểm tra session còn sống trong DB (chưa revoke, chưa hết hạn, user `active`, role khớp). Fail → `401 AUTHENTICATION_REQUIRED`.
- **RequireRole("admin")**: fail → `403 INSUFFICIENT_PERMISSIONS`.

### 2. Group row lock ("transaction boundary" chuẩn)
Mọi mutation theo nhóm (group/bill/settlement) đều gọi `LockActiveGroup` —
`SELECT ... FROM groups WHERE id=$1 AND status='active' FOR UPDATE [NOWAIT]` (`PaySplit-BE/internal/platform/database/group_lock.go`). Đây là cơ chế chống race trung tâm: join nhóm, finalize bill, void bill, payment... đều serialize qua khóa này.

### 3. Idempotency-Key
- Bill và Settlement có **2 hệ idempotency riêng** (bảng `bill_idempotency_keys`, `payment_idempotency_keys`, TTL 24h).
- Key dùng lại với **payload khác** → `409 IDEMPOTENCY_KEY_REUSED`; key đang `in_progress` của op khác → `409 IDEMPOTENCY_IN_PROGRESS`; mutation thất bại → release key để retry không bị kẹt.
- FE settlement: **QR và nhắc nợ dùng UUIDv4 mỗi lần gọi**. Proof dùng UUIDv5 từ group/payment + SHA-256 bytes ảnh + note chuẩn hóa; confirm/reject vẫn UUIDv5 (reject chứa lý do). Cùng nội dung proof retry giữ key; đổi ảnh/note/payment đổi key. Xem [04](04-settlement.md).

### 4. River Queue (background jobs trên PostgreSQL)
Các worker: `send_notification`, `bill_ocr`, `bill_bulk_finalize_item`, `settlement_scan` (nhắc nợ tự động + cảnh báo payment treo), các job retention/cleanup và `ocr_stale_job_reaper` mỗi 2 phút. Các job phát sinh từ mutation được enqueue **trong cùng transaction** với bản ghi nghiệp vụ (BeforeCommit hook); job định kỳ được đăng ký riêng qua River.

`RIVER_POLL_ONLY` mặc định `false` (River vẫn giữ notifier `LISTEN`). Khi bật `true`, River không giữ session `LISTEN`; job mới được tìm bằng polling (`RIVER_FETCH_POLL_INTERVAL_MS`, mặc định 1s). Enqueue của thư viện vẫn có thể gửi `NOTIFY`. Rollback: đặt lại `false` rồi restart process, không cần migration. Chi tiết: spec [0010](../PaySplit-BE/docs/specs/0010-connection-efficient-events/index.md).

### 5. Shared PostgreSQL listener (Bill SSE + Group SSE + User stream)
Mỗi backend instance giữ **một** connection `LISTEN` cho cả ba channel `bill_events`, `group_events`, `user_events` (`internal/platform/database/notification_listener.go`), không còn vòng `StartPostgresListener` riêng trên từng Hub. Hub chỉ decode, validate envelope, rồi publish vào subscriber local (Bill buffer 16, Group buffer 32, User buffer 64).

Kênh `user_events` là nền của **một kết nối SSE duy nhất cho mỗi phiên đăng nhập** — chi tiết đầy đủ ở [`08-realtime.md`](08-realtime.md).

- `/health/ready` chỉ `200` khi listener đã đăng ký đủ cả ba channel; mất connection → `503 degraded`, reconnect backoff, rồi mới healthy lại.
- Khi listener đứt, server **đóng mọi SSE local**. App mặc định đang ở user stream: kết nối lại `GET /users/me/events`, `ready` hàn dữ liệu (xem 08). `REALTIME_MODE=legacy`: Bill mở lại `/bills/{id}/events` lấy `snapshot`; Group dùng version fencing và `GET /groups/{id}/sync`.
- Tắt process: đóng SSE trước, rồi HTTP, River, `UNLISTEN *`, rồi pool.

### 6. Edge case xuyên suốt (mọi màn hình)

| Tình huống | Xử lý |
|---|---|
| Access token hết hạn (15 phút) | FE Mobile: `AuthInterceptor` + `SessionRefresher` single-flight (REST và SSE dùng chung). Web Admin `tryRefreshToken` **thiếu `device_id`** nên không xoay được — xem 06-admin |
| SSE `close: session_ended` | FE đóng stream, gọi `endSession()`, xóa token, chuyển Login kèm cảnh báo. Không chờ REST 401 |
| Refresh token bị tái sử dụng | BE coi là gian lận → revoke toàn bộ session + token, `SESSION_REVOKED` → xóa token cục bộ, điều hướng về đăng nhập |
| Mất mạng / timeout | FE map `connectionError/timeout` → `NetworkFailure` "Không thể kết nối tới máy chủ" |
| Server lỗi 5xx | FE → `ServerFailure`, hiển thị SnackBar/banner kèm nút retry (tùy màn) |
| Body 2xx sai shape | FE → `invalidResponseFailure` (parse khoan dung `ApiResponse<T>`) |

---

## 📌 Hiện trạng & Khả năng mở rộng tiếp theo

| Hạng mục | Trạng thái triển khai | Chi tiết |
|---|:---:|---|
| Push Notification (FCM) + in-app realtime | ✅ **Có triển khai** | Đã tích hợp trọn vẹn cả BE (River worker) và FE Mobile (`fcm_token_manager`, `push_notification_handler`, `notification_route_resolver`) |
| Web Admin Portal | ✅ **Đã hoàn thành** | Nhúng tĩnh `/admin-portal/` kèm chart và probe `/health*`. Auto-refresh token portal đang gãy (thiếu `device_id`, xem 06-admin) |
| Deep Link / App Link | ⚠️ *Đang phát triển* | Lời mời dán tay; QR camera + gallery `zxing2` (xem 02-group). Manifest chưa có App Link |
| Logout Revocation API | ✅ **Đã hoàn thành** | FE gọi `POST /api/v1/auth/sign-out` (TokenAuth), nuốt lỗi mạng, rồi FCM logout + xóa local (xem 01-auth, 07) |
