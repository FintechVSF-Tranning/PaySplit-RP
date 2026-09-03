# PaySplit — Tài liệu Luồng hoạt động (Flows)

Thư mục này mô tả **luồng hoạt động end-to-end** của từng module/màn hình trong hệ sinh thái PaySplit, bao gồm cả Backend (Go) và Frontend (Flutter), kèm **Sequence Diagram** và **Activity Diagram** (Mermaid) và mục **Edge Cases** chi tiết cho mỗi luồng.

> Nguồn tham chiếu: mã nguồn thực tế tại `PaySplit-BE/` và `PaySplit-FE/`. Mỗi điểm quan trọng đều ghi kèm đường dẫn file để đối chiếu.

---

## 📂 Danh mục tài liệu

| # | File | Phạm vi | Nội dung chính |
|---|------|---------|----------------|
| 01 | [`01-auth.md`](01-auth.md) | Module Auth (`/auth`, `/users`) + màn hình Welcome / Register / Verify OTP / Login / Forgot & Reset Password / Profile | Đăng ký, kích hoạt OTP, đăng nhập, phiên đơn (single session), refresh rotation + reuse detection, quên/đổi mật khẩu, avatar, bank profile |
| 02 | [`02-group.md`](02-group.md) | Module Group (`/groups`) + màn hình Groups / Scan QR / Join by Link / Create Group / Add Members / Group Detail Hub | Tạo nhóm, mời (link/QR), preview + join, rời/xóa thành viên, chuyển Captain, giải tán nhóm, activity timeline |
| 03 | [`03-bill.md`](03-bill.md) | Module Bill (`/bills`, group close) + màn hình Bill Capture / Bill Detail | Tạo hóa đơn thủ công & quét OCR, worker OCR + SSE, chia tiền (floor allocation), review → finalize → void, khóa nộp bill, finalize hàng loạt |
| 04 | [`04-settlement.md`](04-settlement.md) | Module Settlement (`/groups/{id}/...`) + màn hình Settlement (4 tab) / VietQR Sheet / Proof Review | Công nợ, tạo Dynamic VietQR, nộp biên lai, xác nhận/từ chối, nhắc nợ thủ công & tự động, idempotency |
| 05 | [`05-notification.md`](05-notification.md) | Module Notification (`/notifications`) + Push Notification (FCM) + màn hình Notifications | In-app notification, FCM push worker, token registration (`FCMTokenManager`), push listener (`PushNotificationHandler`), điều hướng thông minh (`NotificationRouteResolver`) |
| 06 | [`06-admin.md`](06-admin.md) | Module Admin (`/admin`) + Web Admin Portal (`/admin-portal/`) | Web Admin Portal nhúng tĩnh (`//go:embed`), 4 biểu đồ Visual Analytics Live, quản lý tài khoản & thu hồi phiên tức thì, cảnh báo nghĩa vụ tài chính, đo độ trễ probes, xoay vòng token |
| 07 | [`07-app-startup-network.md`](07-app-startup-network.md) | Bootstrap, Splash, GoRouter guards, Dio/AuthInterceptor | Khởi động app, kiểm tra phiên, redirect logic, refresh token single-flight khi 401, xử lý offline |
| 08 | [`08-serverless-runtime-and-realtime-sync.md`](08-serverless-runtime-and-realtime-sync.md) | Vercel Serverless Function, Supabase Supavisor, Durable Queue `app_jobs`, Realtime Broadcast ES256 & Fallback Polling | Kiến trúc Serverless, Single Active Wave Dispatcher, Batch Drain 45s qua pg_net, cấp token ES256 JWT, RLS private broadcast channel, consolidated polling /sync/versions |

### Nguồn tham chiếu gốc (báo cáo explore nguyên văn)

| File | Nội dung |
|---|---|
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
- FE settlement sinh key **deterministic UUIDv5** (replay được), trừ nhắc nợ dùng UUIDv4 ngẫu nhiên.

### 4. River Queue (background jobs trên PostgreSQL)
Các worker: `send_notification`, `bill_ocr`, `bill_bulk_finalize_item`, `settlement_scan` (nhắc nợ tự động + cảnh báo payment treo), các job retention/cleanup. Job luôn được enqueue **trong cùng transaction** với bản ghi nghiệp vụ (BeforeCommit hook) → không có job mồ côi hay bản ghi thiếu job.

`RIVER_POLL_ONLY` mặc định `false` (River vẫn giữ notifier `LISTEN`). Khi bật `true`, River không giữ session `LISTEN`; job mới được tìm bằng polling (`RIVER_FETCH_POLL_INTERVAL_MS`, mặc định 1s). Enqueue của thư viện vẫn có thể gửi `NOTIFY`. Rollback: đặt lại `false` rồi restart process, không cần migration. Chi tiết: spec [0010](../docs/specs/0010-connection-efficient-events/index.md).

### 5. Shared PostgreSQL listener (Bill SSE + Group SSE)
Mỗi backend instance giữ **một** connection `LISTEN bill_events` và `LISTEN group_events` (`internal/platform/database/notification_listener.go`), không còn hai vòng `StartPostgresListener` trên Hub. Hub chỉ decode, validate envelope, rồi publish vào subscriber local (Bill buffer 16, Group buffer 32).

- `/health/ready` chỉ `200` khi listener đã đăng ký đủ hai channel; mất connection → `503 degraded`, reconnect backoff, rồi mới healthy lại.
- Khi listener đứt, server **đóng mọi SSE local**. Client Bill mở lại stream để lấy `snapshot`. Client Group dùng version fencing và `GET /groups/{id}/sync`.
- Tắt process: đóng SSE trước, rồi HTTP, River, `UNLISTEN *`, rồi pool.

### 6. Edge case xuyên suốt (mọi màn hình)

| Tình huống | Xử lý |
|---|---|
| Access token hết hạn (15 phút) | FE Mobile (`AuthInterceptor`) và Web Admin (`tryRefreshToken`) bắt `401` → refresh single-flight → retry request tự động |
| Refresh token bị tái sử dụng | BE coi là gian lận → revoke toàn bộ session + token, `SESSION_REVOKED` → xóa token cục bộ, điều hướng về đăng nhập |
| Mất mạng / timeout | FE map `connectionError/timeout` → `NetworkFailure` "Không thể kết nối tới máy chủ" |
| Server lỗi 5xx | FE → `ServerFailure`, hiển thị SnackBar/banner kèm nút retry (tùy màn) |
| Body 2xx sai shape | FE → `invalidResponseFailure` (parse khoan dung `ApiResponse<T>`) |

---

## 📌 Hiện trạng & Khả năng mở rộng tiếp theo

| Hạng mục | Trạng thái triển khai | Chi tiết |
|---|:---:|---|
| Push Notification (FCM) | ✅ **Đã hoàn thành** | Đã tích hợp trọn vẹn cả BE (River worker) và FE Mobile (`fcm_token_manager`, `push_notification_handler`, `notification_route_resolver`) |
| Web Admin Portal | ✅ **Đã hoàn thành** | Đã tích hợp web app nhúng tĩnh tại `/admin-portal/` kèm visual charts, live probes, token auto-refresh |
| Deep Link / App Link | ⚠️ *Đang phát triển* | Lời mời dạng link hiện dán tay; QR scanner hỗ trợ chọn ảnh từ gallery decode `zxing2` (xem 02-group) |
| Logout Revocation API | ⚠️ *Đang hoàn thiện* | FE Mobile đang gọi clear local storage; khuyến nghị gọi `POST /api/v1/auth/sign-out` để thu hồi tức thời session phía BE |
