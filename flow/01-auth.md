# 01 — Auth: Xác thực, Phiên đăng nhập & Hồ sơ cá nhân

> **Phạm vi**: BE module `auth` (`/api/v1/auth`, `/api/v1/users`) ↔ FE màn hình Welcome / Register / Verify OTP / Login / Forgot & Reset Password / Change Password / Profile / Bank Settings.
>
> Code tham chiếu chính: `PaySplit-BE/internal/modules/auth/**`, `PaySplit-FE/lib/features/auth/**`, `PaySplit-FE/lib/features/profile/**`.

---

## 1. Tổng quan mô hình phiên

| Khái niệm | Giá trị |
|---|---|
| Access token | JWT **15 phút**, payload chứa `sid` (session ID) |
| Refresh token | Opaque 32-byte random (base64url), BE chỉ lưu SHA-256, TTL **7 ngày** |
| Session | **Tối đa 1 session active mỗi user** (unique index `uq_sessions_one_active_per_user`). Đăng nhập thiết bị mới → thu hồi session cũ (`replaced_by_sign_in`) |
| OTP email | 6 chữ số, lưu SHA-256, hiệu lực 10 phút, **tối đa 5 lần thử sai thì token bị vô hiệu vĩnh viễn** |
| Brute-force login | **5 lần sai trong cửa sổ 15 phút → khóa đăng nhập 15 phút** |
| Mô hình token FE | `flutter_secure_storage` — keys `access_token`, `refresh_token` |

## 2. Endpoint & màn hình

### BE endpoints

| Method + Path | Handler | Middleware | Chức năng |
|---|---|---|---|
| POST `/auth/sign-up` | SignUp | — (rate limit IP toàn cục) | Đăng ký, tạo user `pending_verification` + OTP |
| POST `/auth/verify-email` | VerifyEmail | — | Kích hoạt tài khoản bằng OTP |
| POST `/auth/resend-verification` | ResendVerification | — | Gửi lại OTP |
| POST `/auth/sign-in` | SignIn | — | Đăng nhập, phát hành cặp token |
| POST `/auth/refresh` | Refresh | — | Xoay vòng refresh token (rotation) |
| POST `/auth/forgot-password` | ForgotPassword | — | Gửi OTP đặt lại mật khẩu |
| POST `/auth/reset-password` | ResetPassword | — | Đặt lại mật khẩu bằng OTP |
| POST `/auth/sign-out` | SignOut | TokenAuth (chỉ verify JWT) | Thu hồi phiên hiện tại |
| GET/PATCH `/users/me` | Profile | liveAuth | Xem/sửa hồ sơ (+ bank profile) |
| PUT `/users/me/password` | ChangePassword | liveAuth | Đổi mật khẩu |
| PUT/DELETE `/users/me/avatar` | Avatar | liveAuth | Upload/xóa avatar (Cloudinary) |
| PUT `/users/me/fcm-token` | FCMToken | liveAuth | Gắn FCM token vào session |

### FE màn hình (go_router)

| Path | Page | Ghi chú |
|---|---|---|
| `/welcome` | WelcomePage | Onboarding carousel 3 slide → đẩy sang `/login` |
| `/register` | RegisterPage | Validate client-side đầy đủ |
| `/verify-otp` | VerifyOtpPage | extra: `email`; Pinput 6 ô auto-submit |
| `/login` | LoginPage | extra: `resetSuccess` (bool) hiển thị alert sau reset |
| `/forgot-password` | ForgotPasswordPage | |
| `/reset-password` | ResetPasswordPage | extra: `email` |
| `/profile`, `/edit-profile`, `/bank-settings`, `/change-password` | Profile* pages | Shell branch "Cài đặt" |

---

## 3. Sequence Diagrams

### 3.1 Đăng ký → Kích hoạt OTP → Đăng nhập lần đầu

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant FE as Flutter (RegisterPage → VerifyOtpPage)
    participant BE as Auth API (Go)
    participant DB as PostgreSQL
    participant Mail as Gmail SMTP

    U->>FE: Nhập tên, email, mật khẩu, SĐT (tùy chọn), tick điều khoản
    FE->>FE: Validate client: tên ≥2 ký tự, email chứa @ và .<br/>PasswordChecklist realtime (8–72 ký tự, hoa/thường/số)<br/>SĐT regex ^0(3|5|7|8|9)[0-9]{8}$
    FE->>BE: POST /auth/sign-up {display_name, email, password, phone_number?}
    BE->>BE: Normalize email (lowercase, 3–254), SĐT → E.164 VN,<br/>name 1–100 rune, kiểm tra policy mật khẩu
    BE->>DB: Rate limit sign_up theo hash(IP): tối đa 10 lượt/giờ
    alt Vượt giới hạn hoặc email/SĐT trùng
        BE-->>FE: 429 RATE_LIMITED / 409 EMAIL_ALREADY_EXISTS / PHONE_ALREADY_EXISTS
        FE-->>U: SnackBar lỗi đỏ
    end
    Note over BE,DB: 1 transaction: bcrypt(password) → INSERT users (pending_verification) + INSERT user_tokens (OTP 6 số, SHA-256)
    BE->>Mail: Gửi email chứa OTP
    Note over BE,Mail: Lỗi gửi mail CHỈ log — signup vẫn thành công (201)
    BE-->>FE: 201 Created
    FE->>U: Điều hướng VerifyOtpPage (extra: email)

    U->>FE: Nhập 6 số OTP (auto-submit khi đủ)
    FE->>BE: POST /auth/verify-email {email, otp}
    BE->>DB: SELECT user + token FOR UPDATE
    alt User đã active (bấm verify 2 lần)
        BE->>BE: So sánh constant-time với OTP đã used → trả OK (idempotent replay)
        BE-->>FE: 200 OK
    else Sai OTP
        BE->>DB: attempt_count += 1
        alt Đã sai đủ 5 lần
            BE->>DB: Supersede token VĨNH VIỄN (không thể verify nữa)
            BE-->>FE: 400 INVALID_OR_EXPIRED_TOKEN
            FE-->>U: SnackBar đỏ + rung ô PIN → phải bấm gửi lại mã
        else Còn lượt thử
            BE-->>FE: 400 INVALID_OR_EXPIRED_TOKEN
            FE-->>U: SnackBar đỏ + rung
        end
    else OTP đúng, còn hạn, chưa superseded
        BE->>DB: users.status = 'active', tokens.used_at = now()
        BE-->>FE: 200 OK
        FE->>U: Điều hướng /login (đăng nhập bằng tay)
    end
```

**Gửi lại OTP** — `VerifyOtpPage` có countdown 60s; gọi `POST /auth/resend-verification`. BE rate-limit theo `email+IP` (≥1 phút/lần, ≥10 lượt/ngày); **token mới supersede token cũ** (unique partial index: chỉ 1 token active mỗi type).

### 3.2 Đăng nhập & mô hình single-session

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant FE as Flutter (LoginPage)
    participant BE as Auth API
    participant DB as PostgreSQL

    U->>FE: Nhập email + mật khẩu, bấm Đăng nhập
    FE->>FE: Validate client (email, password bắt buộc)
    FE->>BE: POST /auth/sign-in {email, password, device_id, device_name}
    BE->>DB: Kiểm tra login_blocked_until TRƯỚC khi so mật khẩu
    alt Đang bị khóa brute-force
        BE-->>FE: 429 RATE_LIMITED {retry_after}
        FE-->>U: Banner đỏ + timer đếm ngược 900s, disable nút submit
    else Sai email/mật khẩu
        BE->>DB: Ghi login failure (5 sai / 15 phút → block 15 phút)
        BE-->>FE: 401 INVALID_CREDENTIALS
        FE-->>U: SnackBar lỗi
    else Tài khoản chưa kích hoạt
        BE-->>FE: 403 EMAIL_NOT_VERIFIED
        FE-->>U: Banner warning kèm link sang /verify-otp (extra: email)
    else Tài khoản suspended/locked
        BE-->>FE: 423 ACCOUNT_UNAVAILABLE
    else Hợp lệ
        BE->>DB: bcrypt compare OK
        BE->>DB: THU HỒI mọi session cũ của user (replaced_by_sign_in)
        BE->>DB: INSERT session mới + refresh token (SHA-256) — duy nhất 1 session active
        BE->>BE: Ký JWT access 15m chứa sid
        alt Ký JWT thất bại
            BE->>DB: Revoked ngay session vừa tạo (không để phiên mồ côi)
        end
        BE->>DB: Reset bộ đếm login failure
        BE-->>FE: 200 {access_token, refresh_token, user}
        FE->>FE: Lưu 2 token vào secure storage
        FE->>U: Router redirect → /home
    end
```

> Ý nghĩa single-session: người dùng đăng nhập máy mới → máy cũ bị "đá" — JWT cũ chứa `sid` đã chết, request tiếp theo của máy cũ bị `liveAuth` chặn `401`.

### 3.3 Refresh token rotation & reuse detection

```mermaid
sequenceDiagram
    autonumber
    participant FE as AuthInterceptor
    participant BE as Auth API
    participant DB as PostgreSQL

    Note over FE: Request thường nhận 401 (access hết hạn)
    FE->>FE: Single-flight: các request 401 đồng thời chờ chung 1 future _refreshing
    FE->>BE: POST /auth/refresh {refresh_token, device_id} (Dio riêng, không interceptor)
    BE->>DB: Tra refresh token theo SHA-256 hash
    alt Token ĐÃ used_at ≠ NULL (bị tái sử dụng — nghi gian lận)
        BE->>DB: Revoke TOÀN BỘ session + mọi refresh token của nó
        BE-->>FE: 401 SESSION_REVOKED
        FE->>FE: clear() secure storage → AuthController fail → router về /welcome
    else Token revoked hoặc hết hạn
        BE-->>FE: 401 SESSION_REVOKED / INVALID_OR_EXPIRED_TOKEN
        FE->>FE: Clear storage → logout mềm
    else device_id KHÔNG khớp session
        BE-->>FE: 401 SESSION_REVOKED
    else Hợp lệ
        BE->>DB: Mark token cũ used_at = now() + INSERT token mới<br/>TTL mới = min(now + 7 ngày, hạn session)
        BE-->>FE: 200 {access_token, refresh_token}
        FE->>FE: Ghi đè storage, retry request gốc với header Bearer mới (flag retried chống loop)
    end
```

### 3.4 Quên / đặt lại mật khẩu

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant FE as ForgotPasswordPage → ResetPasswordPage
    participant BE as Auth API
    participant Mail as SMTP

    U->>FE: Nhập email
    FE->>BE: POST /auth/forgot-password {email}
    BE->>BE: Rate limit theo email+IP (1/phút, 10/ngày)
    Note over BE: Email KHÔNG tồn tại hoặc user không pending → vẫn trả 200 (chống user enumeration)
    BE->>Mail: Gửi OTP (nếu email tồn tại). Token mới supersede token cũ cùng type
    BE-->>FE: 200 (luôn)
    FE->>U: Điều hướng /reset-password (extra: email)

    U->>FE: Nhập OTP + mật khẩu mới (checklist realtime) + xác nhận khớp
    FE->>BE: POST /auth/reset-password {email, otp, new_password} → 204
    BE->>BE: Logic OTP như verify-email (sai 5 lần → token chết vĩnh viễn)
    BE->>BE: THU HỒI toàn bộ session + refresh token (reason: password_reset)
    FE->>U: context.go(/login, extra: true) → alert xanh "Đặt lại mật khẩu thành công"
```

### 3.5 Đổi mật khẩu (đã đăng nhập)

```mermaid
sequenceDiagram
    autonumber
    actor U as ChangePasswordPage
    participant BE as Auth API
    participant DB as PostgreSQL

    U->>FE: current_password + new_password (checklist ≥8, hoa, số) + confirm khớp
    FE->>BE: PUT /users/me/password {current_password, new_password}
    alt current sai
        BE-->>FE: 400 INVALID_CURRENT_PASSWORD (mapper có sẵn câu tiếng Việt)
    else new trùng current
        BE-->>FE: 400 INVALID_INPUT
    else OK
        BE->>DB: Update bcrypt mới + THU HỒI mọi session KHÁC session hiện tại
        Note over DB: Phiên hiện tại được GIỮ — không tự đăng xuất mình
        BE-->>FE: 204 No Content
    end
```

### 3.6 Upload avatar (compensating actions)

```mermaid
sequenceDiagram
    autonumber
    actor U as ProfilePage
    participant BE as Auth API
    participant CDN as Cloudinary
    participant DB as PostgreSQL
    participant Q as River Queue

    U->>FE: Chọn ảnh (camera/gallery)
    FE->>BE: PUT /users/me/avatar (multipart "avatar")
    alt Ảnh >10MB hoặc decode fail
        BE-->>FE: 413 PAYLOAD_TOO_LARGE / 400 INVALID_IMAGE
    else OK
        BE->>CDN: Convert WebP (strip EXIF) → upload paysplit/avatars/<uid>/<uuidv7>
        alt Upload OK nhưng UPDATE DB fail
            BE->>CDN: XÓA object vừa upload (compensating delete)
            Note over Q: Nếu xóa CDN cũng fail → enqueue media_cleanup_jobs (bền vững, retry exp backoff ≤10 lần)
        else Xóa avatar cũ fail
            BE->>Q: Enqueue media_cleanup_jobs dọn sau
        end
        BE-->>FE: 200 {avatar_url}
        FE->>FE: copyWith avatarUrl vào state AuthController
    end
```

## 4. Activity Diagrams

### 4.1 Luồng màn hình Login (FE)

```mermaid
flowchart TD
    A["Vào /login"] --> B{"extra resetSuccess?"}
    B -->|"true"| C["Hiện alert xanh 'Đặt lại MK thành công'"]
    B -->|"false"| D["Form trống"]
    C --> D
    D --> E["User nhập email + mật khẩu"]
    E --> F{"Validate client pass?"}
    F -->|"Không"| E
    F -->|"Có"| G["Gọi POST /auth/sign-in"]
    G --> H{"Kết quả?"}
    H -->|"200"| I["Lưu token → redirect /home"]
    H -->|"EMAIL_NOT_VERIFIED"| J["Banner warning + link sang /verify-otp"]
    J --> E
    H -->|"RATE_LIMITED"| K["Timer 900s khóa nút submit + banner đỏ"]
    K --> E
    H -->|"Lỗi khác"| L["SnackBar đỏ failure.message"]
    L --> E
```

### 4.2 Luồng màn hình Verify OTP (FE)

```mermaid
flowchart TD
    A["Vào /verify-otp (extra: email)"] --> B["Pinput 6 ô + countdown 60s cho nút gửi lại"]
    B --> C["User nhập OTP"]
    C --> D{"Đủ 6 số?"}
    D -->|"Chưa"| C
    D -->|"Rồi → auto-submit"| E["POST /auth/verify-email"]
    E --> F{"Kết quả?"}
    F -->|"OK"| G["Haptic feedback → context.go /login"]
    F -->|"Sai / hết hạn"| H["SnackBar đỏ + animation rung"]
    H --> I{"Còn lượt thử (<5)? và còn hiệu lực?"}
    I -->|"Có"| C
    I -->|"Token đã chết (sai 5 lần)"| J["Bắt buộc bấm 'Gửi lại mã'"]
    J --> K{"Countdown 60s hết? và rate limit OK?"}
    K -->|"Chưa"| J
    K -->|"Rồi"| L["POST /auth/resend-verification → token mới supersede cũ"]
    L --> B
```

### 4.3 Quyết định redirect khi đổi mật khẩu/quên mật khẩu (tổng hợp)

```mermaid
flowchart LR
    subgraph Reset["Reset password (qua OTP)"]
        R1["Thành công"] --> R2["Thu hồi TOÀN BỘ phiên (kể cả hiện tại)"]
        R2 --> R3["Về /login"]
    end
    subgraph Change["Change password (đã đăng nhập)"]
        C1["Thành công"] --> C2["Thu hồi mọi session KHÁC, giữ phiên hiện tại"]
        C2 --> C3["Ở lại app"]
    end
```

## 5. Edge Cases

### 5.1 Bảng edge case chi tiết

| # | Tình huống | Xử lý hệ thống | Mã lỗi / phản hồi | Vị trí code (tham chiếu) |
|---|---|---|---|---|
| 1 | Email đã tồn tại khi đăng ký | Unique constraint `users_email_key` map thành domain error | `409 EMAIL_ALREADY_EXISTS` | `auth/repository/postgres/repository.go:736-747` |
| 2 | SĐT đã tồn tại | Tương tự qua `users_phone_number_key` | `409 PHONE_ALREADY_EXISTS` | như trên |
| 3 | Spam đăng ký theo IP | Rate limit DB `sign_up`: 10 lượt/giờ, dùng `pg_advisory_xact_lock` chống race đếm | `429 RATE_LIMITED` | `auth/usecase/service.go:81-120` |
| 4 | OTP sai quá 5 lần | attempt_count chạm ngưỡng → **supersede token vĩnh viễn**, phải xin mã mới | `400 INVALID_OR_EXPIRED_TOKEN` | `auth/repository/postgres/repository.go:154-168` |
| 5 | Verify khi đã active (double-submit / replay) | So sánh constant-time với OTP đã used → vẫn trả OK (idempotent) | `200 OK` | cùng file trên |
| 6 | Xin lại mã liên tục | Rate limit resend/forgot theo email+IP: ≥1 phút/lần, ≥10/ngày; token mới supersede cái cũ | `429 RATE_LIMITED` | `repository.go:562-573` |
| 7 | Dò email tồn tại (user enumeration) qua quên mật khẩu/gửi lại OTP | Luôn trả 200 dù email không tồn tại/user không pending | `200 OK` (giả lập) | `auth/usecase/service.go:153-161` |
| 8 | Brute-force mật khẩu | 5 lần sai trong cửa sổ 15′ → block 15′; check `login_blocked_until` **trước** khi so bcrypt (tránh leak thông tin) | `429 RATE_LIMITED {retry_after}` | `repository.go:187-226` |
| 9 | Login khi chưa kích hoạt email | Chặn sớm với hướng dẫn sang màn OTP | `403 EMAIL_NOT_VERIFIED` | `service.go:190-241` |
| 10 | Login khi suspended/locked (admin khóa) | Chặn | `423 ACCOUNT_UNAVAILABLE` | như trên |
| 11 | Đăng nhập thiết bị thứ 2 | Thu hồi session cũ (`replaced_by_sign_in`); JWT cũ có `sid` chết → request kế tiếp bị 401 | `200` + phiên mới | `repository.go:250-255` |
| 12 | Ký JWT thất bại ngay sau khi tạo session | Revoke ngay session vừa tạo — không để phiên mồ côi | `500` | `service.go:236-239` |
| 13 | Refresh token đã dùng bị đưa ra dùng lại (reuse/replay) | **Reuse detection**: revoke toàn bộ session + token con | `401 SESSION_REVOKED` | `repository.go:307-314` |
| 14 | Refresh từ device_id khác | Từ chối — token gắn chặt session/device | `401 SESSION_REVOKED` | `repository.go:318-320` |
| 15 | Nhiều request 401 đồng thời bắn refresh song song | FE single-flight `_refreshing` Future chung; nếu chạy song song thật, rotation sẽ trigger reuse-detection → mất phiên | tránh bởi interceptor | `core/network/interceptors/auth_interceptor.dart:25-30` |
| 16 | Refresh fail (mạng chập chờn 1 lần) | FE clear cả 2 token → AuthController build fail → redirect `/welcome`. **Lưu ý**: chỉ clear khi refresh nhận lỗi xác thực, không retry vô hạn nhờ flag `retried` | về `/welcome` | `auth_interceptor.dart:66-88` |
| 17 | Đổi mật khẩu nhưng vẫn muốn ở lại app | Giữ phiên hiện tại, chỉ đá các phiên khác | `204` | `repository.go:442-465` |
| 18 | Reset mật khẩu khi đang đăng nhập nhiều nơi | Thu hồi **toàn bộ** session (kể cả hiện tại) → phải đăng nhập lại | `204` | `repository.go:379-440` |
| 19 | Avatar >10MB hoặc file giả đuôi ảnh | Check size + decode | `413` / `400 INVALID_IMAGE` | `service.go:310-346` |
| 20 | Upload CDN OK nhưng ghi DB lỗi | Compensating delete object; xóa tiếp fail → queue `media_cleanup_jobs` retry exp backoff ≤10 lần/cap 24h | `500` | `service.go:336-345` |
| 21 | Bank profile thiếu 1 trong 3 trường | Phải đủ cả 3 (code, số TK, chủ TK) hoặc rỗng hoàn toàn — CHECK DB tương ứng; số TK 6–19 chữ số; bank code phải nằm trong directory VietQR | `400 INVALID_INPUT` / `UNSUPPORTED_BANK` | `service.go:367-392` |
| 22 | Gắn FCM token khi session đã chết | Từ chối — token gắn vào session cụ thể | `401 SESSION_REVOKED` | `service.go:445-455` |
| 23 | FE logout | Hiện **chỉ xóa secure storage, chưa gọi** `POST /auth/sign-out` → session BE sống đến hết hạn (khoảng trống đã biết) | — | `features/auth/data/repositories/auth_repository_impl.dart:216-219` |

### 5.2 Edge case FE validation (client-side, trước khi gọi API)

| Màn hình | Ràng buộc |
|---|---|
| Register | Tên ≥2 ký tự; email chứa `@` và `.`; PasswordChecklist realtime (8–72, hoa, thường, số); SĐT regex VN `^0[3\|5\|7\|8\|9][0-9]{8}$` maxLength 11; checkbox điều khoản bắt buộc |
| Login | Email/password bắt buộc; timer 15′ khi bị rate-limited |
| Verify OTP | Pinput 6 số auto-submit; countdown 60s resend |
| Reset password | Checklist + confirm khớp |
| Change password | Checklist (≥8, chữ hoa, chữ số) phải pass hết mới enable submit |
| Bank settings | Bắt buộc chọn ngân hàng; chủ TK tự normalize UPPERCASE không dấu (`VietnameseUtils.toBankHolderFormat`) |

---

## 6. Ghi chú triển khai BE đáng chú ý

- Mọi sự kiện rate-limit/login-failure ghi DB (không chỉ in-memory) → sống sót qua restart, dùng advisory lock chống race đếm.
- Cleanup định kỳ (`auth/jobs/workers.go`): xóa token/session/rate-limit-event hết hạn (batch 500, advisory lock `paysplit_auth_cleanup` chống chạy song song).
- Response `sign-up`/`resend` luôn thành công kể cả khi SMTP lỗi — mail fail chỉ log, tránh chặn onboarding.
