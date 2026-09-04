# 03 — Bill: chia tiền khớp từng đồng, OCR chạy nền, và khóa phiên bản

> **Phạm vi**: BE module `bill` (`/api/v1/bills` + group close) ↔ FE Bill Capture / Bill Detail / modal OCR.
>
> Code tham chiếu chính: `PaySplit-BE/internal/modules/bill/**`, `PaySplit-FE/lib/features/bills/**`.
>
> Đọc cùng: [`08-realtime.md`](08-realtime.md) (`ocr.updated`, `bill.*` invalidate), [`02-group.md`](02-group.md) (lock/unlock nộp bill trên Group Detail), [`04-settlement.md`](04-settlement.md) (void vs QR intent).

---

## 1. Vấn đề, và ý tưởng để giải quyết

### 1.1 Ba người sửa một hóa đơn

Hai máy mở cùng nháp, một người chốt, một người còn gõ. Nếu không có số phiên bản, người gõ đè mất bản đã chốt, hoặc chốt đè mất món vừa thêm.

> Mọi mutation gửi `version` (không phải `expected_version`). Lệch → `409 VERSION_CONFLICT`. Sửa bill `reviewed` thì SQL **hạ về `draft`** và xóa mốc review.

### 1.2 Tổng tiền phải khớp tuyệt đối, không tin field `total` từ client

OCR hay khai sai tổng. Nếu chia theo `total` client gửi, phần lệch dồn lên người trả. Server tính `allocTotal` từ **tổng thành phần**: `Σ line_total + phí + VAT − giảm giá`.

### 1.3 OCR không được giữ request HTTP

Ghép ảnh, gọi LlamaExtract, timeout nhà cung cấp — nếu nằm trong request thì 15 giây middleware cắt. Tạo bill có ảnh trả **202**, job `bill_ocr` nằm **cùng transaction** (BeforeCommit). App chờ trên kênh realtime, không poll 1.5 giây.

### 1.4 Nguyên tắc quyền

Tạo bill: **mọi member active** — người tạo thành creditor. Sửa / xóa nháp / review / OCR: **Captain hoặc creditor**. Finalize / void / khóa nộp / finalize-all: **chỉ Captain**. Xem: member active.

Single-bill finalize/void khi không phải Captain → `403 FORBIDDEN` (không phải `CAPTAIN_REQUIRED`). `CAPTAIN_REQUIRED` chỉ đi với group-close.

---

## 2. Bảng tổng quan

| Khái niệm | Giá trị |
|---|---|
| Vòng đời | `draft` → `reviewed` → `finalized` → `voided`. Xóa cứng chỉ `draft` |
| Khóa lạc quan | Cột `version`, CAS trong SQL |
| Ảnh | 1–5, ≤10MB. FE magic JPEG/PNG/WebP/HEIC. BE processor **jpeg/png/HEIC** (WebP FE nhận, BE không) |
| Tạo có ảnh | **202**. Tạo JSON không ảnh | **201** |
| OCR | LlamaExtract. 1 job active / bill. Retry tay mặc định **5 / 24h** (đếm **mọi** job trong cửa sổ, kể cả job lúc tạo). River `BILL_OCR_MAX_ATTEMPTS` mặc định **3** (20 chỉ là trần bit-shift backoff) |
| Chia tiền | Số hữu tỷ `big.Rat` + **largest remainder**, hòa UUID tăng dần. **Không** dồn phần lẻ cho creditor |
| Review/finalize lệch số | `422 BILL_NOT_READY` — **không** kèm danh sách code. GET detail mới nhét code vào `mismatch_codes` |
| Idempotency | Bảng `bill_idempotency_keys`, TTL 24h. Unlock submissions **không** dùng key |
| Khóa nộp bill | Có **unlock**. Finalize-all tự bật khóa |
| `replaces_bill_id` | Tạo bill mới trỏ bill **voided** cùng nhóm. FE chưa gửi |
| Realtime mặc định | `invalidate` + `ocr.updated` trên user stream. `GET /bills/{id}/events` là legacy |

---

## 3. Vòng đời

```mermaid
flowchart LR
    D["draft"] -->|"POST /review<br/>pass blockers"| R["reviewed"]
    R -->|"PUT / PATCH"| D
    R -->|"POST /finalize<br/>chỉ Captain"| F["finalized"]
    F -->|"POST /void + lý do<br/>chỉ Captain"| V["voided"]
    D -->|"DELETE"| X["Xóa cứng"]
    F -.->|"replaces_bill_id<br/>chỉ trỏ voided"| D
```

Review đã `reviewed` và `version` khớp → trả nguyên (idempotent). `version` lệch trên bill reviewed → `BILL_IMMUTABLE`.

---

## 4. Thuật toán chia tiền (largest remainder)

Đây là chỗ tài liệu cũ sai, nên nói thẳng.

> **Không** phải "lượt 2 creditor hấp thụ remainder". Code hiện tại: tính **đúng số hữu tỷ**, floor từng người, phần lẻ +1 đồng chia theo **phần thập phân lớn nhất**. Hòa → UUID membership **tăng dần**. Creditor không được ưu tiên. Test `100_000 / 3`: remainder có thể về member khác, creditor adjustment = 0.

```mermaid
flowchart TD
    A["items FinalPrice + SC + VAT + general_discount"] --> B["allocTotal = Σ line + SC + VAT − discount<br/>bỏ qua field total client"]
    B --> C["Share món = line × weight / Σweight. Thiếu weight → 1. Thang 1e8"]
    C --> D["SC / VAT / discount tỷ lệ theo tiền hàng.<br/>itemsTotal=0 → cả cục về creditor"]
    D --> E["Cap: discount non-creditor vượt số họ nợ → phần dư dồn discount của creditor"]
    E --> F{"Ai exact final < 0?"}
    F -->|"Creditor"| G["422 DISCOUNT_NOT_ALLOCATABLE — không tự kẹp"]
    F -->|"Người khác"| H["Lỗi invariant"]
    F -->|"Không"| I["Floor từng người. remaining = allocTotal − Σ floor ∈ [0, n)"]
    I --> J["+1 đồng cho ai fractional lớn nhất, hòa UUID tăng"]
    J --> K["RoundingAdjustment = Final − (item+SC+VAT−discount floors) — có thể ở BẤT KỲ ai"]
    K --> L{"Σ Final == allocTotal?"}
    L -->|"Không"| M["Lỗi invariant"]
    L -->|"Có"| N["Hợp lệ"]
```

Giảm giá 2 lớp: `final_price = line_total − discount_amount` do **server** tính, client gửi `final_price` bị bỏ. `general_discount = discount − total_item_discount`. DB CHECK `check_bills_discount_composition`.

`/bills/calculate` parse weight **nghiêm** (không default 1). Thiếu `creditor_member_id` → `ErrCreditorRequired`. Trên HTTP review/finalize, lỗi này bị gói thành `BILL_NOT_READY`.

---

## 5. Endpoint và màn hình

Tất cả `liveAuth`, mount `/api/v1/bills`.

| Method + Path | Việc |
|---|---|
| POST `/bills` | Multipart `images[]` hoặc JSON. Có ảnh → **202** |
| GET `/bills` | `group_id` bắt buộc. Cursor + `status` là đường chính. Offset legacy **cấm** kèm status |
| GET `/bills/{id}` | `group_id` query. Signed URL 5 phút. Preview breakdown chỉ draft/reviewed. `mismatch_codes` |
| GET `/bills/{id}/events` | SSE legacy OCR |
| POST `/bills/{id}/ocr-retry` | **202**. FE **không gọi** |
| POST `/bills/{id}/apply-candidate` | Body `{job_id, version}` — **không** `candidate_id` / `client_version`. FE **không gọi**; apply = merge local + PUT draft |
| POST `/bills/calculate` và `/{id}/calculate` | Cùng handler; `{id}` không dùng |
| PUT/PATCH `/bills/{id}` | Body `version` |
| POST `/bills/{id}/review` | `{version}` |
| POST `/bills/{id}/finalize` | `{version}` — Captain, 403 FORBIDDEN nếu không |
| POST `/bills/{id}/void` | `{version, reason}` 1–500 |
| DELETE `/bills/{id}` | **204**, chỉ draft |

Group close (`/api/v1/groups`, Captain; non-member → `GROUP_NOT_FOUND`):

| Method | Path |
|---|---|
| POST | `/{groupId}/bills/lock-submissions` (Idempotency-Key tùy chọn) |
| POST | `/{groupId}/bills/unlock-submissions` (**không** idempotency) |
| POST | `/{groupId}/bills/finalize-all` → **202** |
| GET | `/{groupId}/bill-finalize-batches/{batchId}` |

FE: `/scan-bill` (extra groupId, groupName) — thiếu groupId redirect `/bills`. `/bill-detail` extra entity hoặc Map.

---

## 6. Sequence Diagrams

### 6.1 Tạo thủ công

```mermaid
sequenceDiagram
    autonumber
    actor U as Member (sẽ thành creditor)
    participant FE as Capture → Detail
    participant BE as Bill API
    participant DB as PostgreSQL

    U->>FE: Nhập thủ công (0 ảnh)
    FE->>U: BillDetail id='' status=draft
    U->>FE: Món, gán người, thuế/phí/KM
    FE->>BE: POST /bills JSON
    BE->>DB: Caller phải member active
    BE->>DB: Pre-check bill_submission_locked_at TRƯỚC xử lý nặng
    alt Đã khóa
        BE-->>FE: 409 BILL_SUBMISSION_LOCKED
    end
    BE->>BE: ≤100 items, discount ≥ 0
    Note over DB: INSERT draft version=1 + items + assignments. Creditor = caller
    BE-->>FE: 201 {bill}
```

### 6.2 OCR: 202, worker, user stream — không poll 1.5s

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant FE as Capture → Detail
    participant BE as Bill API
    participant DB as PostgreSQL
    participant Q as River
    participant W as OCRWorker
    participant AI as LlamaExtract
    participant CDN as Cloudinary

    U->>FE: 1–5 ảnh → Chia tiền N
    FE->>FE: ImageValidator magic + ≤10MB
    FE->>BE: POST /bills multipart group_id, merchant_name, images[]
    BE->>DB: Pre-check lock + member
    BE->>CDN: Upload; fail sau đó → rollback xóa
    alt Khóa giữa chừng sau upload
        BE->>Q: Enqueue media_cleanup (fallback delete thẳng)
        BE-->>FE: 409 BILL_SUBMISSION_LOCKED
    end
    Note over DB: bill draft + images + OCRJob queued + ENQUEUE bill_ocr cùng tx
    BE-->>FE: 202 {bill chưa có items}
    FE->>FE: Đăng ký ocr.waiter + bill.detail. Mặc định KHÔNG mở /bills/{id}/events

    par Worker
        Q-->>W: bill_ocr
        W->>DB: Skip nếu succeeded/failed. CAS queued→processing
        W->>CDN: Tải private → ghép DỌC, resize >1200px, JPEG 90%. Ghép fail → ảnh đầu
        W->>AI: Extract (timeout cấu hình, mặc định 8s)
        alt schema_invalid
            W->>DB: failed, KHÔNG River retry
        else Lỗi tạm, Attempt < MaxAttempts (mặc định 3)
            W-->>Q: backoff base×2^(attempt−1)
        else Hết lần
            W->>DB: failed mã đóng provider_timeout/unavailable/error/download_failed/no_images/bill_not_found
            W->>BE: ocr.updated failed
        else OK
            W->>DB: candidate JSONB + version bill lúc OCR
            W->>BE: ocr.updated succeeded
        end
    and FE chờ
        alt User stream (mặc định)
            BE-->>FE: ocr.updated khớp bill_id → GET /bills/{id}
        else Legacy REALTIME_MODE
            FE->>BE: GET /bills/{id}/events snapshot rồi ocr.updated
        end
        Note over FE: Timeout 60s. GET ngay, GET mỗi frame liên quan, GET lần nữa khi hết giờ.<br/>Không có vòng 1.5s × 40
    end

    FE->>U: Modal candidate + mismatch nếu có
    alt User áp
        FE->>FE: Merge local + PUT draft {version}
        Note over FE: Không gọi apply-candidate
    else Retry
        FE->>BE: POST /bills multipart LẠI — bill mới, bill cũ có thể thành nháp mồ côi
        Note over FE: Không gọi /ocr-retry
    else Nhập tay / hết 60s
        FE->>U: Form thủ công trên bill hiện có
    end
```

Apply-candidate phía BE (nếu client khác gọi): Captain/creditor; job succeeded; **kép version**: `bill.Version == request.version` không thì `VERSION_CONFLICT`; `bill.Version == ocrJob.Version` không thì `OCR_RESULT_STALE`. Gán **mọi** member active weight `1.0000` — không bỏ qua khi `item_ratio`.

### 6.3 Lưu → Review → Finalize

```mermaid
sequenceDiagram
    autonumber
    actor U as Creditor hoặc Captain
    participant FE as BillDetail sticky bar
    participant BE as Bill API
    participant DB as PostgreSQL
    participant Q as River

    U->>FE: Gửi đối soát / Chốt (Captain draft: save → review → finalize một mạch)
    FE->>BE: PUT {..., version}
    alt Version lệch
        BE-->>FE: 409 VERSION_CONFLICT — FE: dữ liệu đã bị thay đổi, tải lại
    end
    FE->>BE: POST /review {version}
    BE->>BE: evaluateAllocation
    alt Có blocker
        BE-->>FE: 422 BILL_NOT_READY — không kèm codes
        Note over FE: Disable nút dựa trên tính local (unassigned, mismatch). Dialog món chưa gán là FE tự liệt kê
    else Pass
        BE->>DB: reviewed
        BE-->>FE: 200
    end

    U->>FE: Captain Chốt chia tiền
    FE->>FE: Nút disable nếu !hasBankAccount || hasNoItems || hasUnassignedItems || isTotalMismatch
    Note over FE: hasBankAccount nhìn STK USER ĐĂNG NHẬP, không phải creditor
    FE->>BE: POST /finalize {version} + Idempotency-Key UUID
    alt Không phải Captain
        BE-->>FE: 403 FORBIDDEN
    else Creditor chưa đủ STK
        BE-->>FE: 422 BANK_ACCOUNT_REQUIRED
    else OK
        Note over DB: 1 tx: finalized + snapshot bill_shares + debts awaiting (amount>0, non-creditor) + notifications + activity
        BE->>Q: send_notification × N cùng tx
        BE-->>FE: 200
        FE->>U: Badge Đã chốt, bar [Huỷ][Xem phân bổ]
    end
```

Blockers thu thập **trước** allocation: `ITEM_UNASSIGNED`, `INACTIVE_MEMBER_ASSIGNED`, `CREDITOR_REQUIRED`, `DISCOUNT_EXCEEDS_BILL`, `SUBTOTAL_MISMATCH` (subtotal ≠ Σ LineTotal), `TOTAL_MISMATCH`. **Mismatch chặn review** — không còn là warning. GET detail mới merge chúng vào `mismatch_codes`.

### 6.4 Void — QR intent không giữ nợ

```mermaid
sequenceDiagram
    autonumber
    actor C as Captain
    participant FE as BillDetail
    participant BE as Bill API
    participant DB as PostgreSQL

    C->>FE: Huỷ — dialog lý do FE ≥3, BE 1–500
    FE->>BE: POST /void {reason, version}
    BE->>DB: Lock group → bill FOR UPDATE → debts ORDER BY id ASC FOR UPDATE
    alt Không phải Captain / chưa finalized / version lệch
        BE-->>FE: 403 FORBIDDEN / 400 / 409 VERSION_CONFLICT
    else Debt không còn awaiting HOẶC payment_id đã set
        BE-->>FE: 409 PAYMENT_ALREADY_STARTED
        Note over BE: pending_proof chỉ là QR intent, chưa gán payment_id → vẫn void được, payment → superseded
    else OK
        BE->>DB: pending_proof liên quan → superseded; void debts; bill voided; activity voided_bill; invalidate bill.voided
        BE-->>FE: 200
        FE->>U: Badge Đã hủy. Bar vẫn có Xem phân bổ
    end
```

### 6.5 Khóa nộp và finalize-all

Khóa **không còn một chiều**. Unlock: `POST .../unlock-submissions`.

```mermaid
sequenceDiagram
    autonumber
    actor C as Captain
    participant FE as Group Detail
    participant BE as Bill Close API
    participant DB as PostgreSQL
    participant Q as River

    C->>BE: POST lock-submissions
    BE->>DB: Lock group → Captain → COALESCE bill_submission_locked_at
    Note over BE: Đã khóa → 200 cùng mốc, không ghi activity trùng

    C->>BE: POST finalize-all (Idempotency-Key tùy chọn, complete trong tx)
    BE->>DB: Lock → Captain → BẬT khóa submissions
    alt Đã có batch active
        BE-->>C: 409 BULK_FINALIZE_IN_PROGRESS {active_batch_id}
    else OK
        BE->>DB: Capture mọi draft/reviewed KÈM version → batch + items
        BE->>Q: bill_bulk_finalize_item × N cùng tx
        alt Batch rỗng
            BE-->>C: completed ngay + notify Captain
        end
    end

    loop Mỗi bill = 1 tx riêng
        Q-->>Q: lock group → batch → item → bill
        alt Item không còn pending
            Note over Q: Skip, at-least-once
        else Bill đã xóa (bill_id cố ý không FK)
            BE->>DB: failed BILL_DELETED, commit ngay
        else Finalized với captured_version+1 (ai đó chốt tay)
            BE->>DB: Đánh dấu finalized, không ghi trùng shares/nợ
        else Version lệch / voided / thiếu bank / allocation
            BE->>DB: failed ổn định, không River retry
        else draft: review + finalize trong tx
            BE->>DB: Item finalized; TryCompleteBatch → notify Captain
        end
    end
```

---

## 7. Activity Diagrams

### 7.1 Capture

```mermaid
flowchart TD
    A["BillCapture extra groupId"] --> B["Camera q88 max 1920 hoặc thư viện. Camera fail → PNG dummy 1×1"]
    B --> C{"Số ảnh > 5?"}
    C -->|"Có"| D["SnackBar"] --> B
    C -->|"Không"| E["Magic JPEG/PNG/WebP/HEIC + ≤10MB"]
    E --> F{"Hợp lệ?"}
    F -->|"Không"| G["Loại"] --> B
    F -->|"Có"| H["Tray: kéo, xoay 90°, crop, xóa"]
    H --> I{"Nút header"}
    I -->|"0 ảnh Nhập thủ công"| J["BillDetail id='' draft"]
    I -->|">=1 Chia tiền N"| K["BillDetail photos autoStartOcr"]
    K --> L["POST multipart 202 + chờ ocr.updated 60s"]
    L --> M{"OCR?"}
    M -->|"succeeded"| N["Modal → merge local + PUT"]
    M -->|"fail / hết giờ"| P["Retry = POST /bills mới, hoặc nhập tay"]
    J --> Q["Bill Detail"]
    N --> Q
    P --> Q
```

### 7.2 Sticky bar theo status × role

Cảnh báo vàng disable nút chính: `!hasBankAccount || hasNoItems || hasUnassignedItems || isTotalMismatch`.

```mermaid
flowchart TD
    A["Sticky bar"] --> B{"Warning?"}
    B -->|"Có"| C["Outline, disable"]
    B -->|"Không"| D{"status"}
    D -->|"draft"| E{"role"}
    E -->|"Captain"| E1["Lưu nháp (disable !dirty) + Chốt hoá đơn"]
    E -->|"Creditor"| E2["Lưu nháp + Gửi đối soát"]
    E -->|"Member"| E3["Xem phân bổ"]
    D -->|"reviewed"| F{"role"}
    F -->|"Captain"| F1["Sửa lại + Chốt chia tiền"]
    F -->|"Creditor"| F2["Gửi đối soát disable !dirty"]
    F -->|"Member"| F3["Xem phân bổ"]
    D -->|"finalized"| G{"Captain?"}
    G -->|"Có"| G1["Huỷ + Xem phân bổ"]
    G -->|"Không"| G2["Xem phân bổ"]
    D -->|"voided"| H["Xem phân bổ outline — không ẩn hết"]
```

`isCaptain` / `isCreditor` **mặc định true** khi chưa có `currentUserId` hoặc `members` rỗng — tránh khóa UI nhầm. BE vẫn chặn.

---

## 8. Realtime

| Loại | Khi | Surface đánh thức |
|---|---|---|
| `bill.created` / `content_changed` / `reviewed` | create / PUT / review | `bill.detail`, `group.bills`, hai list nhóm, `home.activities` |
| `bill.deleted` / `finalized` / `voided` | | thêm `group.debts`, `group.detail`, `settlement.overview` |
| `bill.settlement_changed` | proof/confirm/reject | `bill.detail`, `group.bills` |
| `ocr.updated` | worker | `ocr.waiter`, `bill.detail` khớp đúng id |
| `group.bill_submission_locked` | lock/unlock | `group.detail`, `group.roster`, hai list nhóm |

Không có event `bill.updated`. FE đăng ký `ocr.waiter` cạnh `bill.detail` trong notifier.

---

## 9. Edge Cases

### 9.1 Chia tiền

| # | Tình huống | Xử lý | Mã |
|---|---|---|---|
| 1 | 100k / 3 người | Largest remainder + UUID tie, không dồn creditor | — |
| 2 | `total` OCR sai | Bỏ qua, dùng allocTotal thành phần | — |
| 3 | Discount lớn quá | Cap non-creditor; creditor vẫn âm → không kẹp | `DISCOUNT_NOT_ALLOCATABLE` (review: gói `BILL_NOT_READY`) |
| 4 | Discount > bill | Blocker | `DISCOUNT_EXCEEDS_BILL` → `BILL_NOT_READY` |
| 5 | Món chưa gán | Blocker; FE tự liệt kê | `ITEM_UNASSIGNED` chỉ trên GET `mismatch_codes` |
| 6 | Gán member đã rời | Blocker | `INACTIVE_MEMBER_ASSIGNED` |
| 7 | Calculate thiếu creditor | | usecase `CREDITOR_REQUIRED`; HTTP review `BILL_NOT_READY` |
| 8 | SUBTOTAL/TOTAL_MISMATCH | **Chặn review**, không còn warning | `BILL_NOT_READY` |

### 9.2 Đồng thời

| # | Tình huống | Xử lý | Mã |
|---|---|---|---|
| 9 | 2 máy sửa nháp | CAS version | `409 VERSION_CONFLICT` |
| 10 | Apply-candidate stale | Kép version | `VERSION_CONFLICT` / `OCR_RESULT_STALE` |
| 11 | 2 retry OCR | Unique active job + CAS | `409 OCR_ALREADY_RUNNING` |
| 12 | Spam retry tay | 5 / 24h kể cả job lúc tạo | `429 OCR_LIMIT_REACHED` |
| 13 | Nộp khi đã khóa | Pre-check + re-check trong tx; ảnh lỡ → cleanup | `409 BILL_SUBMISSION_LOCKED` |
| 14 | Void khi đã nộp proof | `payment_id` set hoặc không awaiting | `409 PAYMENT_ALREADY_STARTED` |
| 15 | Void khi mới có QR | Debts còn awaiting, payment_id NULL → void được, QR superseded | `200` |
| 16 | Key tái sử dụng payload khác | | `409 IDEMPOTENCY_KEY_REUSED` |
| 17 | Key in_progress | | `409 IDEMPOTENCY_IN_PROGRESS` |
| 18 | Mutation fail sau reserve | Release key | — |
| 19 | Bill xóa giữa bulk | Item BILL_DELETED, batch chạy tiếp | — |

### 9.3 OCR / FE

| # | Tình huống | Xử lý |
|---|---|---|
| 20 | Provider tạm | River retry đến MaxAttempts (mặc định 3) |
| 21 | schema_invalid | Fail ngay, không retry |
| 22 | Job giao trùng | Skip terminal; CAS processing |
| 23 | Mất SSE | User stream reconnect + `ready` hàn; waiter GET lại |
| 24 | Camera desktop | PNG dummy |
| 25 | File giả đuôi jpg | FE magic bytes |
| 26 | WebP | FE nhận, BE processor từ chối |
| 27 | FE Retry OCR | Tạo **bill mới**, không `/ocr-retry` |
| 28 | FE Apply OCR | PUT draft, không `/apply-candidate` |
| 29 | Finalize thiếu STK | BE nhìn **creditor**; FE nhìn **user đang login** — Captain không phải creditor có thể thấy nút khác BE |
| 30 | Non-Captain finalize | `403 FORBIDDEN` |
| 31 | Void không lý do | BE 1–500; FE ≥3 | `VALIDATION_FAILED` |
| 32 | Finalize-all trùng batch | `409 BULK_FINALIZE_IN_PROGRESS` |
| 33 | Member đoán batch id | `403 CAPTAIN_REQUIRED` |
| 34 | Tạo bill | Mọi member active, không chỉ Captain/creditor |

---

## 10. Cấu hình

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `BILL_OCR_MAX_ATTEMPTS` | `3` | River, không phải 20 |
| `BILL_OCR_MANUAL_LIMIT` / `WINDOW_HOURS` | `5` / `24` | Retry tay |
| `BILL_IMAGE_MAX_BYTES` / `COUNT` | 10MiB / 5 | |
| OCR provider timeout | `8s` | LlamaExtract |
| Signed URL ảnh / proof | 5 phút | |

---

## 11. Ghi chú triển khai đáng chú ý

1. **`version` trong JSON, không `expected_version`.** Client cũ gửi sai tên field = validate fail, không phải conflict.

2. **Largest remainder, không remainder-to-creditor.** Đổi "cho công bằng người trả" là đổi invariant đã có test.

3. **Review trả `BILL_NOT_READY` trần.** Đừng vẽ sequence FE hiện code từ body 422. Code nằm ở GET `mismatch_codes` và tính local.

4. **FE không gọi apply-candidate / ocr-retry.** Tài liệu endpoint vẫn đúng cho client khác. Mô tả app thì nói PUT và POST `/bills` lại.

5. **Khóa nộp có unlock.** Migration comment V1 "một chiều" stale.

6. **QR `pending_proof` không chặn void.** Chỉ proof (debts `pending_confirmation` + `payment_id`) mới `PAYMENT_ALREADY_STARTED`. Xem [`04-settlement.md`](04-settlement.md).

7. **`hasBankAccount` FE ≠ creditor BE.** Nút Captain có thể enable rồi ăn 422, hoặc disable oan.

8. **Idempotency fail phải Release.** Không thì retry kẹt 409 mãi.

9. **Bulk: mỗi bill một tx.** Một bill fail không rollback bill khác. `bill_id` không FK để xóa draft vẫn được.

10. **Job OCR enqueue cùng tx tạo bill.** Rollback → không có job mồ côi. Worker skip terminal vì River at-least-once.

11. **Log OCR nhà cung cấp:** chỉ mã đã phân loại + mô tả cắt 120 ký tự. Không dump candidate, không dump ảnh.

---

## 12. Trạng thái hiện tại

| Hạng mục | Trạng thái | Ghi chú |
|---|---|---|
| Thủ công / review / finalize / void | ✅ | Version CAS |
| OCR LlamaExtract + user stream | ⚠️ Unit test đủ; runtime phụ thuộc nhà cung cấp thật | AC-21 |
| Khóa / mở nộp bill | ✅ | FE Group Detail gọi API |
| Finalize-all | ✅ | |
| Apply-candidate / ocr-retry HTTP | ✅ BE | FE chưa dùng |
| `replaces_bill_id` | ✅ BE | FE chưa gửi |
| SSE `/bills/{id}/events` | ⚠️ Legacy | Cổng 410 chưa bật |
