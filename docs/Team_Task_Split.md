# PaySplit — Phân chia công việc 3 người & Quy chuẩn coding

> Nguồn: `PRD/Product_Requirement_Document.md` (FR 4.1.1–4.1.23, 4.2.1) + `Database/dbv1.sql`.
> Bối cảnh: đã có base project Backend (Go/Chi) và Frontend (Flutter). Timeline 2 tuần (W1/W2) theo Mục 7 PRD.

---

## 0. Nguyên tắc chia việc

1. **Chia dọc, không chia ngang.** Không chia kiểu "1 người làm BE, 1 người làm FE, 1 người làm DB" — kiểu đó ai cũng phải chờ người khác. Mỗi người ôm trọn **một nhóm nghiệp vụ từ DB → API → màn hình Flutter**.
2. **Sở hữu file độc quyền.** Mỗi thư mục/file chỉ có đúng 1 chủ. Muốn sửa file của người khác → nhắn chủ file sửa, không tự sửa. Xem §3.
3. **Ký hợp đồng trước, code sau.** Ngày 1 cả nhóm ngồi chung 2–3 tiếng chốt: API contract (OpenAPI), Go interface (port) giữa các module, error format, migration đầu. Sau buổi đó 3 người tách ra chạy song song, không ai block ai.
4. **Chặn nhau thì dùng stub.** Khi module của bạn cần module người khác mà họ chưa xong: implement `FakeXxx` trong package của **bạn**, code tiếp, ráp thật ở W2.
5. **Không ai chờ ai quá 1 ngày.** Blocked > 1 ngày → báo mentor (Risk R5/R6 trong PRD).

---

## 1. Bản đồ sở hữu module

| | **Người A — Platform & Identity** | **Người B — Group & Bill/OCR** | **Người C — Money (Split/Settlement/QR)** |
|---|---|---|---|
| **Use case PRD** | UC01–06, UC20–23 | UC07–14 | UC15–19 + FR 4.2.1 |
| **FR** | 4.1.1→4.1.6, 4.1.20→4.1.23 | 4.1.7→4.1.14 | 4.1.15→4.1.19, 4.2.1 |
| **Bảng DB sở hữu** | `users`, `sessions`, `user_tokens`, `notifications`, `admin_audit_logs` | `groups`, `group_members`, `group_invites`, `bills`, `bill_items`, `bill_item_assignments`, `ocr_jobs`, `group_activities` | `debts`, `payments`, `v_member_balances` |
| **Vai trò phụ** | Nền tảng dùng chung: middleware, config, storage, mailer, observability, Docker, CI | Nhật ký nhóm (`group_activities`) — cung cấp port cho A & C ghi log | Toán tiền thuần (pure logic, test 100%) |

**Vì sao chia thế này:**
- A là đường **critical path ngày đầu** (auth + middleware + Docker) → A phải xong sớm nhất, sau đó A rảnh hơn nên gánh thêm Admin + Notification.
- B nặng về I/O và tích hợp ngoài (upload ảnh, OCR LLM, SSE) — độc lập hoàn toàn với toán tiền.
- C nặng về logic thuần (Hamilton rounding, gộp nợ, VietQR TLV/CRC) — **có thể code + unit test 100% mà không cần DB của B chạy xong**, chỉ cần struct đầu vào.

---

## 2. Ngày 1 — Việc làm chung (bắt buộc, trước khi tách)

Ngồi cùng nhau, ra được 5 artifact sau rồi mới ai về máy nấy:

| # | Artifact | File | Ai commit |
|---|---|---|---|
| 1 | Migration khởi tạo toàn bộ schema từ `dbv1.sql` | `migrations/000001_init.up.sql` / `.down.sql` | A |
| 2 | Chuẩn error envelope + bảng mã lỗi | `docs/api/errors.md` | A |
| 3 | OpenAPI khung + chia 3 file path | `docs/api/openapi.yaml`, `paths/{auth,group,money}.yaml` | mỗi người 1 file |
| 4 | **Port interfaces** giữa 3 module (chỉ interface, chưa impl) | `internal/port/port.go` | A gõ, 3 người cùng chốt |
| 5 | Docker Compose (postgres + minio + app) chạy được `make dev` | `docker-compose.yml`, `Makefile` | A |

### 2.1 Các port phải chốt trong ngày 1

```go
// internal/port/port.go — file DUY NHẤT cả 3 cùng đọc, sửa phải có consensus.
package port

// ── B cung cấp, C tiêu thụ (dùng cho Finalize Bill) ──────────────────
type BillReader interface {
    // Trả về snapshot bill + items + assignments để tính chia tiền.
    LoadForFinalize(ctx context.Context, tx DBTX, billID uuid.UUID) (BillSnapshot, error)
    // Chốt bill: set status=finalized, finalized_at, version++ (optimistic lock).
    MarkFinalized(ctx context.Context, tx DBTX, billID uuid.UUID, version int32) error
}

type BillSnapshot struct {
    BillID           uuid.UUID
    GroupID          uuid.UUID
    CreditorMemberID uuid.UUID
    Version          int32
    Subtotal, ServiceCharge, VAT, Discount, Total int64 // VND, int64
    Items []ItemSnapshot
}
type ItemSnapshot struct {
    ItemID    uuid.UUID
    LineTotal int64
    Assignees []Assignee // member_id + weight
}
type Assignee struct {
    MemberID uuid.UUID
    Weight   decimal.Decimal // numeric(10,4)
}

// ── B cung cấp, A & C tiêu thụ (nhật ký nhóm) ────────────────────────
type ActivityRecorder interface {
    Record(ctx context.Context, tx DBTX, a Activity) error
}

// ── A cung cấp, B & C tiêu thụ ───────────────────────────────────────
type Notifier interface {
    Notify(ctx context.Context, userIDs []uuid.UUID, typ string, payload any) error
}
type ObjectStorage interface {
    Put(ctx context.Context, key string, r io.Reader, contentType string) error
    PresignGet(ctx context.Context, key string, ttl time.Duration) (string, error)
}
type MemberResolver interface { // C cần map member_id → thông tin bank của user
    BankInfo(ctx context.Context, memberID uuid.UUID) (BankInfo, error)
}
```

**Quy tắc vàng:** interface được khai báo ở `internal/port`, **implement nằm trong package của người sở hữu dữ liệu**. Không ai import trực tiếp package của người khác — chỉ import `internal/port`.

---

## 3. Chống đụng độ Git — bảng sở hữu file

### Backend (Go)

| Đường dẫn | Chủ |
|---|---|
| `cmd/api/`, `cmd/worker/` | A (chỉ A sửa; B/C đăng ký module qua 1 dòng `RegisterRoutes`) |
| `internal/platform/**` (config, logger, httpx, middleware, storage, mailer, metrics, txmanager) | A |
| `internal/modules/auth/**`, `internal/modules/user/**`, `internal/modules/admin/**`, `internal/modules/notification/**` | A |
| `internal/modules/group/**`, `internal/modules/bill/**`, `internal/modules/ocr/**`, `internal/modules/activity/**` | B |
| `internal/modules/split/**`, `internal/modules/settlement/**`, `internal/modules/qr/**`, `internal/modules/reminder/**` | C |
| `internal/port/port.go` | **Chung** — sửa phải báo group chat trước |
| `db/queries/auth.sql`, `user.sql`, `admin.sql`, `notification.sql` | A |
| `db/queries/group.sql`, `bill.sql`, `ocr.sql`, `activity.sql` | B |
| `db/queries/debt.sql`, `payment.sql`, `balance.sql` | C |
| `migrations/0000{01..19}_*` | A |
| `migrations/0000{20..39}_*` | B |
| `migrations/0000{40..59}_*` | C |

> **sqlc:** commit luôn code generate. `sqlc` sinh 1 file `.sql.go` cho mỗi file `.sql` → chia file query theo người thì file generate cũng tách theo người, gần như không bao giờ conflict. Chỉ `models.go` là chung — ai thêm bảng mới thì báo trước khi chạy `make sqlc`.

### Frontend (Flutter)

| Đường dẫn | Chủ |
|---|---|
| `lib/main.dart`, `lib/app/router.dart`, `lib/core/**` (dio client, interceptor, theme, widgets dùng chung, error mapper, l10n) | A |
| `lib/features/auth/**`, `lib/features/profile/**`, `lib/features/admin/**` | A |
| `lib/features/group/**`, `lib/features/bill/**` | B |
| `lib/features/debt/**`, `lib/features/payment/**`, `lib/features/balance/**` | C |

> **Router không được là điểm nghẽn:** mỗi feature tự export danh sách route của mình trong file của mình:
> ```dart
> // lib/features/bill/bill_routes.dart  (B sở hữu)
> final List<RouteBase> billRoutes = [ GoRoute(path: '/bills/:id', ...) ];
> ```
> `router.dart` của A chỉ có 3 dòng `...authRoutes, ...billRoutes, ...paymentRoutes`. Sau ngày 2, `router.dart` gần như không đổi nữa.

> **Design system đóng băng sau D3.** A phải xong `lib/core/theme` + widget dùng chung (`AppButton`, `AppTextField`, `MoneyText`, `AppScaffold`, `EmptyState`, `ErrorView`) trong 3 ngày đầu. Sau đó B/C chỉ dùng, không sửa.

---

## 4. Chi tiết task từng người

### 👤 NGƯỜI A — Platform & Identity

#### A-BE (Backend)

| ID | Task | FR | Ghi chú kỹ thuật | Est |
|---|---|---|---|---|
| A1 | Migration `000001_init` từ `dbv1.sql`, `make migrate-up/down`, seed dev | MNT-02 | golang-migrate; giữ nguyên enum, FK tổ hợp, trigger `set_updated_at`, view `v_member_balances` | 0.5d |
| A2 | Platform: config (env), slog structured logger, request-id, recover, CORS, `httpx` response/error envelope | MNT-01 | Chuẩn error §2 | 0.5d |
| A3 | `txmanager`: chạy usecase trong 1 transaction, truyền `DBTX` xuống repo | REL-01 | Bắt buộc: Finalize (C) và Confirm payment (C) đều cần | 0.5d |
| A4 | Sign Up + gửi mail xác thực + verify token + resend | 4.1.2 | `user_tokens` type=`email_verification`, chỉ lưu hash, UUID v7 | 0.5d |
| A5 | Sign In + JWT access (15m) + refresh token (30d) gắn `device_id` + ghi `sessions` | 4.1.1 | 401 generic, 403 `EMAIL_NOT_VERIFIED`, 403 suspended/locked | 0.5d |
| A6 | Middleware `RequireAuth` (JWT), `RequireAdmin`, rate limit theo IP + theo account (429) | 4.1.1, SEC-01 | Export cho B/C dùng qua `platform/middleware` | 0.5d |
| A7 | Sign Out (revoke refresh, idempotent) + Refresh token rotation | 4.1.4 | | 0.25d |
| A8 | Forgot password + reset (revoke toàn bộ session) + Change password (giữ session hiện tại) | 4.1.3, 4.1.5 | Chống account enumeration: luôn trả 200 | 0.5d |
| A9 | Profile: update display_name / phone / avatar / **bank code + số TK + chủ TK** | 4.1.6 | Validate bank_code theo danh sách NAPAS (hardcode JSON); lỗi bank → 400, giữ nguyên bank cũ | 0.5d |
| A10 | `ObjectStorage` adapter (MinIO/S3) + presigned URL — **B và C đều xài** | SI-02 | Phải xong **trước D4** vì B cần upload ảnh bill | 0.5d |
| A11 | `MemberResolver` port: member_id → bank info (C dùng để sinh QR) | 4.1.17 | | 0.25d |
| A12 | Notification module: bảng `notifications`, API list/mark-read, `Notifier` port (prototype: ghi DB + log; push là stub) | 4.1.19, 4.2.1 | | 0.5d |
| A13 | Admin: list account (phân trang, search, filter status), account detail (mask số TK) | 4.1.20, 4.1.21 | Không bao giờ trả `password_hash` | 0.5d |
| A14 | Admin: update status (suspend/lock/reactivate) + revoke toàn bộ session + `admin_audit_logs` (bắt buộc reason) | 4.1.22 | Validate transition hợp lệ, sai → 400 | 0.5d |
| A15 | `/health` (liveness/readiness: DB, storage, OCR provider) + `/metrics` Prometheus (latency histogram, error rate, queue depth) | 4.1.23 | Queue depth lấy từ River — phối hợp B | 0.5d |
| A16 | Docker Compose (api + worker + postgres + minio), Makefile, README chạy dự án | 6.2 | | 0.5d |

#### A-FE (Flutter)

| ID | Task | Est |
|---|---|---|
| A17 | `core/`: dio client + interceptor (attach token, auto-refresh khi 401, map lỗi BE → `AppException`), secure storage token | 0.75d |
| A18 | Theme + design tokens + widget dùng chung: `AppButton`, `AppTextField`, `MoneyText` (format VND), `AppScaffold`, `EmptyState`, `ErrorView`, `LoadingView` — **freeze sau D3** | 0.75d |
| A19 | `router.dart` + auth guard (chưa login → `/sign-in`) + bottom nav (Nhóm / Nợ của tôi / Thông báo / Hồ sơ) | 0.5d |
| A20 | Màn hình: Sign In, Sign Up, Verify email, Forgot/Reset password | 0.75d |
| A21 | Màn hình: Hồ sơ + Đổi mật khẩu + **Cấu hình tài khoản ngân hàng** (bắt buộc trước khi làm chủ nợ) | 0.5d |
| A22 | Màn hình: Danh sách thông báo (đánh dấu đã đọc) | 0.25d |
| A23 | l10n vi (mặc định) + en, responsive 5"–10" | 0.25d |

**Định nghĩa hoàn thành của A:** người khác `git pull` là chạy được `make dev`, đăng ký → verify → đăng nhập → vào app thấy bottom nav, gọi API có token tự động.

---

### 👤 NGƯỜI B — Group & Bill / OCR

#### B-BE

| ID | Task | FR | Ghi chú kỹ thuật | Est |
|---|---|---|---|---|
| B1 | Create group (creator thành `captain`), list group của tôi, group detail | 4.1.7 | Kiểm tra quota nhóm/user → 403/429 | 0.5d |
| B2 | Generate invite (captain only, expiry, max_uses), revoke invite, trả deep link | 4.1.8 | Đã có invite active → trả invite cũ, trừ khi `regenerate=true` | 0.5d |
| B3 | Join group bằng code | 4.1.9 | **Quan trọng:** người từng rời nhóm phải `UPDATE status='active', left_at=NULL` chứ không INSERT (xem note trong `dbv1.sql`). Invite hết hạn/hết lượt → 410. Đã là member → 200 | 0.5d |
| B4 | Remove member / rời nhóm | 4.1.10 | Chỉ cho phép khi `net_balance = 0` (query `v_member_balances`), ngược lại 409 kèm số tiền. Soft-remove: `status='inactive'`. Captain không tự rời khi còn member khác | 0.5d |
| B5 | List member + đổi role (chuyển captain) | 4.1.10 | Tôn trọng unique index `uq_group_members_active_captain` — đổi captain phải trong 1 tx | 0.25d |
| B6 | `ActivityRecorder` impl + API timeline nhóm (phân trang theo `created_at DESC`) | EXP-03 | Export port cho A & C | 0.5d |
| B7 | Upload ảnh bill → tạo `bills` (draft) + enqueue OCR job, trả `bill_id` + kênh SSE | 4.1.11 | Validate mime/size; storage lỗi → 503 và **không** tạo bill | 0.5d |
| B8 | River worker OCR: gọi Vision LLM (Gemini Flash), retry backoff, ghi `ocr_jobs.raw_response` | 4.1.12 | Prompt trả JSON schema cố định; retry cạn → bill vẫn `draft`, item rỗng | 1d |
| B9 | Normalize kết quả OCR: parse số kiểu VN ("1.250.000₫") → `int64` VND, ghi `bill_items` | 4.1.12, REL-01 | **Cấm float64.** Lệch tổng → set `bills.mismatch_warning = true` | 0.5d |
| B10 | SSE endpoint tiến trình OCR (`queued → processing → succeeded/failed`) | 4.1.11 | | 0.25d |
| B11 | Bill CRUD draft: sửa merchant/date/service_charge/vat/discount, thêm/xóa/sửa item | 4.1.14 | **Optimistic locking** bằng `bills.version` → writer thứ 2 nhận 409. Bill `finalized` → 409. Chỉ creditor tạo bill hoặc captain mới sửa được | 0.75d |
| B12 | Gán món cho thành viên: gán từng món (weight), "chia đều toàn bill" | 4.1.13 | Chia đều = gán mọi item cho mọi người chọn với `weight=1`. Bill nhập tay không có item → tạo **1 item tổng hợp**. Gán cho member `inactive` → 409 | 0.75d |
| B13 | API preview chia tiền tạm tính (chưa finalize) — **gọi `split.Calculate` của C** | 4.1.13, 4.1.16 | Ranh giới rõ: B lo dữ liệu, C lo toán | 0.25d |
| B14 | Impl `BillReader` port (`LoadForFinalize`, `MarkFinalized`) cho C | 4.1.15 | Phải xong **trước D6** vì C cần để ráp finalize | 0.5d |
| B15 | Chặn finalize: còn món chưa gán / danh sách participant rỗng → 400 kèm danh sách item lỗi | 4.1.15 | Validate thuộc B, quyết định finalize thuộc C | 0.25d |

#### B-FE

| ID | Task | Est |
|---|---|---|
| B16 | Danh sách nhóm + tạo nhóm + màn hình nhóm (tab: Hóa đơn / Thành viên / Nhật ký) | 0.75d |
| B17 | Mời thành viên: hiện link + QR mời + share sheet; màn hình join bằng code / deep link | 0.5d |
| B18 | Quản lý thành viên (captain): xóa member, cảnh báo khi còn dư nợ | 0.5d |
| B19 | Feed nhật ký nhóm | 0.25d |
| B20 | Chụp/chọn ảnh hóa đơn → upload → màn hình chờ OCR (progress qua SSE) | 0.75d |
| B21 | Màn hình sửa hóa đơn: bảng item inline edit, thêm/xóa món, phí dịch vụ/VAT/giảm giá, banner cảnh báo `mismatch_warning` | 1d |
| B22 | Màn hình gán món: chọn member cho từng món / nút "chia đều", hiện preview số tiền mỗi người realtime | 1d |

**Định nghĩa hoàn thành của B:** chụp 1 hóa đơn thật → OCR ra item → sửa → gán món → mọi item đều có người gánh → nút "Chốt hóa đơn" sáng lên.

---

### 👤 NGƯỜI C — Money: Split, Settlement, QR, Reminder

> C bắt đầu bằng **pure logic, không cần DB, không cần chờ ai**. Đây là phần rủi ro cao nhất (Risk R4) nên phải test dày.

#### C-BE

| ID | Task | FR | Ghi chú kỹ thuật | Est |
|---|---|---|---|---|
| C1 | **Split Controller (pure function)**: `Calculate(BillSnapshot) []MemberShare` | 4.1.13, REL-01 | Chia theo weight; phân bổ service_charge/VAT/discount **theo tỉ lệ subtotal từng người**; làm tròn **Hamilton (largest remainder)**. Bất biến: `Σ share == total` tuyệt đối. **int64 toàn bộ, cấm float64.** Trả kèm `rounding_adjustment` từng người (EXP-01) | 1d |
| C2 | Unit test bảng cho C1: ≥ 25 case — chia hết, chia lẻ 1đ, 3 người/1000đ, discount lớn hơn subtotal, weight thập phân, 50 member × 100 item (PERF-06), property test `Σ = total` | R4 | Mục tiêu coverage 100% package `split` | 0.5d |
| C3 | **VietQR generator**: TLV + CRC-16/CCITT-FALSE, encode bank BIN + số TK + amount + nội dung CK | 4.1.17 | Có test vector đối chiếu app ngân hàng thật. ≤ 100ms (PERF-03) | 0.75d |
| C4 | Sinh `reference_code` duy nhất toàn hệ thống (unique index `payments.reference_code`), retry khi trùng | 4.1.17 | Format gợi ý: `PS` + base32(uuidv7 rút gọn), ≤ 25 ký tự để vừa nội dung CK | 0.25d |
| C5 | **Finalize Bill usecase** — trong **1 transaction** | 4.1.15 | Gọi `BillReader.LoadForFinalize` (B) → `split.Calculate` (C1) → UPSERT `debts` theo `ON CONFLICT (bill_id, debtor, creditor) DO UPDATE` → `MarkFinalized` (B) → `ActivityRecorder.Record` (B) → `Notifier` (A). Lỗi bất kỳ → rollback toàn bộ, bill vẫn `draft`. Chỉ **captain** được finalize | 1d |
| C6 | API "nợ của tôi" + "ai nợ tôi" (theo nhóm & toàn cục), kèm truy vết về bill và từng món | 4.1.16, EXP-03 | Dùng index `idx_debts_debtor_unsettled` / `idx_debts_creditor_unsettled` | 0.5d |
| C7 | API tổng quan số dư nhóm (đọc `v_member_balances`) | 4.1.10 | B dùng lại API này khi remove member | 0.25d |
| C8 | **Generate Payment QR (gộp nợ)**: nhận `debt_ids[]` → validate cùng group + cùng debtor + cùng creditor + đều `awaiting` → tạo `payments` (amount = Σ) → set các debt sang `pending_confirmation` + gắn `payment_id` | 4.1.17 | Khác creditor → 400; đã có payment active → 409; creditor chưa có bank → 409. Cho phép chọn tập con | 0.75d |
| C9 | Submit payment proof: upload ảnh (qua `ObjectStorage` của A) + note, stamp `submitted_at`, notify creditor | 4.1.18 | Nộp lại → **update** payment cũ, không tạo mới. Storage lỗi → vẫn lưu note, báo retry ảnh | 0.5d |
| C10 | Confirm payment (1 tx): stamp `confirmed_at`, mọi debt phủ bởi payment → `settled` + `settled_at`, ghi activity, notify | 4.1.19 | All-or-nothing, không hỗ trợ trả một phần | 0.5d |
| C11 | Reject payment: bắt buộc `rejection_reason` (thiếu → 400), stamp `rejected_at`, debts quay về `awaiting` + `payment_id = NULL`, giữ payment làm audit, **không tái sử dụng reference_code** | 4.1.19 | | 0.5d |
| C12 | Hộp thư "Chờ tôi xác nhận" của chủ nợ | 4.1.19 | Index `idx_payments_creditor_pending` | 0.25d |
| C13 | **River cron job nhắc nợ**: debt `awaiting` quá hạn → notify + `reminder_count++`; `pending_confirmation` quá N lần → `stalled_confirmation` + ghi activity + notify 2 bên | 4.2.1 | **Không bao giờ tự động settle.** Gửi noti lỗi → không tăng `reminder_count` để lần sau retry | 0.75d |

#### C-FE

| ID | Task | Est |
|---|---|---|
| C14 | Màn hình tổng kết hóa đơn: mỗi người bao nhiêu, **breakdown từng món + phần VAT/phí/giảm giá + số tiền làm tròn** (EXP-01), nút Chốt (chỉ captain) | 0.75d |
| C15 | Màn hình "Nợ của tôi": gom theo chủ nợ, checkbox chọn nhiều khoản nợ để gộp 1 QR, hiện tổng đang chọn | 0.75d |
| C16 | Màn hình QR thanh toán: QR ≥ 250×250px (UI-04), mã tham chiếu dạng text copy được, danh sách bill mà QR này trả, fallback hiện tên NH/số TK/chủ TK khi QR lỗi | 0.75d |
| C17 | Màn hình gửi bằng chứng: chọn ảnh + note + nút "Tôi đã chuyển" | 0.5d |
| C18 | Màn hình chủ nợ xác nhận: xem ảnh bằng chứng, nút Xác nhận / Từ chối (bắt buộc nhập lý do) | 0.5d |
| C19 | Màn hình số dư nhóm + trạng thái nợ (badge màu theo 5 trạng thái) | 0.5d |

**Định nghĩa hoàn thành của C:** chốt 1 bill 3 người → mỗi người thấy đúng số tiền, tổng khớp tuyệt đối → payer chọn 2 bill của cùng chủ nợ → 1 QR duy nhất → nộp ảnh → chủ nợ xác nhận → cả 2 nợ về `settled`.

---

## 5. Timeline & thứ tự song song

```
        D1        D2      D3      D4      D5     │  D6      D7      D8      D9      D10
────────┼─────────┼───────┼───────┼───────┼──────┼─────────┼───────┼───────┼───────┼────────
CHUNG   │ Kickoff: contract + port + migration + docker (buổi sáng D1)
────────┼──────────────────────────────────────────────────────────────────────────────────
   A    │ A1-A3   │ A4-A5 │ A6-A8 │ A9-A11│A12   │ A13-A14 │ A15   │ A17-A19 (FE) ─────────►
        │         │       │ A17-A18 (FE, song song buổi tối)     │ A20-A23 (FE)
────────┼─────────┼───────┼───────┼───────┼──────┼─────────┼───────┼───────┼───────┼────────
   B    │ B1-B2   │ B3-B5 │ B6-B7 │ B8    │B9-B10│ B11-B12 │ B14   │ B16-B19 (FE) ─────────►
        │         │       │       │ ▲cần A10      │ ▲C cần B14  │ B20-B22 (FE)
────────┼─────────┼───────┼───────┼───────┼──────┼─────────┼───────┼───────┼───────┼────────
   C    │ C1-C2   │ C1-C2 │ C3-C4 │ C6-C7 │C8    │ C5 ◄B14 │ C9-C11│ C12-C13│ C14-C19 (FE) ►
        │ (pure, không cần ai)   │       │      │ ▲ điểm ráp lớn nhất
────────┴─────────┴───────┴───────┴───────┴──────┴─────────┴───────┴───────┴───────┴────────
                            ▲ GATE: TDD review (cuối W1)      ▲ GATE: Test report (giữa W2)
                                                                      D9-D10: E2E + Docker + demo
```

**Chỉ có 3 điểm phụ thuộc cứng trong toàn dự án:**

| Ai chờ ai | Cái gì | Hạn chót | Nếu trễ thì làm gì |
|---|---|---|---|
| B chờ A | `ObjectStorage` (A10) | hết D4 | B code upload với `LocalDiskStorage` tự viết tạm |
| C chờ B | `BillReader` (B14) | hết D6 | C test C5 với `FakeBillReader` trả snapshot cứng |
| C chờ A | `MemberResolver` bank info (A11) | hết D4 | C hardcode bank info trong test QR |

Mọi phụ thuộc khác đều là **soft** (chỉ ảnh hưởng lúc ráp E2E ở D9–D10).

---

## 6. QUY CHUẨN CODING

### 6.1 Cấu trúc thư mục Backend (modular monolith — MNT-01)

```
cmd/
  api/main.go              # HTTP server
  worker/main.go           # River worker + cron
internal/
  port/port.go             # interface dùng chung giữa các module
  platform/
    config/  logger/  httpx/  middleware/  storage/  mailer/  metrics/  txmanager/
  modules/
    <module>/
      handler/     # HTTP: decode request, gọi usecase, encode response. KHÔNG có business logic.
      usecase/     # Business logic + authorization. KHÔNG biết HTTP, KHÔNG biết SQL.
      repo/        # Truy cập DB qua sqlc. KHÔNG có business logic.
      domain/      # struct + rule thuần, không import gì bên ngoài.
db/
  queries/*.sql            # nguồn cho sqlc
  sqlc/                    # code generate (COMMIT vào repo)
migrations/
```

**Luật tầng (bất khả xâm phạm):** `handler → usecase → repo`. Không được nhảy cóc, không được ngược chiều. `usecase` nhận interface, không nhận struct cụ thể của tầng repo.

### 6.2 Go

```go
// ✅ ĐÚNG
func (u *BillUsecase) Finalize(ctx context.Context, actorID, billID uuid.UUID) (*Bill, error) {
    if err := u.authz.RequireCaptain(ctx, actorID, billID); err != nil {
        return nil, fmt.Errorf("finalize bill %s: %w", billID, err)
    }
    ...
}
```

- `context.Context` **luôn là tham số đầu tiên**, không bao giờ lưu trong struct.
- Error: bọc bằng `fmt.Errorf("...: %w", err)`. So sánh bằng `errors.Is` / `errors.As`, **cấm** `err.Error() == "..."`.
- Sentinel error khai báo ở tầng domain: `var ErrBillFinalized = errors.New("bill already finalized")`. Tầng handler map sang HTTP code — usecase **không** biết đến số 409.
- **Cấm `panic`** trong code nghiệp vụ. Chỉ `panic` lúc khởi động khi config sai.
- **Tiền = `int64` VND. Cấm tuyệt đối `float64`, `float32` cho tiền.** Weight dùng `decimal` hoặc `numeric` từ pgx, không dùng float.
- ID sinh ở tầng ứng dụng bằng **UUID v7** (`github.com/google/uuid` v1.6+ `uuid.NewV7()`).
- Thời gian: `time.Time` UTC, cột DB `TIMESTAMPTZ`. Không format ngày thủ công.
- Interface khai báo ở **nơi tiêu thụ** (consumer side), nhỏ (1–3 method). Không tạo interface "cho có" khi chỉ 1 impl và không cần mock.
- Logging: `log/slog`, structured, kèm `request_id`, `user_id`, `group_id`. **Cấm log** password, token, số tài khoản đầy đủ, `raw_response` chứa PII.
- Tên: package tên ngắn 1 từ thường (`bill`, không `billmodule`, không `utils`). Không stutter: `bill.Service` chứ không `bill.BillService`.
- Format & lint: `gofumpt` + `golangci-lint run` (bật `errcheck, govet, staticcheck, revive, gosec, bodyclose, sqlclosecheck`). **CI đỏ = không merge.**

### 6.3 API

- Prefix `/api/v1`. Danh từ số nhiều, kebab-case: `/api/v1/groups/{groupId}/bills`.
- Hành động không CRUD dùng sub-resource động từ: `POST /bills/{id}/finalize`, `POST /payments/{id}/confirm`.
- JSON field: `snake_case`. Tiền trả về là **số nguyên** (`"amount": 125000`), không phải chuỗi, không có phần thập phân.
- Response thành công:
  ```json
  { "data": { ... }, "meta": { "page": 1, "page_size": 20, "total": 137 } }
  ```
- Response lỗi (thống nhất toàn hệ thống):
  ```json
  { "error": { "code": "EMAIL_NOT_VERIFIED", "message": "Email chưa được xác thực",
               "details": [{"field": "email", "issue": "not_verified"}],
               "request_id": "01J..." } }
  ```
- Mã HTTP theo đúng PRD: 400 validate · 401 chưa auth · 403 không đủ quyền · 404 không tồn tại · 409 xung đột trạng thái/optimistic lock · 410 invite hết hạn · 429 rate limit · 503 dịch vụ ngoài chết.
- Phân trang: `?page=&page_size=` (mặc định 20, max 100 — vượt thì **clamp**, không báo lỗi, theo FR 4.1.20).
- Optimistic locking: client gửi kèm `version` trong body khi sửa bill; sai version → 409 `STALE_VERSION`.

### 6.4 Database & SQL

- Mọi thay đổi schema đi qua migration đánh số tuần tự, có `.up.sql` **và** `.down.sql`. **Migration đã merge vào `main` là bất biến** — sửa thì viết migration mới.
- Số migration theo dải đã chia ở §3 để không trùng số.
- Mọi query trong phạm vi nhóm **bắt buộc có `group_id` trong `WHERE`**, kể cả khi đã lọc theo id. Đây là lớp phòng thủ thứ 2 chống rò dữ liệu chéo nhóm.
- Không dùng `SELECT *`. Viết query trong `db/queries/*.sql`, sinh code bằng `sqlc`, **không viết SQL chuỗi trong Go**.
- Mọi usecase ghi ≥ 2 bảng **phải** chạy trong transaction qua `txmanager` (Finalize, Confirm, Reject, Join/Remove member, Change captain).
- Tôn trọng các invariant DB đã có: FK tổ hợp `(id, group_id)`, `uq_group_members_active_captain`, `uq_debts_bill_pair`, các CHECK trạng thái. **Không** vô hiệu hóa constraint để code chạy được.
- Tính năng chuyên biệt Postgres đã có sẵn thì dùng lại, không tính lại ở Go: view `v_member_balances`, trigger `set_updated_at`.

### 6.5 Flutter / Dart

```
lib/
  main.dart
  app/           router.dart, app.dart
  core/          api/ (dio, interceptor, exception), theme/, widgets/, utils/, l10n/
  features/<feature>/
    data/        <x>_api.dart, <x>_repository.dart, dto (freezed + json_serializable)
    domain/      model, enum
    presentation/  <x>_screen.dart, widgets/, <x>_controller.dart (Riverpod Notifier)
    <feature>_routes.dart
```

- State: `flutter_riverpod` — dùng `AsyncNotifier` / `Notifier` (code-gen `@riverpod`). **Cấm** logic gọi API trong `build()` của Widget.
- Widget: tách nhỏ, ưu tiên `const`. File > 300 dòng → tách. Không lồng quá 5 tầng widget, tách thành widget con có tên.
- Model: `freezed` + `json_serializable`. Tiền parse thành `int` (không `double`), format hiển thị **chỉ** qua `MoneyText` / `NumberFormat` của A.
- Lỗi: repository bắt `DioException` → ném `AppException(code, message)`; UI hiện `ErrorView` theo `code`, **không** hiện raw exception cho user.
- Text hiển thị: qua l10n, **không hardcode chuỗi tiếng Việt trong widget**. Mặc định `vi` (UI-01).
- Đặt tên file `snake_case.dart`, class `PascalCase`, biến/hàm `lowerCamelCase`, private `_prefix`.
- `flutter analyze` sạch (bật `flutter_lints` + `prefer_const_constructors`, `avoid_print`). Dùng `debugPrint`/logger, không `print`.
- Mọi màn hình phải xử lý đủ 4 trạng thái: **loading / empty / error / data**. Không có màn hình trắng.

### 6.6 Git & quy trình

- Branch: `feat/<module>/<mô-tả-ngắn>`, ví dụ `feat/settlement/generate-qr`. Fix: `fix/...`. Không push thẳng `main`.
- Commit theo Conventional Commits, tiếng Anh, thì hiện tại:
  `feat(settlement): aggregate awaiting debts into one payment` · `fix(bill): reject edit on finalized bill with 409` · `test(split): add hamilton rounding cases`
- PR **≤ 400 dòng thay đổi**. To hơn thì tách. PR phải có: mô tả, FR liên quan (VD `FR 4.1.15`), cách test tay.
- Review chéo vòng tròn: **A review B, B review C, C review A.** Reviewer trả lời trong ≤ 4 giờ làm việc. 1 approve là merge được.
- Merge bằng **squash**, đồng bộ nhánh bằng **rebase** (`git pull --rebase`), không merge commit rác.
- Cấm commit: `.env`, API key, file build, `node_modules`, ảnh test dung lượng lớn.
- Daily standup 10 phút: hôm qua / hôm nay / đang kẹt gì.

### 6.7 Testing

| Loại | Bắt buộc cho | Công cụ |
|---|---|---|
| Unit (table-driven) | **`split` package: 100%** (Risk R4), `qr` (CRC test vector), mọi hàm validate | `go test` + `testify` |
| Usecase test (mock port) | Finalize, Generate QR, Confirm/Reject, Join/Remove member | mock thủ công, không cần framework |
| Integration (DB thật) | Repo layer + các luồng transaction | `testcontainers` hoặc Postgres trong compose |
| E2E thủ công | 1 kịch bản đầy đủ, có script trong `docs/demo-script.md` | tay, D9–D10 |

- Tên test: `TestFinalize_UnassignedItem_Returns400`.
- Test không được phụ thuộc thứ tự chạy, không dùng `time.Sleep` để đồng bộ.
- **Bất biến bắt buộc có test:** `Σ debts.amount == bills.total` với mọi bộ input.

### 6.8 Definition of Done (áp cho mọi task)

Một task chỉ được coi là xong khi đủ **tất cả**:

- [ ] Code chạy, `golangci-lint` / `flutter analyze` sạch
- [ ] Có unit test cho nhánh logic chính **và** ít nhất 1 abnormal case mà PRD nêu
- [ ] Xử lý **đủ** các abnormal case của FR tương ứng (đúng HTTP code PRD ghi)
- [ ] API đã cập nhật vào file OpenAPI của mình
- [ ] Ghi `group_activities` nếu hành động làm thay đổi trạng thái nhóm (EXP-03)
- [ ] Không có `TODO` trần trong code — nếu còn thì gắn `// TODO(tên): mô tả`
- [ ] PR được 1 người review và approve

---

## 7. Rủi ro về mặt phối hợp & cách chặn

| Rủi ro | Dấu hiệu sớm | Cách chặn |
|---|---|---|
| Conflict `router.dart` / `main.go` liên tục | 2 PR đụng cùng file trong 1 ngày | Pattern "mỗi feature tự export routes" (§3) — file trung tâm chỉ 3 dòng |
| C ngồi chờ B xong bill | Hết D5 mà B14 chưa có | C dùng `FakeBillReader`, ráp thật ở D6 |
| Đổi API contract giữa chừng làm FE vỡ | FE báo lỗi parse | Đổi contract **phải** báo trong group chat + cập nhật OpenAPI **trước** khi merge BE |
| Ai đó sửa file của người khác cho nhanh | Conflict lạ khi rebase | Bảng sở hữu §3; nhờ chủ file sửa, mất 5 phút, đỡ mất 1 tiếng gỡ conflict |
| Lệch cách hiểu về "gộp nợ" (2 tầng) | Debt sinh sai số dòng | Đọc kỹ block comment mục 7 trong `Database/dbv1.sql`; C viết test cho cả 2 tầng gộp trước khi code |
