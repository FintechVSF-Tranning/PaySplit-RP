# 🔍 CẨM NANG SOI CODE & TRUY VẾT KỸ THUẬT (CODE DEEP DIVE)
### Dành riêng cho 3 Module: OCR • Chia Bill & Vòng Đời • Thông Báo (River Queue)

> **Mục tiêu:** Giúp bạn nắm trọn từng dòng code, struct, thuật toán, hàm xử lý và câu lệnh SQL trong thực tế. Khi Mentor yêu cầu *"Mở code ra giải thích chỗ này hoạt động thế nào"*, bạn có thể mở đúng file, chỉ đúng dòng và trả lời rành mạch với phong thái của một kỹ sư giàu kinh nghiệm.

---

## MỤC LỤC BẢN ĐỒ CODE

1. [BẢN ĐỒ ĐỊNH VỊ CODEBASE (MENTAL MAP)](#1-bản-đồ-định-vị-codebase-mental-map)
2. [DEEP DIVE CODE: MODULE 1 - OCR PROCESSING PIPELINE](#2-deep-dive-code-module-1---ocr-processing-pipeline)
   - 2.1. HTTP Entrypoint & Chặn tràn bộ nhớ (`handler.go`)
   - 2.2. River Worker, Ghép ảnh & Giải phóng RAM (`ocr_worker.go`)
   - 2.3. Cấu trúc JSON Schema gửi cho AI (`schema.go`)
   - 2.4. Tầng chuẩn hóa & Xử lý biên tinh vi (`normalizer.go`)
   - 2.5. Cơ chế dọn dẹp dữ liệu cũ (`retention.go`)
3. [DEEP DIVE CODE: MODULE 2 - CHIA BILL & QUẢN LÝ VÒNG ĐỜI HÓA ĐƠN](#3-deep-dive-code-module-2---chia-bill--quản-lý-vòng-đời-hóa-đơn)
   - 3.1. Thuật toán số học phân số chính xác & Hamilton (`allocation.go`)
   - 3.2. Quản lý trạng thái & Chốt hóa đơn nguyên khối (`service.go`)
   - 3.3. Tầng lưu trữ, Khóa dòng & Snapshot bất biến (`bill.sql` & `repository.go`)
   - 3.4. Khóa một chiều & Batch Processing (`bill_close.go`)
4. [DEEP DIVE CODE: MODULE 3 - NOTIFICATION & RIVER WORKER](#4-deep-dive-code-module-3---notification--river-worker)
   - 4.1. Thiết kế Thin Job Pattern (`send_notification.go`)
   - 4.2. Luồng xử lý Worker & Phân loại lỗi Firebase (`send_notification.go`)
   - 4.3. Transactional Enqueue trong cùng PostgreSQL Tx (`service.go`)
   - 4.4. Truy vấn Token từ Active Session (`notification.sql`)
5. [BỘ 15 CÂU HỎI "CHỈ TAY VÀO CODE" CỦA MENTOR (CODE GRILLING Q&A)](#5-bộ-15-câu-hỏi-chỉ-tay-vào-code-của-mentor-code-grilling-qa)

---

# 1. BẢN ĐỒ ĐỊNH VỊ CODEBASE (MENTAL MAP)

Để không bị bối rối khi mentor yêu cầu mở code, hãy ghi nhớ vị trí các file theo bảng tra cứu sau:

```text
PaySplit-BE/
├── internal/platform/
│   ├── ocr/llamaextract/
│   │   ├── schema.go          # [OCR] JSON Schema định nghĩa cấu trúc gửi LlamaExtract
│   │   ├── normalizer.go      # [OCR] Logic gộp KM, sửa ngày mập mờ, kiểm tra số học
│   │   └── client.go          # [OCR] HTTP Client gọi API LlamaExtract kèm retry/timeout
│   └── queue/river/           # [Queue] Cấu hình River Queue trên pgxpool
│
└── internal/modules/
    ├── bill/
    │   ├── delivery/http/
    │   │   └── handler.go     # [HTTP] Chặn dung lượng upload, REST endpoints
    │   ├── domain/
    │   │   ├── bill.go        # [Domain] Entity Bill, Item, Assignment, Error sentinels
    │   │   └── ocr.go         # [Domain] OCRJob, OCRCandidate, Status enum
    │   ├── jobs/
    │   │   ├── ocr_worker.go  # [Worker] Ghép 1-5 ảnh, gọi OCR, error classification
    │   │   └── retention.go   # [Cron] Tự động xóa raw OCR JSON sau 30 ngày
    │   ├── usecase/
    │   │   ├── allocation.go  # [Toán] Thuật toán Hamilton bằng big.Rat & Tie-breaking
    │   │   ├── service.go     # [Logic] FinalizeBill, ReviewBill, OCC Version check
    │   │   └── bill_close.go  # [Batch] Khóa 1 chiều LockSubmissions, StartBulkFinalize
    │   └── repository/postgres/
    │       ├── repository.go  # [DB Tx] Thực thi Transaction ghi bill_shares & debts
    │       └── queries/
    │           └── bill.sql   # [SQL] Truy vấn FOR UPDATE, lateral joins, cursor paging
    │
    └── notification/
        ├── domain/
        │   └── notification.go# [Domain] Entity Notification, Type constants
        ├── jobs/
        │   └── send_notification.go # [Worker] Bốc job, gọi FCM, dọn token rác
        └── repository/postgres/
            └── queries/
                └── notification.sql # [SQL] Query FCM token từ sessions còn hạn
```

---

# 2. DEEP DIVE CODE: MODULE 1 - OCR PROCESSING PIPELINE

## 2.1. HTTP Entrypoint & Chặn tràn bộ nhớ (`handler.go`)
* **Vị trí file:** `internal/modules/bill/delivery/http/handler.go`
* **Hàm then chốt:** `CreateBill(w http.ResponseWriter, r *http.Request)` (Dòng 83)

```go
// Đoạn code phòng thủ sớm (Early Defense):
const multipartOverheadSlack = 1 << 20 // 1MB cho metadata JSON, boundary
maxBodyBytes := h.imageMaxBytes*int64(h.imageMaxCount) + multipartOverheadSlack
r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)
```

### 💡 Điểm đắt giá cần nói với Mentor:
* Không bao giờ gọi `ParseMultipartForm` ngay từ đầu. Chúng ta bọc `r.Body` qua `http.MaxBytesReader` để **chặn stream mạng ngay lập tức** nếu client cố tình đẩy file vượt quá giới hạn ($5 \text{ ảnh} \times 10\text{MB} + 1\text{MB metadata}$). Điều này chống tấn công từ chối dịch vụ (DoS) làm cạn kiệt RAM server trước khi kịp ghi file ra đĩa.

---

## 2.2. River Worker, Ghép ảnh & Giải phóng RAM (`ocr_worker.go`)
* **Vị trí file:** `internal/modules/bill/jobs/ocr_worker.go`
* **Hàm then chốt:** `Work(ctx context.Context, job *river.Job[OCRJobArgs]) error` (Dòng 134)

### Điểm 1: Ghép hóa đơn nhiều trang (Multi-page Stitching)
```go
imageBytes := allBytes[0]
if len(allBytes) > 1 {
    stitched, err := stitchReceiptImages(allBytes)
    if err == nil && len(stitched) > 0 {
        imageBytes = stitched
    }
}
```
* Nếu hóa đơn dài nhiều trang (1-5 ảnh), hàm `stitchReceiptImages` (dùng thư viện `imaging`) sẽ nối dọc các ảnh lại thành 1 ảnh JPEG duy nhất trước khi gửi cho model AI phân tích, giúp AI hiểu được ngữ cảnh liền mạch từ đầu tới chân hóa đơn.

### Điểm 2: Quản lý bộ nhớ thủ công để hỗ trợ Garbage Collector
```go
candidate, rawJSON, err := w.ocrProvider.ExtractReceipt(extractCtx, imageBytes, "image/jpeg")
imageBytes = nil // <-- DÒNG ĐẮT GIÁ: Giải phóng con trỏ buffer ảnh ngay lập tức
```
* Mảng byte ảnh ghép có thể nặng từ 5MB – 15MB. Việc gán `imageBytes = nil` ngay sau khi gọi mạng giúp Go Garbage Collector (GC) thu hồi vùng nhớ heap này ngay lập tức, ngăn ngừa hiện tượng **Out-Of-Memory (OOM)** khi có nhiều worker chạy đồng thời.

### Điểm 3: Bộ mã lỗi đóng bảo mật (Bounded Error Codes)
```go
const (
    ocrErrorBillNotFound        = "bill_not_found"
    ocrErrorSchemaInvalid       = "schema_invalid"
    ocrErrorProviderTimeout     = "provider_timeout"
    ocrErrorProviderUnavailable = "provider_unavailable"
    ocrErrorProvider            = "provider_error"
)
```
* **Tại sao không log lỗi thô của AI?** Vì body lỗi từ AI có thể chứa chính văn bản hóa đơn nhạy cảm (tên người mua, món ăn riêng tư). Hàm `ocrErrorCode()` ép mọi lỗi về một danh sách mã enum đóng, tuyệt đối không lộ dữ liệu tài chính vào log hệ thống.

---

## 2.3. Cấu trúc JSON Schema gửi cho AI (`schema.go`)
* **Vị trí file:** `internal/platform/ocr/llamaextract/schema.go`
* **Hàm then chốt:** `ReceiptSchema() map[string]any` (Dòng 8)

```go
"items": map[string]any{
    "type": "array",
    "description": "Danh sách món ăn, bao gồm cả các dòng khuyến mãi/chiết khấu riêng theo món... với line_total âm hoặc bằng giá trị được giảm",
    "properties": map[string]any{
        "name":       map[string]any{"type": "string"},
        "quantity":   map[string]any{"type": "string"},
        "unit_price": map[string]any{"type": "integer"},
        "line_total": map[string]any{"type": "integer"},
    },
    "required": []string{"name", "line_total"},
}
```
* **Quyết định kiến trúc:** Model AI được yêu cầu trả về các số tiền dưới dạng `integer` VND (không nhận float). Dòng khuyến mãi được phép trả về `line_total` mang dấu âm. Trách nhiệm gộp khuyến mãi thuộc về tầng **Normalizer**, không phụ thuộc vào độ tin cậy của prompt AI.

---

## 2.4. Tầng chuẩn hóa & Xử lý biên tinh vi (`normalizer.go`)
* **Vị trí file:** `internal/platform/ocr/llamaextract/normalizer.go`
* **Hàm then chốt:** `Normalize(rawBytes []byte) (*domain.OCRCandidate, error)` (Dòng 34)

### Logic 1: Nhận diện & Gộp dòng Khuyến mãi (Line 105 - 150)
```go
isPromotionLine := isPromotionMarker(name) || rawLineTotal < 0 ||
    (isNullOrZeroQuantity(itemMap["quantity"]) && rawLineTotal <= 0)

if isPromotionLine {
    promoValue := absInt64(rawLineTotal)
    if len(items) == 0 {
        // Trường hợp không có món trước: chuyển thành giảm giá chung toàn bill
        orphanItemDiscount += promoValue
        warnings = append(warnings, domain.WarningOCROrphanItemDiscount)
        continue
    }
    // Gộp vào món liền trước
    prevItem := &items[len(items)-1]
    if promoValue <= prevItem.LineTotal {
        prevItem.LineTotal -= promoValue
    } else {
        // Giảm giá vượt giá trị món ăn
        exceededExcessDiscount += (promoValue - prevItem.LineTotal)
        prevItem.LineTotal = 0
    }
}
```

### Logic 2: Phân định ngày tháng mập mờ (Line 380 - 420)
```go
func ParseDate(dateStr string) (*string, bool) {
    // Thử regex DD/MM/YYYY vs YYYY/MM/DD
    // Nếu ngày <= 12 và tháng <= 12 -> isAmbiguous = true
}
```
* Nếu ngày và tháng đều $\le 12$, trả về `isAmbiguous = true` để đưa cảnh báo `WarningOCRDateAmbiguous` lên UI, nhưng backend vẫn xử lý thông suốt mà không crash.

---

## 2.5. Cơ chế dọn dẹp dữ liệu cũ (`retention.go`)
* **Vị trí file:** `internal/modules/bill/jobs/retention.go`
* **Hàm then chốt:** `OCRRetentionWorker.Work()`
* Định kỳ chạy River Cron Job xóa cột `raw_response` (JSON thô chứa thông tin chi tiết hóa đơn từ AI) của các hóa đơn đã xử lý quá 30 ngày. Điều này đảm bảo tuân thủ nguyên tắc **Tối thiểu hóa dữ liệu (Data Minimization)** của luật an toàn thông tin.

---

# 3. DEEP DIVE CODE: MODULE 2 - CHIA BILL & QUẢN LÝ VÒNG ĐỜI HÓA ĐƠN

## 3.1. Thuật toán số học phân số chính xác & Hamilton (`allocation.go`)
* **Vị trí file:** `internal/modules/bill/usecase/allocation.go`
* **Hàm then chốt:** `CalculateAllocation(in AllocationInput) ([]*MemberAllocation, error)` (Dòng 69)

### 1. Phân số chính xác vô hạn với `big.Rat` (Line 118 - 125)
```go
// Thay vì: share := float64(lineTotal) * weight / totalWeight (SAI SỐ FLOAT!)
// Chúng ta dùng:
numerator := new(big.Int).Mul(big.NewInt(item.LineTotal), big.NewInt(assignment.Weight))
share := new(big.Rat).SetFrac(numerator, totalWeight)
exactItems[assignment.MemberID].Add(exactItems[assignment.MemberID], share)
```
* `big.Rat` lưu trữ dạng tử số / mẫu số (`Num / Denom`). Phép cộng phân số của các món diễn ra hoàn toàn chính xác tuyệt đối, không có sai số dấu phẩy động nhị phân.

### 2. Phân bổ phụ phí theo tỷ lệ (Line 155 - 165)
```go
func proportionalRat(total int64, base *big.Rat, totalBase *big.Int) *big.Rat {
    result := new(big.Rat).Mul(new(big.Rat).SetInt64(total), base)
    return result.Quo(result, new(big.Rat).SetInt(totalBase))
}
```
* Thuế VAT và phí dịch vụ của từng người được nhân với tỷ lệ tiền món ăn của họ so với tổng tiền món toàn bàn.

### 3. Điều tiết giảm giá dôi dư cho Creditor (Line 172 - 185)
```go
owed := new(big.Rat).Add(new(big.Rat).Set(exact.item), exact.service)
owed.Add(owed, exact.vat)
if exact.discount.Cmp(owed) > 0 {
    excess := new(big.Rat).Sub(new(big.Rat).Set(exact.discount), owed)
    exact.discount.Set(owed) // Người này trả 0đ
    creditor.discount.Add(creditor.discount, excess) // Dồn phần giảm giá thừa cho Creditor
}
```

### 4. Thuật toán Hamilton & Deterministic Tie-Breaking (Line 217 - 235)
```go
remaining := allocTotal - sumBase // Số tiền lẻ còn dư (0 <= remaining < N)

orderedByRemainder := append([]uuid.UUID(nil), allMembers...)
sort.SliceStable(orderedByRemainder, func(i, j int) bool {
    left := fractionalPart(exactByID[orderedByRemainder[i]].final)
    right := fractionalPart(exactByID[orderedByRemainder[j]].final)
    if cmp := left.Cmp(right); cmp != 0 {
        return cmp > 0 // Ưu tiên phần thập phân lớn hơn
    }
    // PHÁ VỠ THẾ HÒA: So sánh thứ tự byte của UUID
    return bytes.Compare(orderedByRemainder[i][:], orderedByRemainder[j][:]) < 0
})

// Chia mỗi người 1 VND theo thứ tự ưu tiên
for i := int64(0); i < remaining; i++ {
    exactByID[orderedByRemainder[i]].base++
}
```

### 5. Khóa bảo vệ toàn vẹn (Final Invariant Guard) (Line 281)
```go
if sumFinal != allocTotal {
    return nil, fmt.Errorf("allocation invariant broken: shares sum to %d but computed bill total is %d", sumFinal, allocTotal)
}
```
* Chốt chặn cuối cùng: Nếu tổng tiền của tất cả thành viên sau khi làm tròn không khớp 100% với tổng tiền bill, code lập tức `panic/error`, không bao giờ để dữ liệu sai lệch lọt vào Database.

---

## 3.2. Quản lý trạng thái & Chốt hóa đơn nguyên khối (`service.go`)
* **Vị trí file:** `internal/modules/bill/usecase/service.go`
* **Hàm then chốt:** `FinalizeBill` $\rightarrow$ `finalizeBillImpl` (Dòng 1010)

```text
[Kiểm tra Quyền: member.Role == "captain"]
                   │
[Kiểm tra State: bill.Status == "reviewed"]
                   │
[Kiểm tra Concurrency: bill.Version == expectedVersion]
                   │
[Kiểm tra Điều kiện Tiên quyết: Creditor có STK ngân hàng]
                   │
[Chạy Thuật toán Phân bổ: validateAllocationForFinalize]
                   │
[Tạo Plan: Dựng BillShare + Debts + Notifications]
                   │
[Thực thi DB Transaction: s.repo.FinalizeBill]
```

### Điểm đặc biệt trong `buildFinalizationPlan` (Dòng 1104):
* **Lưu Snapshot bất biến (`BillShare`):** Lưu lại chi tiết từng thành phần: `item_subtotal`, `service_charge_share`, `vat_share`, `discount_share`, và đặc biệt là `rounding_adjustment` (ghi nhận người nào được nhận $\pm 1$đ do làm tròn Hamilton).
* **Tự động sinh công nợ (`Debt`):** Nếu `amount > 0` và không phải là Creditor $\rightarrow$ Sinh ngay bản ghi nợ với trạng thái `awaiting`.
* **Kích hoạt Transactional Enqueue:** Đẩy job thông báo cho từng người thông qua hook `BeforeCommit`.

---

## 3.3. Tầng lưu trữ, Khóa dòng & Snapshot bất biến (`bill.sql`)
* **Vị trí file:** `internal/modules/bill/repository/postgres/queries/bill.sql`

### 1. Pessimistic Locking chống tranh chấp sửa đổi
```sql
-- name: GetBillByIDForUpdate :one
SELECT * FROM bills
WHERE id = $1 AND group_id = $2
FOR UPDATE;
```
* Dùng `FOR UPDATE` khóa dòng hóa đơn trong cơ sở dữ liệu trong suốt thời gian giao dịch diễn ra, ngăn chặn 2 admin cùng bấm chốt hóa đơn cùng một lúc.

### 2. Tính toán tiến độ thanh toán bằng Lateral Query tối ưu
```sql
-- name: ListBillsByGroup :many
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (
            WHERE shares.member_id = b.creditor_member_id
                OR shares.final_amount = 0
                OR debts.status IN ('settled', 'voided')
        ) AS paid_member_count,
        COUNT(*) AS member_count
    FROM bill_shares shares
    LEFT JOIN debts ON debts.bill_id = b.id AND debts.debtor_member_id = shares.member_id
    WHERE b.status = 'finalized' AND shares.bill_id = b.id
) progress ON true
```
* Truy vấn thông minh dùng `LATERAL`: Tiến độ của một bill được tính toán ngay trong câu lệnh SQL duy nhất mà không cần chạy vòng lặp ở tầng ứng dụng, đảm bảo thời gian phản hồi API danh sách bill luôn $<50\text{ms}$.

---

## 3.4. Khóa một chiều & Batch Processing (`bill_close.go`)
* **Vị trí file:** `internal/modules/bill/usecase/bill_close.go`
* **Hàm then chốt:** `LockSubmissions` (Dòng 52) & `StartBulkFinalize` (Dòng 82)

* **Khóa một chiều (`LockSubmissions`):** Kích hoạt cờ `bill_submission_locked = true` trên nhóm. Thiết kế theo nguyên lý **Idempotent**: Gọi lại nhiều lần không sinh lỗi, không ghi log thừa.
* **Bulk Finalize:** Tạo `FinalizeBatch` với UUIDv7 (sắp xếp theo thời gian), gom tất cả bill chưa chốt và dùng vòng lặp `s.enqueuer.EnqueueBulkFinalizeItemTx(txCtx, tx, ...)` đẩy vào River Queue để xử lý song song trên background.

---

# 4. MODULE 3: NOTIFICATION & RIVER WORKER

## 4.1. Thiết kế Thin Job Pattern (`send_notification.go`)
* **Vị trí file:** `internal/modules/notification/jobs/send_notification.go`

```go
type NotificationJobArgs struct {
    NotificationID string `json:"notification_id"`
}

func (NotificationJobArgs) Kind() string { return "send_notification" }
```
### 💡 Phân tích kỹ thuật:
* Struct công việc trong River Queue chỉ chứa duy nhất một trường `NotificationID`.
* **Tại sao không nhét Title, Body hay Token vào Job Args?**
  1. Tránh làm phình to bảng cơ sở dữ liệu `river_job`.
  2. **Tránh Stale Data:** Khi worker chạy sau đó vài giây, người dùng có thể đã đọc thông báo trên web hoặc đã đổi FCM Token trên điện thoại. Bốc lại dữ liệu từ DB đảm bảo worker luôn có trạng thái mới nhất.

---

## 4.2. Luồng xử lý Worker & Phân loại lỗi Firebase (`send_notification.go`)
* **Hàm then chốt:** `Work(ctx context.Context, job *river.Job[NotificationJobArgs]) error` (Dòng 57)

```go
// 1. Nạp dữ liệu tươi từ DB
notif, err := w.repo.GetNotificationByID(ctx, job.Args.NotificationID)

// 2. Tìm Active FCM Token từ phiên đăng nhập còn hạn
token, err := w.repo.GetActiveFCMTokenByUserID(ctx, notif.UserID)
if token == "" {
    return nil // Người dùng chưa đăng nhập thiết bị nào, kết thúc an toàn
}

// 3. Gọi Firebase Cloud Messaging
if sendErr := w.pushNotifier.SendToDevice(ctx, token, msg); sendErr != nil {
    // Phân loại lỗi thông minh:
    if fcm.IsInvalidTokenError(sendErr) {
        _ = w.repo.ClearFCMToken(ctx, notif.UserID, token) // Xóa token chết
        return nil // Không retry
    }
    if fcm.IsInvalidMessageError(sendErr) {
        log.Printf("Payload sai cấu trúc: %v", sendErr)
        return nil // Lỗi logic code, không retry
    }
    return sendErr // Lỗi mạng tạm thời -> Báo River tự động retry với Exponential Backoff!
}
```

---

## 4.3. Transactional Enqueue trong cùng PostgreSQL Tx (`service.go`)
* **Cơ chế:**
```go
// Trong internal/modules/bill/usecase/bill_close.go (Dòng 100):
BeforeCommit: func(txCtx context.Context, tx pgx.Tx, info *repository.BulkStartEnqueueInfo) error {
    for _, notifID := range info.NotificationIDs {
        if err := s.enqueuer.EnqueueNotificationTx(txCtx, tx, notifID); err != nil {
            return fmt.Errorf("enqueue notification job: %w", err)
        }
    }
    return nil
}
```
* Hàm `EnqueueNotificationTx` gọi lệnh `river.Client.InsertTx(ctx, tx, args, nil)`.
* Job được chèn vào bảng PostgreSQL `river_job` **sử dụng chính transaction `tx` đang xử lý hóa đơn**.
* **Đảm bảo tính nguyên tử (Atomicity):** Nếu thao tác lưu bill bị lỗi `ROLLBACK`, job thông báo cũng biến mất hoàn toàn. **Không bao giờ có chuyện gửi thông báo nợ khi hóa đơn chưa được lưu thành công.**

---

## 4.4. Truy vấn Token từ Active Session (`notification.sql`)
* **Vị trí file:** `internal/modules/notification/repository/postgres/queries/notification.sql`

```sql
-- name: GetActiveFCMTokenByUserID :one
SELECT fcm_token
FROM sessions
WHERE user_id = $1 
  AND revoked_at IS NULL 
  AND expires_at > now() 
  AND fcm_token IS NOT NULL 
  AND fcm_token <> ''
ORDER BY issued_at DESC
LIMIT 1;
```
* **Bảo mật tuyệt đối:** Chỉ gửi push notification đến những phiên đăng nhập (`sessions`) **chưa bị thu hồi (`revoked_at IS NULL`)** và **chưa hết hạn (`expires_at > now()`)**. Nếu người dùng vừa bấm Đăng xuất trên thiết bị, token đó sẽ không bao giờ nhận được push thông báo nữa.

---

# 5. BỘ 15 CÂU HỎI "CHỈ TAY VÀO CODE" CỦA MENTOR (CODE GRILLING Q&A)

Dưới đây là 15 câu hỏi thực chiến mà các Senior Engineer hoặc Architect tại các công ty công nghệ lớn thường hỏi khi soi code:

---

### 🔹 VỀ MODULE OCR:
#### 1. "Tại sao ở dòng 220 của `ocr_worker.go`, em lại gán `imageBytes = nil`?"
> **Trả lời:** Mảng byte ảnh sau khi ghép nhiều trang có kích thước khá lớn (từ 5–15MB). Việc gán `imageBytes = nil` ngay khi gọi xong API của provider giúp trình dọn rác (GC) của Go có thể thu hồi vùng nhớ này ngay lập tức ở chu kỳ quét tiếp theo, tránh giữ con trỏ lâu trong suốt thời gian worker đợi DB ghi dữ liệu, hạn chế nguy cơ OOM khi tải cao.

#### 2. "Nếu AI bóc tách trả về một dòng khuyến mãi `-50.000đ` nằm ngay đầu tiên của mảng items thì code xử lý thế nào?"
> **Trả lời:** Tại `normalizer.go` (dòng 117), hàm kiểm tra `if len(items) == 0`. Vì không có món nào phía trước để khấu trừ, hệ thống coi đây là dòng giảm giá chung của toàn bill (`orphanItemDiscount`), cộng giá trị này vào tổng `discount` của hóa đơn và phát sinh cảnh báo `WarningOCROrphanItemDiscount` để người dùng xác nhận ở màn hình Review.

#### 3. "Nếu ảnh hóa đơn bị mờ khiến LlamaExtract trả về JSON sai format hoàn toàn thì hệ thống có bị treo worker không?"
> **Trả lời:** Không ạ. Hàm `Normalize()` trong `normalizer.go` sẽ bắt lỗi unmarshal và trả về lỗi `domain.ErrOcrSchemaInvalid`. Trong `ocr_worker.go` (dòng 224), worker bắt đúng lỗi này và gọi `w.failJob(..., ocrErrorSchemaInvalid)`. Job kết thúc ngay lập tức mà không retry vô ích, đồng thời bắn sự kiện cập nhật trạng thái lỗi về client.

---

### 🔹 VỀ MODULE CHIA BILL & THUẬT TOÁN:
#### 4. "Tại sao không dùng `float64` rồi làm tròn ở bước cuối cho nhanh, mà phải dùng `math/big.Rat`?"
> **Trả lời:** Kiểu `float64` chuẩn IEEE 754 lưu trữ số học ở hệ nhị phân, dẫn đến các sai số làm tròn không thể kiểm soát (ví dụ $0.1 + 0.2 = 0.30000000000000004$). Khi chia một hóa đơn qua 20 món ăn với tỷ lệ trọng số lẻ (ví dụ 3 người chia một đĩa 100.000đ thành $33333.333...$đ), việc cộng dồn float sẽ tạo ra sai số lũy kế. Sử dụng `big.Rat` lưu trữ tỷ lệ phân số chính xác tuyệt đối giúp chúng em bảo toàn tính toàn vẹn tài chính cho đến tận bước làm tròn duy nhất cuối cùng.

#### 5. "Cơ chế phá vỡ thế hòa (Tie-Breaking) trong thuật toán Hamilton ở `allocation.go` hoạt động ra sao?"
> **Trả lời:** Tại dòng 223 của `allocation.go`, chúng em dùng `sort.SliceStable`. Khi phần dư thập phân của 2 thành viên bằng nhau chằn chặn, thuật toán sẽ so sánh `bytes.Compare(UUID_A[:], UUID_B[:]) < 0`. Do chuỗi byte của UUID là duy nhất và cố định, thứ tự ưu tiên nhận 1 đồng lẻ là hoàn toàn **xác định (Deterministic)**, không phụ thuộc vào thứ tự ngẫu nhiên của Go map hay thời gian chạy.

#### 6. "Nếu một thành viên được mã giảm giá quá lớn khiến tiền phải trả của họ bị âm thì thuật toán xử lý thế nào?"
> **Trả lời:** Tại dòng 180 của `allocation.go` (Discount Excess Reconciliation), phần tiền nợ của thành viên đó được chặn sàn ở mức 0đ (không bị âm). Phần giảm giá dư thừa chưa dùng hết được chuyển dồn cho người trả tiền trước (**Creditor**) hấp thụ. Nếu tổng giảm giá quá lớn khiến ngay cả Creditor cũng bị âm tiền, hệ thống từ chối hóa đơn và trả về lỗi `domain.ErrDiscountNotAllocatable`.

#### 7. "Làm sao em ngăn chặn được việc 2 người cùng chỉnh sửa hoặc cùng bấm Chốt hóa đơn một lúc?"
> **Trả lời:** Hệ thống áp dụng 2 tầng bảo vệ:
> 1. **Optimistic Concurrency Control (OCC):** Khi client gửi request chốt bill, bắt buộc phải truyền `expectedVersion`. Nếu version trong DB đã bị tăng lên bởi thao tác trước đó, lệnh sẽ trả về `409 Conflict`.
> 2. **Pessimistic Row Locking (`FOR UPDATE`):** Trong repository SQL (`bill.sql`), câu lệnh `SELECT ... FOR UPDATE` khóa chặt dòng dữ liệu của hóa đơn trong PostgreSQL transaction, buộc các request đồng thời khác phải xếp hàng chờ.

#### 8. "Tại sao trong bảng `bill_shares` lại lưu cả `rounding_adjustment`?"
> **Trả lời:** Thuật toán phân bổ phải có tính **giải trình được (Explainability)**. `rounding_adjustment` ghi nhận chính xác thành viên nào phải chịu $+1$đ hoặc $-1$đ do làm tròn lẻ, giúp giải thích minh bạch với người dùng tại sao tổng tiền của họ lại chênh 1đ so với công thức lý thuyết.

#### 9. "Một hóa đơn đã Finalize rồi thì có sửa được nữa không? Tại sao?"
> **Trả lời:** Tuyệt đối không ạ. Tại `service.go` dòng 1027, nếu `bill.Status == BillStatusFinalized`, hệ thống trả về lỗi `domain.ErrBillImmutable`. Khi bill đã chốt, nó đã sinh ra các bản ghi công nợ (`debts`) và người khác có thể đã chuyển khoản thanh toán. Việc sửa đổi bill đã chốt sẽ phá vỡ toàn bộ sổ sách kế toán. Nếu có sai sót, người dùng buộc phải tạo giao dịch điều chỉnh hoặc Void hóa đơn.

---

### 🔹 VỀ MODULE NOTIFICATION & RIVER QUEUE:
#### 10. "Tại sao dùng PostgreSQL River Queue mà không dùng Redis Pub/Sub hay RabbitMQ?"
> **Trả lời:** Lý do quan trọng nhất là **Transactional Enqueue (ACID)**. Với River, lệnh đẩy job gửi thông báo nằm trong cùng một PostgreSQL Transaction (`pgx.Tx`) với lệnh lưu bill. Nếu nghiệp vụ lưu bill bị rollback, job gửi thông báo cũng tự hủy theo. Dùng Redis bên ngoài sẽ gặp bài toán **Dual-Write**: nếu DB rollback mà Redis đã nhận job thì người dùng sẽ nhận thông báo nợ của một hóa đơn không hề tồn tại (**Ghost Notification**).

#### 11. "Thin Job Pattern trong `send_notification.go` mang lại lợi ích gì về mặt hiệu năng?"
> **Trả lời:** Struct `NotificationJobArgs` chỉ lưu đúng chuỗi `notification_id`. Nó giúp:
> 1. Bảng `river_job` trong PostgreSQL cực kỳ gọn nhẹ, tối ưu bộ đệm RAM và chỉ mục B-Tree.
> 2. Tránh gửi thông tin cũ (Stale Data): Worker khi chạy sẽ query lại bảng `notifications` và `sessions`, lấy được tiêu đề, nội dung và Token thiết bị mới nhất ở thời điểm thực thi.

#### 12. "Nếu người dùng gỡ cài đặt ứng dụng (Uninstall App) thì hệ thống xử lý push notification như thế nào?"
> **Trả lời:** Tại dòng 92 của `send_notification.go`, khi gọi Firebase FCM bị lỗi, worker dùng hàm `fcm.IsInvalidTokenError(sendErr)` để kiểm tra. Nếu Firebase báo token không còn tồn tại (`UNREGISTERED`), worker lập tức gọi `w.repo.ClearFCMToken()` để set `fcm_token = NULL` trong DB và kết thúc job an toàn, không retry nữa để tiết kiệm tài nguyên.

#### 13. "Nếu Firebase FCM bị rớt mạng tạm thời thì sao?"
> **Trả lời:** Worker sẽ trả về lỗi `sendErr`. River Queue sẽ bắt lấy lỗi này và kích hoạt cơ chế **Exponential Backoff** tự động thử lại sau $1\text{s}, 2\text{s}, 4\text{s}, 8\text{s},...$ cho đến khi thành công hoặc đạt giới hạn số lần thử tối đa (`MaxAttempts`).

#### 14. "Làm sao Flutter App biết mở màn hình nào khi người dùng chạm vào Push Notification?"
> **Trả lời:** Trong hàm `Work()`, worker nạp trường `notif.Payload` và gán `data["type"] = notif.Type` cùng các entity ID (`bill_id`, `group_id`). Phía Flutter, Router lắng nghe `FirebaseMessaging.onMessageOpenedApp`, đọc trường `data["type"]` để kích hoạt điều hướng Deep Link trực diện đến màn hình chi tiết bill hoặc mở pop-up mã VietQR.

#### 15. "Nếu một thành viên trong nhóm bị khóa tài khoản hoặc xóa tài khoản thì thông báo có bị crash worker không?"
> **Trả lời:** Tại dòng 62 của `send_notification.go`, nếu hàm `GetNotificationByID` trả về `domain.ErrNotificationNotFound`, worker coi đây là trường hợp bản ghi đã bị hủy hợp lệ, trả về `nil` để hoàn tất job trong im lặng, không ghi log lỗi nghiêm trọng và không làm gián đoạn worker.
