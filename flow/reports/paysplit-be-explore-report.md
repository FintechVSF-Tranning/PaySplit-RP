# Báo cáo khám phá PaySplit-BE (raw)

> **Tài liệu lịch sử, không đại diện HEAD ngày 06/09/2026.** Nội dung explore nguyên văn bên dưới được giữ để truy nguyên; số dòng và một số kết luận đã cũ. Đọc [đối chiếu hiện tại](2026-09-06-flow-sync.md) và [flow 01–08](../README.md) trước khi dùng. Các thay đổi về SSE, notification, unlock, giới hạn nhóm và idempotency được mô tả ở tài liệu mới.

> Nguyên văn kết quả của subagent explore (nghiên cứu codebase Go backend tại `PaySplit-BE`, mức độ very thorough). Dùng làm nguồn tham chiếu thô cho các file flow `01–07`.

---

Tôi đã khám phá đầy đủ codebase. Dưới đây là báo cáo nghiên cứu chi tiết theo từng module.

## 0. Tổng quan kiến trúc & middleware dùng chung

**Điểm nối dây duy nhất**: `internal/bootstrap/app.go` — khởi tạo config → DB pool → platform adapters → 6 module → River Queue → router. Route đăng ký tại `app.go:247-259`:

| Prefix | Module |
|---|---|
| `/api/v1/auth`, `/api/v1/users` | auth |
| `/api/v1/notifications` | notification |
| `/api/v1/groups` (+ settlement, bill-close con) | group, settlement, bill |
| `/api/v1/admin` | admin |
| `/api/v1/banks` | banks (platform) |
| `/api/v1/bills` | bill |

**Middleware gốc** (`internal/transport/http/router/router.go:31-40`, áp dụng cho MỌI request): `RequestID` → `ClientIPFromRemoteAddr` (không tin forwarding header) → Prometheus metrics → RequestLogger → Recoverer → CORS → **RateLimit IP** → Timeout.

- **RateLimit toàn cục**: fixed-window theo IP, trả `429 RATE_LIMITED` + header `Retry-After` (`middleware/ratelimit.go:21-63`).
- **Auth middleware** (`middleware/auth.go:30-67`): 2 biến thể:
  - `TokenAuth(verifier)` — chỉ verify JWT (dùng cho `/auth/sign-out`).
  - `Auth(verifier, sessions)` = "liveAuth" — verify JWT **và** kiểm tra session còn sống trong DB (`ValidateSession`: session chưa revoke, chưa hết hạn, user status='active', role khớp — `auth/repository/postgres/repository.go:343-353`). Đây là middleware mặc định của mọi route protected.
  - Lỗi → `401 AUTHENTICATION_REQUIRED`.
- **RequireRole("admin")** (`middleware/auth.go:94-113`): `403 INSUFFICIENT_PERMISSIONS` nếu role không khớp.
- **RateLimitByAccountAndIP** (`middleware/ratelimit.go:68-135`): budget dùng chung 2 khóa `account:<userID>` và `ip:<IP>` — áp dụng riêng cho PreviewInvite + JoinGroup (`bootstrap/app.go:234`).
- **Khóa nhóm dùng chung**: `database.LockActiveGroup` / `LockActiveGroupNowait` (`platform/database/group_lock.go:20-45`) — `SELECT ... FROM groups WHERE id=$1 AND status='active' FOR UPDATE [NOWAIT]`; là "transaction boundary" chuẩn cho mọi mutation theo nhóm ở cả 3 module group/bill/settlement.
- Response envelope chuẩn `{success, data|error{code,message,details}}` qua `helpers/json.go`, `helpers/error.go`.

---

## 1. MODULE AUTH

### 1.1 Endpoints HTTP (`auth/delivery/http/routes.go`)
File: `internal/modules/auth/delivery/http/routes.go`

**RegisterAuthRoutes** (mount `/api/v1/auth`) — chỉ có TokenAuth cho sign-out:

| Method+Path | Handler | Middleware |
|---|---|---|
| POST `/sign-up` | SignUp | none (rate limit IP toàn cục) |
| POST `/verify-email` | VerifyEmail | none |
| POST `/resend-verification` | ResendVerification | none |
| POST `/sign-in` | SignIn | none |
| POST `/refresh` | Refresh | none |
| POST `/forgot-password` | ForgotPassword | none |
| POST `/reset-password` | ResetPassword | none |
| POST `/sign-out` | SignOut | `tokenAuth` |

**RegisterUserRoutes** (mount `/api/v1/users`, tất cả `liveAuth`) — routes.go:18-27:
GET `/me` · PATCH `/me` · PUT `/me/password` · PUT `/me/avatar` · DELETE `/me/avatar` · PUT `/me/fcm-token`.

### 1.2 UseCases (`auth/usecase/service.go`)
- **SignUp** (:81-120): normalize email (RFC, lowercase, 3–254 ký tự :394-404) → normalize phone E.164 vùng VN (:405-415) → name 1–100 rune → password policy (8–72 byte, chữ thường+hoa+số — `platform/security/password/bcrypt.go:33-47`) → rate limit DB `sign_up` theo hash(IP) (10 lần/giờ, không giới hạn/phút) → bcrypt hash → sinh OTP 6 số + SHA-256 hash (`domain/token.go:22-30`) → insert user + token trong 1 tx → gửi mail verification (lỗi mail chỉ log, KHÔNG fail signup :114-118).
- **VerifyEmail** (:122-128) → repo `VerifyEmail` (repository.go:105-185): lock user FOR UPDATE; nếu đã active → so sánh constant-time với OTP đã used (idempotent replay); nếu pending → check token còn hạn/chưa used/superseded, **tối đa 5 lần thử sai thì supersede vĩnh viễn token** (:154-168); đúng OTP → status='active' + đánh dấu used_at.
- **ResendVerification / ForgotPassword** (:130-181): rate limit DB theo email+IP (≥1 lần/phút, ≥10 lần/giờ — repository.go:562-573); **email không tồn tại hoặc user không pending → vẫn trả nil (chống user enumeration)**; token mới supersede token cũ (`CreateUserToken` repository.go:83-103, unique partial index `uq_user_tokens_one_active_per_type`).
- **SignIn** (:190-241): sai email/password → ghi login failure; **5 lần sai trong cửa sổ 15 phút → khóa login 15 phút** trả `RateLimitError{RetryAfter}` (`RecordLoginFailure` repository.go:187-226); check `login_blocked_until` trước khi so mật khẩu; tạo refresh token opaque 32-byte random (base64url, chỉ lưu SHA-256); **đăng nhập mới thu hồi mọi session cũ** (`replaced_by_sign_in`, repository.go:250-255) → mô hình 1 session active/user (unique index `uq_sessions_one_active_per_user`); reset bộ đếm login failure; phát hành access JWT 15m chứa `sid`. Nếu issue JWT lỗi → revoke ngay session vừa tạo (:236-239).
- **Refresh** (:243-264) → repo `RotateRefresh` (repository.go:273-341): tra token theo hash; **REUSE DETECTION**: nếu token đã used_at ≠ NULL → revoke TOÀN BỘ session + các refresh token của nó, trả `ErrSessionRevoked` (:307-314); check revoked/expired; **deviceID phải khớp session** (:318-320); rotation: mark used + insert token mới, TTL mới = min(now+7d, session expiry) (:324-333).
- **ResetPassword** (:270-283 → repo :379-440): OTP logic như verify-email; sau khi đổi → **thu hồi toàn bộ session + refresh token** (reason `password_reset`).
- **ChangePassword** (:285-304): validate mật khẩu mới, current phải đúng, **mới phải khác hiện tại**; repo thu hồi mọi session KHÁC session hiện tại (:442-465).
- **UploadAvatar** (:310-346): ≤10MB, convert WebP (EXIF strip), upload Cloudinary publicID `paysplit/avatars/<uid>/<uuidv7>`; upload OK nhưng update DB fail → xóa file vừa upload (compensating delete); xóa avatar cũ fail → enqueue `media_cleanup_jobs` bền vững.
- **PatchProfile** (:367-392): bank profile phải đủ cả 3 trường hoặc rỗng hoàn toàn (CHECK DB tương ứng), số TK 6–19 chữ số, bank code phải nằm trong directory VietQR (`ErrUnsupportedBank`).
- **UpdateFCMToken** (:445-455): gắn fcm_token vào session hiện tại; session hết hạn/không tồn tại → `ErrSessionRevoked` (repo :718-734).

### 1.3 Domain errors (`auth/domain/errors.go:8-29`)
`ErrInvalidInput`, `ErrEmailAlreadyExists` (map từ constraint `users_email_key` — repository.go:736-747), `ErrPhoneAlreadyExists` (`users_phone_number_key`), `ErrInvalidCredentials`, `ErrUserNotFound`, `ErrEmailNotVerified` (login khi pending_verification), `ErrAccountUnavailable` (status suspended/locked), `ErrInvalidOrExpiredToken`, `ErrSessionRevoked`, `ErrInvalidCurrentPassword`, `ErrUnsupportedBank`, `ErrInvalidImage`, `ErrPayloadTooLarge`, `ErrImageStorage`, struct `RateLimitError{RetryAfter}`.

### 1.4 Edge cases auth (đã kiểm chứng trong code)
1. Refresh token reuse → revoke cả session (phát hiện gian lận) — repository.go:307-314.
2. OTP sai 5 lần → token bị vô hiệu vĩnh viễn — repository.go:154-168, 416-425.
3. Brute-force login: 5 sai/15 phút → block 15 phút, có RetryAfter — repository.go:205-215.
4. User enumeration: forgot/resend luôn trả 200 — service.go:153-161.
5. Email/phone trùng → map từ unique constraint thành 409 domain error — repository.go:736-747.
6. Session đơn: đăng nhập thiết bị mới đá session cũ; JWT sid chết → liveAuth chặn 401.
7. Đổi mật khẩu/reset → thu hồi phiên nơi khác nhưng giữ phiên hiện tại (change password).
8. Rate limit DB dùng `pg_advisory_xact_lock` chống race đếm sự kiện — repository.go:548-553.
9. Cleanup định kỳ (`auth/jobs/workers.go`): xóa token/session/rate-limit-event/media-cleanup-job quá hạn (batch 500, advisory lock `paysplit_auth_cleanup` chống chạy song song — repository.go:627-661); media cleanup retry exponential backoff tối đa 10 lần/cap 24h (:59-83).

---

## 2. MODULE GROUP

### 2.1 Endpoints (`group/delivery/http/routes.go:9-28`, tất cả `liveAuth`; mount `/api/v1/groups`)

| Method+Path | Handler | Middleware thêm |
|---|---|---|
| POST `/` | CreateGroup | liveAuth |
| GET `/` | ListGroups | liveAuth |
| GET `/{id}` | GetGroupDetail | liveAuth |
| PATCH `/{id}` | RenameGroup | liveAuth |
| DELETE `/{id}` | DisbandGroup | liveAuth |
| GET `/{id}/invites` | ListInvites | liveAuth |
| POST `/{id}/invites` | CreateInvite | liveAuth |
| DELETE `/{id}/invites/{inviteId}` | RevokeInvite | liveAuth |
| GET `/invites/{code}` | PreviewInvite | liveAuth + **inviteAttemptLimiter** |
| POST `/join` | JoinGroup | liveAuth + **inviteAttemptLimiter** |
| DELETE `/{id}/members/{memberId}` | LeaveOrRemoveMember | liveAuth |
| PUT `/{id}/members/{memberId}/role` | TransferRole | liveAuth |
| GET `/{id}/activities` | ListActivities | liveAuth |

Lưu ý mount: settlement handler và bill close handler cũng gắn trên cùng prefix `/groups` (bootstrap app.go:251-255).

### 2.2 UseCases (`group/usecase/service.go`)
- **CreateGroup** (:63-84): tên trim 1–100 rune; currency **chỉ VND** (default VND). Repo tạo group + membership Captain + activity `group_created` trong 1 tx (`group/repository/postgres/repository.go:44-83`).
- **ListGroups** (:97-106): keyset cursor `(created_at,id)` base64, default limit 20, max 100, fetch limit+1 để detect hasMore (repo :85-163). Item gồm net balance, pending bill count, last activity, `bill_submission_locked_at`.
- **GetGroupDetail** (:111-116): **nhóm không tồn tại và caller không phải member cùng trả `ErrGroupNotFound`** (anti-enumeration — repo :183-191). Captain được thêm `active_bill_finalize_batch_id` / `latest_bill_finalize_batch_id` (repo :229-244).
- **CreateInvite** (:155-217): expiry default 24h, chấp nhận 1–168h; max_uses 1–50; **chỉ Captain được cấu hình (expiry/max_uses/regenerate)** — presence-first authorization (:137-149) rồi re-check dưới group lock (repo :309-311); member thường gọi không cấu hình → tái sử dụng invite available hiện có; `regenerate=true` → revoke mọi invite available rồi tạo mới (repo :319-337); **code Base62 8 ký tự, collision → retry tối đa 5 lần với transaction mới** (:188-208, `ErrInviteCodeCollision` từ 23505 `group_invites_code_key`). URL = HTTPS base + code (validate base tuyệt đối https :234-246).
- **RevokeInvite** (:274-282): **idempotent** — invite đã revoke vẫn 204 (repo :496-499); chỉ Captain.
- **PreviewInvite** (:286-291): trả tên nhóm, số member active, tên Captain; code sai format/hết hạn/revoke/hết lượt → `ErrInviteNotFound`.
- **JoinGroup** (:296-304) → `RedeemInvite` (repo :550-664): resolve group ngoài tx để fail fast; **lock group row TRƯỚC để serialize mọi redemption**; **member đã active → idempotent success trước cả check invite/capacity** (invariant 11, :590-604); check invite available (không revoke, chưa expire, use_count < max_uses — `inviteAvailable` :1118-1129); **check capacity 50 member active** (`maxGroupActiveMembers` repo :30, check :620-624) → `ErrGroupMemberLimitReached`; increment use_count; reactivate membership cũ nếu đã rời (do UNIQUE(group_id,user_id) cấm INSERT lại — comment migration 000001 :172-175); activity `member_joined`/`member_reactivated`.
- **LeaveOrRemoveMember** (:310-318 → repo :666-780): tự rời hoặc Captain xóa member thường; **authorization check TRƯỚC khi lộ trạng thái target** (anti-oracle :705-726); **idempotent** với target đã inactive (:728-732); **Captain active không thể rời/bị xóa** → `ErrCaptainTransferRequired` (:737-739); **CHẶN RỜI KHI CÒN NỢ**: sum debts `NOT IN ('settled','voided')` cả 2 chiều payable/receivable > 0 → `OpenDebtsError{PayableAmount, ReceivableAmount}` (:741-751); activity `member_left`/`member_removed`.
- **TransferCaptain** (:322-330 → repo :782-878): chỉ Captain; **group lock NOWAIT → conflict trả `ErrCaptainTransferConflict` thay vì queue** (:804-813); không tự chuyển cho chính mình (`ErrInvalidInput`); **lock 2 membership theo thứ tự UUID tăng dần tránh deadlock chuyển chéo** (:830-852, `bytesLess` :1108-1116); target phải active; demote→promote→activity `captain_transferred`.
- **RenameGroup** (:332-341): Captain only, 1–100 rune, activity `group_renamed` kèm old/new name.
- **DisbandGroup** (:343-348 → repo :938-1024): Captain only; **chặn khi còn batch bulk finalize queued/processing** → `BulkFinalizeInProgressError{ActiveBatchID}` (:972-980); **chặn khi còn bill draft/reviewed hoặc debt mở** → `UnsettledObligationsError{DraftOrReviewedBillCount, OpenDebtCount}` (:982-995); archive: deactivate members + revoke invites + status='archived' + activity `group_archived`.
- **ListActivities** (:364-373): chỉ member active đọc; cursor keyset.

### 2.3 Domain errors (`group/domain/errors.go:5-70`)
`ErrInvalidInput`, `ErrGroupNotFound` (nhóm không có HOẶC caller không phải member), `ErrInvalidCursor`, `ErrCaptainRequired` (kèm che tồn tại nhóm), `ErrInviteNotFound`, `ErrInviteUnavailable`, `ErrInviteCodeCollision`, `ErrGroupMemberLimitReached` (>50), `ErrForbidden`, `ErrCaptainTransferRequired`, `ErrMemberNotFound`, `ErrCaptainTransferConflict`, structs `BulkFinalizeInProgressError{ActiveBatchID}`, `OpenDebtsError{PayableAmount, ReceivableAmount}`, `UnsettledObligationsError{...}`.

### 2.4 Edge cases group
1. Anti-enumeration nhất quán (not-found == non-member) cho detail/invite mutation.
2. Nhóm full 50: join bị chặn dù invite còn valid; serialization bằng group row lock nên 2 join đồng thời không vượt cap.
3. Join lại nhóm cũ → reactivation giữ nguyên member_id (lịch sử hóa đơn/nợ không đứt).
4. Rời nhóm khi còn nợ → blocked kèm số tiền cụ thể trong error fields (spec 0002 AC-6).
5. Captain transfer deadlock-free (lock ordering) + NOWAIT conflict.
6. Invite collision retry ≤5; metadata activity không bao giờ chứa invite code (invariant 10 — repo :385-398).
7. Idempotency: revoke invite, leave/remove, join khi đã active.
8. Mọi mutation ghi activity ATOMIC trong cùng transaction (insertActivity :400-412).

---

## 3. MODULE BILL (bao gồm OCR, SSE, Group Bill Close)

### 3.1 Endpoints
**RegisterRoutes** (`bill/delivery/http/handler.go:60-78`, mount `/api/v1/bills`, tất cả `liveAuth`):

| Method+Path | Handler |
|---|---|
| POST `/` | CreateBill (multipart ảnh 1–5 hoặc JSON thủ công) |
| GET `/` | ListBills (offset legacy) |
| GET `/{id}` | GetBillDetail |
| GET `/{id}/events` | SSE StreamBillEvents |
| POST `/{id}/ocr-retry` | RetryOCR |
| POST `/{id}/apply-candidate` | ApplyCandidate |
| POST `/calculate` + POST `/{id}/calculate` | CalculateBreakdown (stateless) |
| PUT/PATCH `/{id}` | UpdateDraftBill |
| POST `/{id}/review` | ReviewBill |
| POST `/{id}/finalize` | FinalizeBill |
| POST `/{id}/void` | VoidBill |
| DELETE `/{id}` | DeleteDraftBill |

**RegisterGroupCloseRoutes** (`close_handler.go:17-23`, mount `/groups`):
POST `/{groupId}/bills/lock-submissions` · POST `/{groupId}/bills/finalize-all` · GET `/{groupId}/bill-finalize-batches/{batchId}`.

### 3.2 Trạng thái & thuật toán chia tiền
- Bill lifecycle: `draft` → (review) → `reviewed` → (finalize) → `finalized` → (void) → `voided`. Version int optimistic locking trên mọi mutation.
- **Floor allocation** (`usecase/allocation.go:93-230`) — thuật toán 2 lượt:
  - Trọng số trên thang `weightScale=1e8`; thiếu weight/ratio → mặc định 1 (:50-61).
  - Tiền món chia sàn theo trọng số; phí dịch vụ/VAT/giảm giá CHUNG chia sàn theo tỷ lệ tiền hàng (:169-183).
  - Lượt 1 (non-Creditor): **discount share bị chặn trần tại đúng số tiền người đó phải trả** (FinalAmount=0 tối thiểu) (:192-201).
  - Lượt 2: **Creditor hấp thụ phần dư/remainder**: `FinalAmount = allocTotal − sumOthers`; `RoundingAdjustment` = hiệu giữa final và tổng 4 thành phần sàn của chính Creditor (:203-211). **Tổng luôn khớp tuyệt đối theo cấu trúc** (invariant check :215-227).
  - `allocTotal` tính từ TỔNG THÀNH PHẦN chứ không lấy Total client khai (tránh OCR sai đẩy chênh lệch lên Creditor) (:160-167).
  - Creditor âm → `ErrDiscountNotAllocatable` (KHÔNG kẹp) (:206-210).
- **Reconciliation blockers** (`usecase/reconciliation.go:14-114`): `ITEM_UNASSIGNED`, `INACTIVE_MEMBER_ASSIGNED` (gán món cho member đã rời), `DISCOUNT_EXCEEDS_BILL`, `DISCOUNT_NOT_ALLOCATABLE`, `CREDITOR_REQUIRED`, cộng warning lưu từ OCR `SUBTOTAL_MISMATCH`/`TOTAL_MISMATCH`. Một nguồn sự thật duy nhất cho read/review/finalize.
- Giảm giá 2 lớp (Spec AC-17..21): `final_price = line_total − discount_amount` per item; phân bổ dùng **FinalPrice** của món (`toAllocationInput` service.go:1196-1202); chỉ `general_discount = discount − total_item_discount` được chia tỷ lệ; server tự tính, không nhận final_price từ client; DB CHECK `check_bills_discount_composition` (migration 000007).

### 3.3 UseCases chính (`usecase/service.go`)
- **CreateBill** (:191-412): member active check → pre-check submission lock (rẻ, trước upload) → ≤5 ảnh, ≤100 items, discount ≥ 0 → replaces_bill_id phải là bill voided → process+upload ảnh (rollback xóa ảnh nếu fail; nếu bị chặn lock giữa chừng → **enqueue media cleanup bền vững**, fallback direct delete, join errors :379-402) → item discounts validation → tạo OCRJob nếu có ảnh → insert + **enqueue River job trong cùng tx** (BeforeCommit hook) → re-check lock trong tx là nguồn sự thật cuối.
- **GetBillDetail** (:415-473): signed URLs 5 phút; preview breakdown + mismatch_codes cho draft/reviewed; metric preview latency.
- **CalculateBreakdown** (:476-563): stateless, yêu cầu creditor_member_id (`ErrCreditorRequired`), enrich user info, trả is_balanced.
- **RetryOCR** (:597-665): **chỉ Creditor hoặc Captain**; bill draft/reviewed + có ảnh; **chỉ 1 job OCR active/bill** (partial unique index `uq_ocr_jobs_active_bill`) → `ErrOcrAlreadyRunning`; **giới hạn 5 lần thủ công/24h** (configurable `BILL_OCR_MANUAL_LIMIT`) → `ErrOcrLimitReached` (HTTP 429); insert job + enqueue cùng tx.
- **ApplyCandidate** (:668-768): quyền như RetryOCR; job phải succeeded + thuộc đúng bill (job khác bill → not-found để không leak); **version client phải = bill version hiện tại** (`ErrVersionConflict`) và **= version lúc chạy OCR** (`ErrOcrResultStale` + metric stale apply); apply candidate → items mới gán đều weight 1.0 cho mọi member active.
- **UpdateDraftBill** (:771-874): Creditor/Captain; reviewed→draft khi sửa; version conflict qua expected_version.
- **ReviewBill** (:877-925): chỉ từ draft; idempotent nếu đã reviewed đúng version; chạy evaluateAllocation → blocker → 422.
- **FinalizeBill** (:929-1008): **CHỈ CAPTAIN**; phải reviewed; version khớp; **Creditor phải cấu hình tài khoản ngân hàng** (`ErrBankAccountRequired` → 422 BANK_ACCOUNT_REQUIRED, :982-987); re-validate allocation; build plan (shares snapshot + debts awaiting cho amount>0 non-Creditor + notification `bill_finalized` cho từng member) → finalizeCore trong tx (repository.go:757-858): cập nhật status, xóa-ghi lại shares, insert debts, insert notifications, enqueue push jobs (hook), activity `finalized_bill`. Metric duration.
- **VoidBill** (:1112-1148 → repo :861-961): **CHỈ CAPTAIN**, reason bắt buộc 1–500 ký tự; chỉ finalized; **mọi debt của bill phải đang awaiting (chưa payment)** → ngược lại `ErrPaymentAlreadyStarted`; payment pending_proof liên quan bị chuyển `superseded` (QR intent chưa giữ nợ); void debts; activity `voided_bill`. Lock ordering: group → bill → debts (UUID order).
- **DeleteDraftBill** (:1151-1179): Creditor/Captain, chỉ draft; enqueue ảnh vào media cleanup trong tx xóa; hard delete cascade.
- **Idempotency keys** (:1246-1323): bảng `bill_idempotency_keys`, TTL 24h; key reuse khác payload → `ErrIdempotencyKeyReused`; in_progress của op khác → `ErrIdempotencyInProgress`; Release khi mutation fail để retry không kẹt 409.

### 3.4 Group Bill Close (Spec 0008) — `usecase/bill_close.go`
- **LockSubmissions** (:52-71): Captain only; **khóa MỘT CHIỀU** (không unlock trong V1); idempotent (đã khóa → 200 cùng mốc thời gian, không ghi activity); repo (`bill/repository/postgres/bill_close.go:48-116`) khóa group → check captain → COALESCE set `bill_submission_locked_at` → activity `bill_submission_locked` chỉ khi đổi.
- **StartBulkFinalize** (:76-138 → repo :124-307): một tx: lock group → Captain → bật khóa → **chặn khi còn batch active** (`BulkFinalizeInProgressError{ActiveBatchID}`, partial unique `uq_bill_finalize_batches_active`) → capture mọi bill draft/reviewed kèm version → tạo batch + items → activity started → **enqueue từng item job trong hook beforeCommit (không mạng giữ lock)**; batch rỗng → completed ngay + notification Captain. Hỗ trợ idempotency key complete trong cùng tx (:107-123).
- **ProcessBulkFinalizeItem** (:188-312): MỖI bill một transaction riêng (1 bill fail không rollback bill khác): thứ tự khóa group → batch → item → bill; item không pending → skip an toàn khi River giao lại (at-least-once); phân loại: bill deleted → failed DELETED; **bill đã finalized đúng captured_version+1 → đánh dấu finalized không ghi trùng**; version lệch → VERSION_CONFLICT; voided → failed; draft → review trong tx rồi finalize; **thiếu bank/discount → thất bại ổn định commit ngay**; lỗi tạm thời → return err để River retry với item còn pending; sau mỗi item thử `TryCompleteBatch` → completed + notification Captain + metric.
- **GetFinalizeBatch** (:156-174): **chỉ Captain** đọc (member thường không suy ra ID batch/kết quả từng bill).

### 3.5 OCR Worker & SSE
- **OCRWorker** (`jobs/ocr_worker.go`): job kind `bill_ocr` (:58). Work (:121-257): idempotent skip nếu succeeded/failed; CAS processing (conflict → worker khác đã nhận); download ảnh Cloudinary (private) → **ghép dọc 1–5 ảnh thành JPEG 90%** (stitchReceiptImages :464-509, resize >1200px) → gọi LlamaExtract với timeout riêng; lỗi schema AI → failed không retry; hết MaxAttempts → failed với mã đóng (`provider_timeout/provider_unavailable/provider_error/download_failed/no_images/bill_not_found/schema_invalid` :28-36); NextRetry = exponential backoff `base * 2^(attempt-1)` cap attempt 20 (:85-98); phát SSE `ocr.updated` (processing/succeeded/failed).
- **Retention jobs** (`jobs/retention.go`): `ocr_raw_retention_cleanup` (xóa raw_response OCR >30 ngày, RunOnStart, mỗi 24h) và `bill_idempotency_key_cleanup` (mỗi 24h). `PollQueueDepth` gauge 15s (bootstrap :290-291).
- **SSE** (`delivery/http/sse_hub.go`, `sse_handler.go`): Hub in-process theo bill_id + đồng bộ đa replica qua **PostgreSQL LISTEN/NOTIFY** (goroutine `StartPostgresListener` bootstrap :288); heartbeat 15s, max connection age 15 phút; auth: member active của nhóm (:90-93).

### 3.6 Domain errors (`bill/domain/errors.go`) — xem danh sách đầy đủ :5-118; mapping HTTP tại `handler.go:683-808` (ví dụ ErrSubmissionLocked→409 BILL_SUBMISSION_LOCKED, ErrOcrLimitReached→429, ErrDiscountNotAllocatable→422 DISCOUNT_NOT_ALLOCATABLE, BulkFinalizeInProgress→409 kèm `active_batch_id`).

---

## 4. MODULE SETTLEMENT

### 4.1 Endpoints (`settlement/delivery/http/handler.go:40-50`, mount `/api/v1/groups`, tất cả `liveAuth`)

| Method+Path | Handler |
|---|---|
| GET `/{groupId}/expenses/me` | ListExpenses |
| GET `/{groupId}/debts` | ListDebts (filter debtor/creditor/status, cursor) |
| POST `/{groupId}/payments/qr` | GeneratePayment (**bắt buộc Idempotency-Key**) |
| GET `/{groupId}/payments/{paymentId}` | GetPayment |
| POST `/{groupId}/payments/{paymentId}/proof` | SubmitProof (multipart, bắt buộc key) |
| POST `/{groupId}/payments/{paymentId}/confirm` | ConfirmPayment (key) |
| POST `/{groupId}/payments/{paymentId}/reject` | RejectPayment (key + reason 1–500) |
| POST `/{groupId}/debts/{debtId}/remind` | RemindDebt (key) |

### 4.2 UseCases (`usecase/service.go`)
- **GeneratePayment** (:83-108 → repo :327-488): DebtIDs 1–100, parse + **dedupe + sort** để canonical hash; idempotency qua `beginIdempotency` (hash mismatch → `ErrIdempotencyConflict`; in_progress → `ErrIdempotencyInProgress`; completed → replay response JSON); debtor = caller (active member); **creditor phải active + có bank profile đầy đủ + bank supported trong directory VietQR** → `ErrBankAccountRequired` / `ErrCreditorNotFound`; lock debts FOR UPDATE (status awaiting, đúng cặp debtor→creditor); thiếu/leak 1 debt → `ErrDebtsNotAwaiting`; **nếu đã tồn tại payment pending_proof cùng cặp: cùng tập debt → trả lại QR cũ (200, không tạo mới); khác tập → payment cũ thành `superseded`** (:414-441); sinh reference_code `PAY` + 8 ký tự Base32-ish (alphabet không nhập nhằng :834-845); build VietQR payload; insert payment + payment_debts + activity `payment_created` + **notification cho creditor** (hook NotifyTx trong tx); complete idempotency 201.
- **SubmitProof** (service :127-173): validate ảnh bằng **magic bytes** (JPEG/PNG/HEIC sniffing độc lập với multipart header — `validProofImage`/`DetectProofContentType` :184-220), ≤10MB; note ≤500 rune; 2 pha: `PrepareProof` (reserve idempotency + check debtor + payment pending_proof + creditor bank) → upload Cloudinary `payments/<pid>/proofs/<opID>` → `SubmitProof` (resume idempotency; **debts phải còn awaiting toàn bộ**; payment → pending_confirmation, debts → pending_confirmation; activity + notify creditor). Upload fail → ResetProofAttempt(replaceOperation=false); DB fail → xóa ảnh (fallback queue media cleanup) + reset attempt với operation mới (:158-170).
- **ConfirmPayment / RejectPayment** (:227-258 → repo `finishPayment` :1009-1149): **chỉ CREDITOR**; mọi debt phải pending_confirmation + trỏ đúng payment; confirm → payments confirmed + debts settled (settled_at); reject (reason 1–500) → payments rejected + **debts quay lại awaiting, payment_id=NULL** (có thể tạo QR mới); idempotency replay; activity + notify debtor.
- **RemindDebt** (:262-269 → repo :1150-1264): caller = creditor **hoặc Captain**; debt phải awaiting; **rate limit nghiệp vụ: tối đa 3 lời nhắc/debt và cách nhau ≥24h** (`chk_debts_reminder_count` CHECK 0..3; check count>=max \|\| last<24h → `ErrReminderRateLimited` :1229-1231); activity `debt_reminded` + notify debtor.
- **ListExpenses/ListDebts** (:277-296): cursor keyset; status filter whitelist (`awaiting\|pending_confirmation\|settled`); limit 1–100; kèm summary (total owed/settled/receivable/net) và debt matrix.

### 4.3 Domain errors (`domain/errors.go`)
`ErrInvalidInput`, `ErrInvalidImage`, `ErrInvalidCursor`, `ErrGroupNotFound`, `ErrDebtNotFound`, `ErrPaymentNotFound`, `ErrCreditorNotFound`, `ErrForbidden`, `ErrBankAccountRequired`, `ErrDebtsNotAwaiting`, `ErrPaymentNotPendingProof`, `ErrPaymentNotPendingConfirmation`, `ErrDebtNotAwaiting`, `ErrReminderRateLimited`, `ErrIdempotencyConflict`, `ErrIdempotencyInProgress`, `ErrStorageUnavailable`.

### 4.4 Edge cases settlement
1. State machine payment nghiêm ngặt enforced bởi DB CHECK matrix `chk_payments_state_matrix` (migration 000009 :35-59) — mỗi trạng thái ràng buộc bộ cột timestamp/bank snapshot/rejection reason.
2. Chỉ 1 payment pending_proof mỗi cặp debtor→creditor/nhóm (partial unique `uq_payments_pending_proof_pair`); tạo QR mới với tập debt khác → superseded QR cũ.
3. Debtor nộp proof nhưng 1 debt nào đó đã bị xử lý nơi khác → `ErrDebtsNotAwaiting` (kiểm tra RowsAffected đúng số debt :971-974).
4. Confirm/reject race: debts FOR UPDATE + check payment_id khớp + RowsAffected.
5. Reminder spam: max 3 + cooldown 24h, cả manual lẫn automated dùng chung reminder_count.
6. Idempotency hai tầng: canonical request hash (payload + image sha256) chống key-reuse; retry_after cho phép resume in_progress sau crash giữa upload và submit (PrepareProof :616-626).
7. Compensation: upload OK mà commit fail → xóa object, fallback queue cleanup bền vững.
8. `submitted_at IS NULL = recipient_bank_* IS NULL` snapshot consistency CHECK.

### 4.5 Background jobs settlement (`jobs/workers.go`)
- `settlement_scan` (mỗi giờ, RunOnStart): `ProcessAutomatedReminders` — debts awaiting, tạo trước `REMINDER_STALE_AGE` (mặc định 72h), count<3, last reminded ≥24h trước, **FOR UPDATE SKIP LOCKED LIMIT 100**, tăng count + activity actor_kind='system' + notify debtor (:1266-1311); `ProcessStalledPayments` — payments pending_confirmation quá `STALLED_CONFIRMATION_AGE` (48h) chưa alerted → đánh dấu stalled_alerted_at + activity `payment_stalled_confirmation` + notify creditor (:1312-1360).
- `settlement_cleanup` (mỗi ngày): xóa idempotency keys hết hạn + `ProcessMediaCleanup` (claim SKIP LOCKED, backoff 5min×2^n cap, max 10 attempts).

---

## 5. MODULE NOTIFICATION

### 5.1 Endpoints (`notification/delivery/http/routes.go:10-17`, mount `/api/v1/notifications`, tất cả `liveAuth`)
GET `/` (list, offset pager) · GET `/unread-count` · PATCH `/read-all` · PATCH `/{id}/read`.

### 5.2 Kiến trúc tạo thông báo
- **In-app + push atomic** (`usecase/service.go:54-132`): `SendToUser` ghi bản ghi notifications và enqueue River job `send_notification` **trong cùng transaction** (`WithTx` + `EnqueueNotificationTx`) — không bao giờ có record mồ côi hay job trùng. Fallback không có enqueuer: gửi push trực tiếp.
- Validation: title/body bắt buộc; truncate theo RUNE về giới hạn CHECK DB (type≤60, title≤255, body≤1000) thêm "..." (:136-146) thay vì 500.
- **NotificationWorker** (`jobs/send_notification.go:57-98`): job chỉ mang `NotificationID` (handle idempotency, at-least-once); load lại nội dung từ DB; lấy FCM token active mới nhất từ sessions (query `WHERE revoked_at IS NULL AND expires_at > now()` — queries/notification.sql:41); token rỗng → bỏ qua; **token invalid (user gỡ app) → ClearFCMToken và kết thúc**; invalid message → log, không xóa token; lỗi khác → return err để River retry backoff.
- FCM disabled (thiếu credentials): notifier = typed-nil được kiểm tra cẩn thận ở bootstrap (app.go:123-160), worker vẫn đăng ký để server chạy bình thường.

### 5.3 Các loại notification thực tế trong code
- `bill_finalized` — tạo khi FinalizeBill cho từng member (bill/service.go:1072-1093), body kèm số tiền phần mình / tổng cho Creditor.
- Từ settlement (`integration/notification.go:45-61`): `payment_created` (cho creditor), `payment_submitted` (cho creditor), `payment_confirmed` + `payment_rejected` (cho debtor), `debt_reminded` (manual + automated, cho debtor), `payment_stalled_confirmation` (cho creditor).
- `bill_bulk_finalize_completed` — cho Captain khi batch xong (bill/repository/postgres/bill_close.go:311-348).
- Domain constants khai báo thêm (`notification/domain/notification.go:32-40`): `payment_reminder`, `new_bill`, `group_invitation`, `bill_updated`, `system_announcement` (một số chưa có producer).

### 5.4 Edge cases notification
1. Ownership: MarkAsRead query `WHERE id=$1 AND user_id=$2` — không đọc/đánh dấu hộ người khác.
2. FCM token chết → tự dọn khỏi session; message lỗi nội dung → không xóa token nhầm.
3. Truncation rune-based khớp `char_length` của Postgres.
4. Payload JSONB → map[string]string cho FCM data (nil-safe).
5. Notification không tồn tại khi worker xử lý → hoàn tất job, không retry.

---

## 6. MODULE ADMIN

### 6.1 Endpoints (`admin/delivery/http/routes.go:12-21`, mount `/api/v1/admin`, middleware `liveAuth` + `RequireRole("admin")`)

| Method+Path | Handler | Chức năng |
|---|---|---|
| GET `/accounts` | ListAccounts | search (email/name/phone), filter status/role, sort by created_at/display_name/email asc/desc, page/limit (clamp ≤100) |
| GET `/accounts/{id}` | GetAccountDetail | chi tiết đầy đủ |
| PUT `/accounts/{id}/status` | UpdateAccountStatus | active/suspended/locked |
| GET `/system/overview` | GetSystemOverview | thống kê toàn hệ thống |

### 6.2 UseCases (`admin/usecase/service.go`)
- **ListAccounts** (:53-133): whitelist sort fields/orders; status ∈ {pending_verification, active, suspended, locked}; role ∈ {user, admin}; clamp limit 100; pagination offset + total pages.
- **GetAccountDetail** (:136-141): trả SafeUser + failed_login_count, login_blocked_until, bank snapshot **đã mask số TK (chỉ 4 số cuối — `MaskBankAccount` repo :434-441)**, số session active, danh sách nhóm, financials (outstanding debts/credits), audit logs gần đây.
- **UpdateAccountStatus** (:144-173): status ∈ {active,suspended,locked}; **suspend/lock bắt buộc reason** (`ErrReasonRequired`); reason rỗng khi reactivate → tự điền "Reactivated by admin" (do audit log NOT NULL). Repo `UpdateAccountStatusWithRevocation` (repository.go:226-355) trong MỘT tx: **anti-TOCTOU — check self/admin/pending_verification ngay dưới transaction** (:251-274):
  - `ErrCannotModifySelf` — admin không tự đổi trạng thái mình;
  - `ErrCannotModifyAdmin` — không suspend/lock admin khác;
  - `ErrInvalidStatusTransition` — target đang pending_verification không chuyển qua API này.
  - suspend/locked → **thu hồi toàn bộ sessions + refresh tokens** (reason `admin_suspended`/`admin_locked`);
  - ghi `admin_audit_logs` (enum action suspend/lock/reactivate);
  - trả kèm `WarningMeta{UnsettledDebtsCount, UnsettledCreditsCount}` cảnh báo nghĩa vụ tài chính chưa xong.
- **GetSystemOverview** (:176-178 → repo :357-432): thống kê users theo status, tổng groups, bills (finalized/draft), **debts theo 5 trạng thái** (awaiting/pending_confirmation/stalled_confirmation/rejected/settled), media_cleanup_jobs pending, OCR jobs (queued/processing/succeeded/failed), runtime (goroutines, alloc memory, uptime).

### 6.3 Domain errors (`admin/domain/errors.go`)
`ErrInvalidInput`, `ErrAccountNotFound`, `ErrCannotModifySelf`, `ErrCannotModifyAdmin`, `ErrInvalidStatusTransition`, `ErrReasonRequired`, `ErrForbidden`.

---

## 7. BACKGROUND JOBS TỔNG HỢP (River Queue)

Đăng ký tại `bootstrap/app.go:142-212`; workers:

| Job Kind | File | Khi enqueue | Worker làm gì |
|---|---|---|---|
| `send_notification` | notification/jobs/send_notification.go | cùng tx với CreateNotification (finalize bill, settlement events, bulk close) | push FCM tới token active, clear token invalid |
| `bill_ocr` | bill/jobs/ocr_worker.go | cùng tx CreateBill/RetryOCR khi có ảnh | download ảnh, ghép trang, gọi LlamaExtract, lưu candidate, SSE broadcast; retry exp backoff |
| `bill_bulk_finalize_item` | bill/jobs/bulk_finalize_worker.go | cùng tx StartBulkFinalize cho từng bill captured | review+finalize 1 bill trong 1 tx riêng |
| `ocr_raw_retention_cleanup` | bill/jobs/retention.go | periodic 24h + RunOnStart | purge raw_response OCR > N ngày |
| `bill_idempotency_key_cleanup` | bill/jobs/retention.go | periodic 24h + RunOnStart | purge idempotency keys hết hạn |
| `settlement_scan` | settlement/jobs/workers.go | periodic 1h + RunOnStart | automated reminders + stalled payment alerts |
| `settlement_cleanup` | settlement/jobs/workers.go | periodic 24h + RunOnStart | purge idempotency + media cleanup |

**Ngoài River** (goroutine thường): auth cleanup workers (`auth/jobs/workers.go`, ticker interval config) — CleanupExpiredAuth + MediaCleanup retry; SSE Postgres LISTEN listener; PollQueueDepth gauge 15s.

---

## 8. DB SCHEMA CHÍNH (db/migrations, goose single-file Up/Down)

**Enums** (000001, bổ sung về sau): `account_status(pending_verification,active,suspended,locked)`, `user_role(user,admin)`, `group_role(captain,member)`, `member_status(active,inactive)`, `group_status(active,archived)` (000011), `bill_status(draft,reviewed,finalized,voided)` (reviewed/voided thêm ở 000006), `ocr_job_status(queued,processing,succeeded,failed)`, `debt_status(awaiting,pending_confirmation,stalled_confirmation,rejected,settled,voided)`, `payment_status(pending_proof,pending_confirmation,confirmed,rejected,superseded)` (000009), `token_type(email_verification,password_reset)`, `admin_action(suspend,lock,reactivate)`, `activity_type` (~20 giá trị), `bulk_finalize_status(queued,processing,completed)`, `bulk_finalize_item_status(pending,finalized,failed)`, `idempotency_state(in_progress,completed)`, `activity_actor_kind(member,system)`.

**Auth**: `users` (email CITEXT unique, phone unique E.164, bank triple all-or-nothing CHECK, failed-login counters), `sessions` (**unique 1 active/user** `uq_sessions_one_active_per_user`, revocation pair CHECK, fcm_token — 000003), `session_refresh_tokens` (token_hash BYTEA unique 32B, used_at cho rotation/reuse-detection), `user_tokens` (unique 1 active/type, terminal state CHECK, attempt_count — 000005), `auth_rate_limit_events`, `media_cleanup_jobs` (attempt ≤10, unique open object_key).

**Group**: `groups` (name 1–100 trimmed CHECK, currency='VND' CHECK, status, bill_submission_locked_at — 000012), `group_members` (**UNIQUE(group_id,user_id) — join lại = UPDATE**, composite FK anchor `(id,group_id)`, **unique 1 captain active/nhóm**, CHECK status↔left_at), `group_invites` (code Base62-8 unique + CHECK, max_uses/use_count CHECK, FK created_by→(id,group_id)), `group_activities` (actor_member nullable cho system — 000009, metadata JSONB, timeline index).

**Bill**: `bills` (composite FK creditor, amounts ≥0, version, split_method CHECK, mismatch_codes TEXT[], reviewed_by/at, voided_at, `uq_bills_replacement` unique replaces_bill_id, `discount = total_item_discount + general_discount` CHECK — 000007), `bill_items` (position, `final_price = line_total - discount_amount` CHECK), `bill_item_assignments` (**UNIQUE(bill_item_id,member_id)** — 1 member 1 lượt/món, weight>0), `bill_images` (1–5, UNIQUE(bill_id,position)), `bill_shares` (snapshot finalize, final_amount ≥0, UNIQUE(bill_id,member_id)), `ocr_jobs` (**partial unique 1 active job/bill**, candidate JSONB, version), `bill_idempotency_keys` (PK actor+operation+key_hash, TTL 24h), `group_bill_finalize_batches` (state-matrix CHECK, **partial unique 1 active batch/group**, counter invariant finalized+failed=target khi completed) + `group_bill_finalize_items` (PK(batch,bill), item state-matrix CHECK, bill_id cố ý KHÔNG có FK tới bills để draft xóa được — migration 000012 :69-72).

**Settlement**: `payments` (amount>0, reference_code unique toàn hệ thống, **chk_payments_state_matrix** ràng buộc trạng thái↔cột, debtor≠creditor, `uq_payments_pending_proof_pair` partial unique), `debts` (amount>0, **UNIQUE(bill_id,debtor,creditor)** gộp nợ, CHECK awaiting↔no-payment (mở rộng awaiting\|voided — 000006), settled↔settled_at, reminder_count 0–3, payment FK composite cùng nhóm), `payment_debts` (PK(payment,debt), double composite FK), `payment_idempotency_keys`, view `v_member_balances` (net balance tính-on-read, chỉ tính awaiting+pending_confirmation — 000009 :144-156).

**Notification/Admin**: `notifications` (title/body CHECK lengths, unread partial index), `admin_audit_logs` (reason NOT NULL <> '', enum action).

**Khóa & thứ tự lock xuyên module**: mọi bảng scoped-nhóm mang group_id với composite FK `(id, group_id)` chặn dữ liệu trỏ chéo nhóm; mọi mutation nhóm/bill/settlement serialize qua group row lock (`LockActiveGroup`), VoidBill lock group→bill→debts theo UUID (comment Invariant 12 — bill repository.go:869-902).

---

## 9. ĐỐI CHIẾU OPENAPI (docs/openapi.yaml, 2729 dòng)

Spec phủ đầy đủ 45 path, khớp router: auth (sign-up…reset-password), users/me*, banks, groups CRUD + invites/join/members/role/activities, group bill close (lock-submissions, finalize-all, bill-finalize-batches), notifications 4 endpoints, bills (create/list/calculate/{id} CRUD + ocr-retry/apply-candidate/events SSE/review/finalize/void), settlement (expenses/me, debts, remind, payments/qr, get, proof, confirm, reject), admin (accounts list/detail/status, system/overview). Không thấy endpoint trong code mà thiếu trong spec (ngoài `/health*`, `/metrics` hạ tầng).

---

## 10. TÓM TẮT EDGE CASES THEO YÊU CẦU (chốt để đưa vào flow docs)

| Tình huống | Xử lý thực tế trong code | Vị trí |
|---|---|---|
| Access token hết hạn | liveAuth kiểm session DB mỗi request → 401; FE dùng refresh | middleware/auth.go:54-60 |
| Refresh token reuse | revoke toàn bộ session + tokens, `SESSION_REVOKED` | auth repo :307-314 |
| Email trùng | unique constraint → `EMAIL_ALREADY_EXISTS` 409 | auth repo :736-747 |
| OTP sai 5 lần | supersede token vĩnh viễn | auth repo :154-168 |
| Login brute force | 5 sai/15′ → block 15′ + RetryAfter | auth repo :187-226 |
| Nhóm full 50 | group lock + count check → MEMBER_LIMIT | group repo :620-624 |
| Rời nhóm khi còn nợ | sum open debts 2 chiều → 409 kèm amounts | group repo :741-751 |
| Captain rời/bị xóa | chặn, phải transfer trước | group repo :737-739 |
| Concurrent captain transfer | NOWAIT → 409 CONFLICT; lock UUID order chống deadlock | group repo :804-852 |
| Join race | serialize qua group row lock; already-active idempotent | group repo :572-604 |
| Gán món cho member đã rời | blocker INACTIVE_MEMBER_ASSIGNED chặn review/finalize | reconciliation.go:55-68 |
| Chia tiền không đều/remainder | floor 2 lượt, Creditor hấp thụ dư, RoundingAdjustment; invariant sum check | allocation.go:93-230 |
| Discount vượt khả năng hấp thụ | chặn trần per-member; Creditor âm → DISCOUNT_NOT_ALLOCATABLE (không kẹp) | allocation.go:192-210 |
| Concurrent claim OCR job | partial unique 1 active job/bill + CAS processing | ocr_worker.go:148-159 |
| Concurrent bulk finalize item | item status CAS trong tx; duplicate delivery no-op | bill_close.go:222-238 |
| Xóa người dùng/bill giữa batch | bill deleted/version lệch/voided → item failed ổn định | bill_close.go:244-267 |
| Void bill khi đang thanh toán | debts phải awaiting → PAYMENT_ALREADY_STARTED; QR intent → superseded | bill repo :897-921 |
| Payment confirm/reject race | lock debts + payment + RowsAffected check | settlement repo :1051-1088 |
| Reminder spam | max 3 + 24h cooldown (DB CHECK + logic) | settlement repo :1229-1231 |
| Idempotency | bill + payment 2 hệ riêng; key reuse khác payload → 409; release khi fail | bill service :1246-1295 |
| Upload mồ côi | compensating delete + media_cleanup_jobs bền vững retry exp backoff ≤10 lần | auth service :336-345, settlement service :163-170 |
| Admin tự khóa mình / khóa admin | ErrCannotModifySelf / ErrCannotModifyAdmin trong tx (anti-TOCTOU) | admin repo :251-274 |
| Suspend user | thu hồi toàn bộ session + refresh token + audit log + warning nợ chưa xong | admin repo :276-354 |
