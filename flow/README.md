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
| 05 | [`05-notification.md`](05-notification.md) | Module Notification (`/notifications`) + màn hình Notifications | In-app notification, FCM push worker, đánh dấu đã đọc, điều hướng theo payload |
| 06 | [`06-admin.md`](06-admin.md) | Module Admin (`/admin`) | Quản lý tài khoản, suspend/lock + thu hồi phiên, audit log, thống kê hệ thống |
| 07 | [`07-app-startup-network.md`](07-app-startup-network.md) | Bootstrap, Splash, GoRouter guards, Dio/AuthInterceptor | Khởi động app, kiểm tra phiên, redirect logic, refresh token single-flight khi 401, xử lý offline |

### Nguồn tham chiếu gốc (báo cáo explore nguyên văn)

| File | Nội dung |
|---|---|
| [`reports/paysplit-be-explore-report.md`](reports/paysplit-be-explore-report.md) | Raw report Backend: endpoints, usecases, domain errors, edge cases, River jobs, DB schema theo từng module + đối chiếu OpenAPI |
| [`reports/paysplit-fe-explore-report.md`](reports/paysplit-fe-explore-report.md) | Raw report Frontend: routing/guards, providers/state, datasources/API calls, UI flow và edge cases theo từng feature |

---

## 🔤 Quy ước đọc diagram

- **Sequence Diagram** (Mermaid `sequenceDiagram`): thể hiện thứ tự tương tác **Người dùng → Flutter App → API BE → DB/Dịch vụ ngoài**. Số dòng có `autonumber`.
- **Activity Diagram** (Mermaid `flowchart TD/LR`): thể hiện nhánh quyết định của một màn hình hoặc một thuật toán.
- Ký hiệu lỗi: `4xx CODE` là mã lỗi nghiệp vụ trả về trong envelope chuẩn:

```json
// Thành công
{ "success": true, "data": { ... }, "message": "..." }
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

### 5. Edge case xuyên suốt (mọi màn hình)

| Tình huống | Xử lý |
|---|---|
| Access token hết hạn (15 phút) | FE `AuthInterceptor` bắt `401` → refresh single-flight → retry request 1 lần (xem 07) |
| Refresh token bị tái sử dụng | BE coi là gian lận → revoke toàn bộ session + token, `SESSION_REVOKED` → FE xóa token cục bộ, về `/welcome` |
| Mất mạng / timeout | FE map `connectionError/timeout` → `NetworkFailure` "Không thể kết nối tới máy chủ" |
| Server lỗi 5xx | FE → `ServerFailure`, hiển thị SnackBar/banner kèm nút retry (tùy màn) |
| Body 2xx sai shape | FE → `invalidResponseFailure` (parse khoan dung `ApiResponse<T>`) |

---

## ⚠️ Khoảng trống đã biết (ghi nhận thực tế codebase, cập nhật khi triển khai xong)

| Khoảng trống | Chi tiết |
|---|---|
| FE chưa tích hợp FCM | Không có `firebase_messaging` trong `pubspec.yaml`; push chỉ chạy phía BE, FE hiện polling REST in-app (xem 05) |
| Logout chưa gọi `POST /auth/sign-out` | FE chỉ xóa secure storage, session phía BE còn sống đến khi hết hạn (xem 01, 07) |
| Không có deep link/app link | Lời mời dạng link phải **dán tay** vào sheet; QR scanner là placeholder (chọn ảnh từ gallery decode bằng `zxing2`) (xem 02) |
| Group Detail Hub dùng mock | Panels hóa đơn/công nợ trong nhóm + "Nhóm gần đây"/"Danh bạ" là dữ liệu in-memory; thao tác quản trị thì gọi API thật (xem 02) |
| Khóa bill phía FE chưa nối API thật | `markGroupClosedLocally` chỉ đổi state local (xem 02) |
| `NetworkInfo` đã DI nhưng chưa dùng | Offline detection dựa vào `DioException.connectionError` (xem 07) |
