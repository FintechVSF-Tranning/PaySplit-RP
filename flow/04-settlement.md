# 04 — Settlement: điều phối trả nợ, không cầm tiền

> **Phạm vi**: BE module `settlement` (`/api/v1/groups/{groupId}/...`) ↔ FE Settlement 4 tab + DynamicVietQrSheet + Proof Review.
>
> Code tham chiếu chính: `PaySplit-BE/internal/modules/settlement/**`, `PaySplit-FE/lib/features/settlement/**`.
>
> Đọc cùng: [`03-bill.md`](03-bill.md) mục 6.4 (void vs QR intent), [`08-realtime.md`](08-realtime.md) (`settlement.*`, `home.balance_changed`), [`05-notification.md`](05-notification.md).

---

## 1. Vấn đề, và ý tưởng để giải quyết

### 1.1 App không phải cổng thanh toán

Người nợ chuyển tiền **ngoài app** (VietQR / ngân hàng). App chỉ: chỉ đúng STK, nhận ảnh biên lai, để người cho vay bấm đã nhận hoặc chưa.

> PaySplit **không** giữ tiền, không hoàn tiền, không đối soát NAPAS. Sai trạng thái trong DB thì tiền ngoài đời vẫn đã chuyển — nên mọi bước ghi phải idempotent và không được tạo payment "nửa vời".

### 1.2 QR là ý định, không phải giữ chỗ nợ

Đây là chỗ dễ hiểu nhầm nhất:

> Tạo QR **không** đụng bảng `debts`. Nợ vẫn `awaiting`, `payment_id` vẫn NULL. Captain vẫn void hóa đơn được; payment `pending_proof` bị `superseded`. Chỉ khi **nộp biên lai** nợ mới nhảy `pending_confirmation` và gắn `payment_id`. Lúc đó void thua với `409 PAYMENT_ALREADY_STARTED`.

DB CHECK `debts_check1`: `awaiting`/`voided` ⇔ `payment_id IS NULL`. QR không thể "ghim" nợ dù muốn.

### 1.3 Snapshot ngân hàng chốt lúc nộp proof, không lúc tạo QR

CHECK `chk_payments_state_matrix` **cấm** cột `recipient_bank_*` khi status `pending_proof`. GetPayment / replay QR **dựng lại** ảnh từ hồ sơ creditor **hiện tại**. Creditor đổi STK giữa lúc hiện QR và lúc nộp ảnh → snapshot theo STK mới.

---

## 2. Bảng tổng quan

| Khái niệm | Giá trị |
|---|---|
| Payment | `pending_proof` → `pending_confirmation` → `confirmed` \| `rejected`. Nhánh `superseded` từ `pending_proof` |
| Unique | Đúng 1 `pending_proof` / cặp debtor→creditor trong nhóm |
| Debts dùng | `awaiting` → `pending_confirmation` → `settled` (+ `voided` từ bill) |
| Khóa | group → debts UUID ASC → payment. Cùng thứ tự với void bill |
| Trần QR | 1–100 debt ids; omit/null = **mọi** awaiting của cặp. Mảng rỗng = `VALIDATION_FAILED` |
| Idempotency | Bảng `payment_idempotency_keys`, TTL 24h. Mọi ghi **bắt buộc** header |
| Key FE | UUIDv5 deterministic cho qr/proof/confirm/reject. Nhắc nợ **UUIDv4 mỗi lần** (chủ đích lặp) |
| Mã 409 key | **`IDEMPOTENCY_KEY_REUSED`** (không có `IDEMPOTENCY_CONFLICT` trên HTTP) |
| Nhắc nợ | Max 3, cách ≥24h, chung counter với job. FE cooldown **24 giờ**, không phải 60 giây |
| Job | `settlement_scan` mỗi giờ + RunOnStart (72h stale, 48h stalled). `settlement_cleanup` mỗi 24h |

---

## 3. State machine

```mermaid
flowchart LR
    A["pending_proof<br/>QR, debts vẫn awaiting"] -->|"nộp ảnh"| B["pending_confirmation<br/>debts gắn payment_id"]
    B -->|"creditor xác nhận"| C["confirmed<br/>debts settled"]
    B -->|"từ chối + lý do"| D["rejected<br/>debts về awaiting, payment_id NULL"]
    A -->|"QR mới khác tập nợ, hoặc void bill"| E["superseded"]
```

`chk_payments_state_matrix` khóa bộ cột theo status — không tồn tại trạng thái nửa vời. `confirmed`/`rejected`/`superseded` là cuối.

Ai được xem payment: debtor, creditor, hoặc **Captain**. Confirm/reject: **chỉ creditor** (Captain không thế). Remind: creditor **hoặc** Captain.

---

## 4. Endpoint và màn hình

Mount `/api/v1/groups`, `liveAuth`. Ghi bắt buộc `Idempotency-Key`.

| Method + Path | Việc | Thành công |
|---|---|---|
| GET `/{id}/expenses/me` | Tổng quan + matrix | FE **không gọi** |
| GET `/{id}/debts` | Filter debtor/creditor/status whitelist; cursor; limit 1–100 | |
| POST `/{id}/payments/qr` | Tạo / replay VietQR | **200** replay / **201** mới. Body `{payment}` — `qr_image_url` **nằm trong** payment |
| GET `/{id}/payments/{pid}` | Chi tiết; pending_proof rebuild QR live | |
| POST `/{id}/payments/{pid}/proof` | Multipart `image` + `note` ≤500 rune | 200 `{payment}` |
| POST `/{id}/payments/{pid}/confirm` | | 200 `{payment, settled_debts}` |
| POST `/{id}/payments/{pid}/reject` | `{reason}` 1–500 | 200 `{payment, reset_debts}` |
| POST `/{id}/debts/{did}/remind` | | 200 `{debt_id, reminder_count, reminded_at}` |

FE: `/bills` và `/settlement` **cùng** `SettlementPage`, extra chọn tab. `/bills` mặc định tab Hóa đơn, `/settlement` mặc định Cần trả.

| Tab | Nội dung |
|---|---|
| Cần trả | Nợ mình awaiting + pending_confirmation. Trả chỉ awaiting. Batch gom `groupId+creditorId` |
| Cần thu | Proof chờ duyệt + khoản cho vay + nhắc (cooldown 24h, hiện Xh/Xp/Xs) |
| Hóa đơn | Bill đa nhóm + search |
| Lịch sử | Payment `confirmed` |

---

## 5. Sequence Diagrams

### 5.1 Tạo QR

```mermaid
sequenceDiagram
    autonumber
    actor U as Debtor
    participant FE as Settlement / batch sheet
    participant BE as Settlement API
    participant DB as PostgreSQL

    U->>FE: Chọn khoản awaiting → Trả
    Note over FE: Key = UUIDv5(qr:{groupId}:{creditorId}:{sortedDebtIds})
    FE->>BE: POST .../payments/qr {debt_ids?} + Idempotency-Key
    BE->>BE: Parse 1–100 UUID, dedupe, sort. Omit = mọi awaiting của cặp
    alt Key completed
        BE-->>FE: Replay 200
    else Key khác hash
        BE-->>FE: 409 IDEMPOTENCY_KEY_REUSED
    else in_progress
        BE-->>FE: 409 IDEMPOTENCY_IN_PROGRESS + Retry-After 1
    end
    BE->>DB: Lock group. Caller = debtor (không member → GROUP_NOT_FOUND)
    BE->>DB: Creditor active; đủ 3 trường bank + directory
    alt Thiếu STK
        BE-->>FE: 422 BANK_ACCOUNT_REQUIRED
        FE-->>U: SnackBar — không phải Dialog
    else Creditor không phải member
        BE-->>FE: 404 CREDITOR_NOT_FOUND
    end
    BE->>DB: LOCK debts ORDER BY id. Toàn awaiting đúng cặp
    alt Thiếu 1 id bất kỳ
        BE-->>FE: 409 DEBTS_NOT_AWAITING — hủy cả batch, không payment nửa vời
    else Đã có pending_proof cùng cặp, cùng tập UUID
        BE-->>FE: 200 QR dựng lại từ bank LIVE
    else Cùng cặp, khác tập
        BE->>DB: Cũ → superseded + INSERT mới
    else Sạch
        BE->>BE: reference_code PAY + 8 Base32 (không I,O,0,1)
        Note over DB: INSERT pending_proof KHÔNG có cột bank. Activity + notify creditor + settlement.payment_changed
        BE-->>FE: 201 {payment}
    end
    FE->>U: Sheet QR, copy STK / số tiền / nội dung CK
```

Idempotency **trước** check bank: replay bản completed vẫn 200 dù creditor đã xóa STK sau đó.

### 5.2 Nộp biên lai — hai pha

```mermaid
sequenceDiagram
    autonumber
    actor U as Debtor
    participant FE as VietQrSheet
    participant BE as Settlement API
    participant CDN as Cloudinary
    participant DB as PostgreSQL

    U->>FE: Ảnh gallery JPEG/PNG/HEIC 1 byte–10MB, note ≤500
    Note over FE: Key UUIDv5(proof:{groupId}:{paymentId})

    rect rgb(240,240,245)
        Note over BE: PrepareProof — commit in_progress
        BE->>DB: Caller = debtor, payment pending_proof, bank creditor còn hợp lệ
        alt Sai trạng thái
            BE-->>FE: 409 PAYMENT_NOT_PENDING_PROOF
        end
    end
    BE->>BE: Sniff magic bytes, ghi đè Content-Type
    BE->>CDN: payments/{pid}/proofs/{operationId} WebP q100
    alt Upload fail
        BE->>DB: ResetProofAttempt(replaceOperation=false)
        BE-->>FE: 503 STORAGE_UNAVAILABLE
    end

    rect rgb(240,240,245)
        Note over BE: SubmitProof
        BE->>DB: Lock debts. Phải còn awaiting. Snapshot bank VÀO payment. pending_confirmation
        alt RowsAffected ≠ số debt
            BE-->>FE: 409 DEBTS_NOT_AWAITING
            Note over BE: Sau lỗi pha 2: Delete CDN (fail → media_cleanup) + ResetProofAttempt(true) — operation_id MỚI
        else OK
            BE->>DB: Activity + notify creditor payment_submitted + debts_changed + bill.settlement_changed
            BE-->>FE: 200
            FE->>U: Pop + snackbar chờ xác nhận
        end
    end
```

### 5.3 Confirm / Reject

```mermaid
sequenceDiagram
    autonumber
    actor C as Creditor
    participant FE as Tab Cần thu
    participant BE as Settlement API
    participant DB as PostgreSQL

    alt Xác nhận
        FE->>BE: POST confirm (key UUIDv5)
        BE->>DB: Lock debts. Mọi debt pending_confirmation VÀ payment_id = pid. Caller PHẢI là creditor
        BE->>DB: confirmed + debts settled
        Note over BE: Thêm home.balance_changed chỉ debtor+creditor
        BE-->>FE: 200
    else Từ chối
        FE->>FE: Dialog bắt buộc lý do
        FE->>BE: POST reject {reason} (reason nằm trong key)
        alt Reason rỗng / quá dài
            BE-->>FE: 400 VALIDATION_FAILED
        end
        BE->>DB: rejected + debts awaiting, payment_id NULL
        BE-->>FE: 200 — debtor tạo QR lại
    end
    Note over BE: Hai thiết bị đua: kẻ thua 409 PAYMENT_NOT_PENDING_CONFIRMATION
```

FE `mutate` mutex chặn bấm đôi trên một máy.

### 5.4 Nhắc nợ — tay và máy dùng chung 3 lần

```mermaid
sequenceDiagram
    autonumber
    actor S as Creditor hoặc Captain
    participant FE as Tab Cần thu
    participant BE as Settlement API
    participant Q as settlement_scan mỗi giờ

    S->>FE: Nhắc
    FE->>FE: Cooldown UI 24 giờ từ lastRemindedAt
    FE->>BE: POST remind (key UUIDv4 ngẫu nhiên)
    alt count ≥ 3 hoặc last < 24h
        BE-->>FE: 429 REMINDER_RATE_LIMITED
        FE->>FE: Vẫn bật cooldown 24h
    else OK
        BE->>DB: count++ actor_kind=member + notify debtor + settlement.debt_reminded
        BE-->>FE: 200
    end

    par Job tự động
        Q->>Q: awaiting, created_at ≥ 72h, count<3, last ≥24h, SKIP LOCKED LIMIT 100
        Q->>BE: actor_kind=system
    and Payment treo
        Q->>Q: pending_confirmation >48h, stalled_alerted_at NULL → alert một lần, không đổi status
    end
```

---

## 6. Activity Diagrams

### 6.1 Góc debtor

```mermaid
flowchart TD
    A["Tab Cần trả"] --> B["Chọn awaiting, lẻ hoặc batch theo creditor"]
    B --> C["POST payments/qr"]
    C --> D{"Kết quả"}
    D -->|"422 BANK_ACCOUNT_REQUIRED"| E["SnackBar chủ nợ chưa STK"] --> A
    D -->|"409 IDEMPOTENCY_KEY_REUSED / IN_PROGRESS"| F["SnackBar"]
    D -->|"200 / 201"| G["Sheet QR"]
    G --> H{"Nộp ảnh?"}
    H -->|"Đóng sheet"| I["Payment vẫn pending_proof. Void bill vẫn được"]
    H -->|"Có"| J["POST proof 2 pha"]
    J --> K{"OK?"}
    K -->|"DEBTS_NOT_AWAITING"| A
    K -->|"OK"| L["Chờ creditor"]
    L --> M{"Confirm → lịch sử / Reject → awaiting, QR mới"}
```

### 6.2 Góc creditor

```mermaid
flowchart TD
    A["Hero N biên lai → tab Cần thu"] --> B["Card ảnh + tiền + note"]
    B --> C{"Quyết định"}
    C -->|"Xác nhận"| D["POST confirm"]
    C -->|"Từ chối"| E["Dialog lý do bắt buộc"] --> F["POST reject"]
    D --> G["Reload, mutex"]
    F --> G
    G --> H{"Còn proof?"}
    H -->|"Có"| B
    H -->|"Không"| I["Danh sách + nút nhắc 24h"]
```

### 6.3 Gom dữ liệu đa nhóm

```mermaid
flowchart TD
    A["loadData"] --> B["GET /groups 100/trang, max 50 trang, cursor phải tiến"]
    B --> C["Mỗi nhóm: debts + bills song song. Throttle 6 nhóm một lúc"]
    C --> D["Debts/bills cũng paginate 100 × 50"]
    D --> E["Load payment cho debt có paymentId pending_confirmation/settled, throttle 6"]
    E --> F{"Record JSON hỏng / status lạ?"}
    F -->|"Skip từng record"| G
    F -->|"OK"| G["Phân loại payable / receivable / proofs / history"]
    G --> H["Lỗi request một nhóm → fail CẢ load + banner Thử lại. Không skip theo nhóm"]
```

---

## 7. Realtime

| Type | Khi | FE đánh thức |
|---|---|---|
| `settlement.payment_changed` | tạo QR, proof, confirm, reject, stalled | `settlement.overview` |
| `settlement.debt_reminded` | nhắc tay + job | `settlement.overview` + `group.debts` |
| `group.debts_changed` | proof, confirm, reject — **không** tạo QR, **không** nhắc | `group.debts` + `group.detail` |
| `bill.settlement_changed` | proof/confirm/reject theo từng bill | `bill.detail`, `group.bills` |
| `group.activity_changed` | hầu hết mutation trên | `group.activities`, `home.activities` |
| `home.balance_changed` | **chỉ confirm**, audience debtor+creditor | `settlement.overview` + hai list nhóm |

Tạo QR không `group.debts_changed` vì nợ vẫn awaiting.

---

## 8. Edge Cases

| # | Tình huống | Xử lý | Mã |
|---|---|---|---|
| 1 | Batch QR thiếu 1 debt | Hủy cả batch | `409 DEBTS_NOT_AWAITING` |
| 2 | QR 2 cùng cặp | Cùng tập → 200 live QR; khác tập → superseded | 200 / 201 |
| 3 | Creditor thiếu STK | | `422 BANK_ACCOUNT_REQUIRED` — không ghép 404 |
| 4 | Không phải member | | `404 GROUP_NOT_FOUND` |
| 5 | Debt ids không khớp cặp | Lock filter thiếu hàng | `409 DEBTS_NOT_AWAITING` — không 403 |
| 6 | Proof khi không còn pending_proof | Trước upload | `409 PAYMENT_NOT_PENDING_PROOF` — không 400 |
| 7 | Void thắng giữa proof | RowsAffected | `409 DEBTS_NOT_AWAITING` + reset operation mới |
| 8 | Ảnh giả / >10MB | Magic bytes | `400 INVALID_IMAGE` |
| 9 | CDN OK, DB fail | Delete + cleanup + operation_id mới | retry được |
| 10 | Confirm/reject đua | Lock + state check | `409 PAYMENT_NOT_PENDING_CONFIRMATION` |
| 11 | Reject không lý do | | `400 VALIDATION_FAILED` |
| 12 | Spam nhắc | 3 lần, 24h, tay+máy chung | `429 REMINDER_RATE_LIMITED` |
| 13 | Nhắc không awaiting / không creditor-captain | | `409 DEBT_NOT_AWAITING` / `403 FORBIDDEN` |
| 14 | Key khác payload | Canonical hash (proof gồm image sha256) | `409 IDEMPOTENCY_KEY_REUSED` |
| 15 | Crash giữa Prepare và Submit | in_progress + retry_after; FE key deterministic resume | `IN_PROGRESS` rồi resume |
| 16 | Proof treo >48h | Alert một lần, không đổi status | |
| 17 | Status lạ (skew version) | FE map debt→voided, payment→superseded; skip record hỏng | |
| 18 | Nhiều nhóm | Throttle 6, max 50 trang; **lỗi nhóm fail cả màn** | |
| 19 | Đóng sheet không nộp | Nợ không bị giữ; void được | |
| 20 | Creditor đổi STK sau QR | Get/replay/proof dùng bank **live**; snapshot lúc SubmitProof | |
| 21 | Confirm không phải creditor (Captain) | | `403 FORBIDDEN` |
| 22 | GetPayment outsider | | `403 FORBIDDEN` |
| 23 | CDN down lúc upload | | `503 STORAGE_UNAVAILABLE` |
| 24 | `expenses/me` | BE có, FE không dùng; màn gom từ list groups | |

---

## 9. Cấu hình

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `PAYMENT_REMINDER_STALE_HOURS` | `72` | Job nhắc |
| `STALLED_CONFIRMATION_HOURS` | `48` | Alert proof treo |
| `PAYMENT_REMINDER_MAX_COUNT` | `3` | Trần, khớp DB CHECK |
| VietQR img | `https://img.vietqr.io/image` template `compact` | Dựng URL, không gọi API ngân hàng |
| Proof signed URL | 5 phút | Cloudinary private |

---

## 10. Ghi chú triển khai đáng chú ý

1. **HTTP không có `IDEMPOTENCY_CONFLICT`.** Domain `ErrIdempotencyConflict` map `IDEMPOTENCY_KEY_REUSED`. Client bắt tên domain sẽ miss.

2. **`PAYMENT_NOT_PENDING_PROOF` là 409.** Chuẩn bị proof trước upload — đừng tốn CDN rồi mới biết QR đã superseded.

3. **Pha 2 fail → `replaceOperation=true`.** Operation cũ đã gắn object CDN. Giữ id cũ = upload đè hoặc 409 kẹt. Upload fail mới `false`.

4. **Canonical QR sort UUID.** Cùng tập khác thứ tự = cùng hash = replay. FE UUIDv5 phải sort giống BE.

5. **Reject: lý do nằm trong key.** Đổi lý do ≠ replay. Đúng: người ta không confirm nhầm reason.

6. **Remind FE UUIDv4.** Deterministic sẽ biến lần 2 thành replay im lặng, không tăng count.

7. **`home.balance_changed` chỉ lúc confirm.** Tạo QR / proof chưa đổi net balance.

8. **Lock order giống void bill.** Đổi một bên = deadlock.

9. **`reference_code` alphabet loại I/O/0/1.** Người đọc nhầm chữ số khi chuyển khoản.

10. **Gom FE: lỗi một nhóm hạ cả màn.** Chỉ skip JSON hỏng từng record. Banner Thử lại là page-level.

11. **Log không chứa STK, payload QR, ảnh proof, danh sách debt id.** 

---

## 11. Trạng thái hiện tại

| Hạng mục | Trạng thái | Ghi chú |
|---|---|---|
| QR / proof / confirm / reject / nhắc | ✅ | Idempotency, lock debts |
| Job 72h / 48h | ✅ | SKIP LOCKED đa instance |
| Realtime overview | ⚠️ AC-22 một phần | Khóa nộp đã kiểm runtime; ma trận payment chưa đủ |
| `GET expenses/me` | ✅ BE | FE chưa dùng |
| Cooldown nhắc UI | ✅ 24h | Khớp BE, không còn 60s |
