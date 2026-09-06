# 🛡️ BÁO CÁO CHUYÊN SÂU KIẾN TRÚC VÀ NGHIỆP VỤ LÕI: OCR, CHIA BILL & THÔNG BÁO (PAYSPLIT)

> **Tài liệu chuẩn bị cho buổi phản biện và báo cáo kỹ thuật với Mentor.**  
> **Phạm vi phụ trách:** Module 1: Xử lý OCR Hóa Đơn • Module 2: Thuật Toán Phân Bổ & Chia Tiền • Module 3: Hệ Thống Thông Báo & Worker Hàng Đợi Ngầm.

---

## MỤC LỤC TỔNG QUAN

1. [TỔNG QUAN VỊ THẾ & TRÁCH NHIỆM HỆ THỐNG](#1-tổng-quan-vị-thế--trách-nhiệm-hệ-thống)
2. [MODULE 1: OCR PROCESSING PIPELINE (TRÍCH XUẤT HÓA ĐƠN)](#2-module-1-ocr-processing-pipeline-trích-xuất-hóa-đơn)
   - 2.1. Bản chất kiến trúc & Luồng xử lý dữ liệu bất đồng bộ
   - 2.2. Các phương án kiến trúc đã cân nhắc (Trade-off Analysis)
   - 2.3. Quy trình chuẩn hóa & Xử lý biên (Normalizer & Edge Cases)
   - 2.4. Bảo mật dữ liệu hình ảnh nhạy cảm
   - 2.5. Bộ câu hỏi Mentor dự kiến & Câu trả lời chuẩn mực
3. [MODULE 2: THUẬT TOÁN CHIA TIỀN & QUẢN LÝ VÒNG ĐỜI BILL](#3-module-2-thuật-toán-chia-tiền--quản-lý-vòng-đời-bill)
   - 3.1. Bài toán số học tài chính & Nguyên tắc bất biến
   - 3.2. Lịch sử tiến hóa thuật toán (The Evolution Story)
   - 3.3. Công thức toán học & Thuật toán Hamilton chi tiết
   - 3.4. Vòng đời hóa đơn, Khóa một chiều & Batch Processing
   - 3.5. Xử lý tranh chấp dữ liệu (Concurrency & Idempotency)
   - 3.6. Bộ câu hỏi Mentor dự kiến & Câu trả lời chuẩn mực
4. [MODULE 3: NOTIFICATION & BACKGROUND WORKER (RIVER QUEUE)](#4-module-3-notification--background-worker-river-queue)
   - 4.1. Kiến trúc hàng đợi dựa trên PostgreSQL (PostgreSQL-backed Queue)
   - 4.2. Bài toán Dual-Write & Giải pháp Transactional Enqueue
   - 4.3. Mô hình Thin Job Pattern & Idempotent Worker
   - 4.4. Tích hợp Firebase Cloud Messaging (FCM) & Xử lý lỗi
   - 4.5. Cơ chế Deep Link & Đồng bộ đa nền tảng
   - 4.6. Bộ câu hỏi Mentor dự kiến & Câu trả lời chuẩn mực
5. [TỔNG HỢP CHIẾN LƯỢC TRÌNH BÀY & TÂM THẾ BẢO VỆ ĐỒ ÁN](#5-tổng-hợp-chiến-lược-trình-bày--tâm-thế-bảo-vệ-đồ-án)

---

# 1. TỔNG QUAN VỊ THẾ & TRÁCH NHIỆM HỆ THỐNG

Trong hệ sinh thái **PaySplit**, ba module bạn phụ trách tạo thành **chuỗi giá trị cốt lõi (Core Value Chain)** của toàn bộ sản phẩm:

```text
[Hình ảnh hóa đơn] 
       │
       ▼ (Module 1: OCR Pipeline)
[Dữ liệu món & Tiền tệ đã chuẩn hóa] 
       │
       ▼ (Module 2: Bill Allocation Engine)
[Công nợ chính xác 100% từng đồng VND - Bất biến] 
       │
       ▼ (Module 3: Transactional Notification)
[Thông báo nhắc nợ / Deep Link thanh toán tức thì]
```

* **Module 1 (OCR):** Tiếp nhận dữ liệu phi cấu trúc từ thế giới thực (ảnh chụp hóa đơn), lọc nhiễu, biến nó thành cấu trúc dữ liệu tài chính có thể kiểm toán.
* **Module 2 (Chia Bill):** "Trái tim" nghiệp vụ. Tính toán số liệu công nợ với độ chính xác tuyệt đối (Zero rounding error), quản lý trạng thái bất biến và chống gian lận.
* **Module 3 (Thông báo):** "Hệ thần kinh". Đảm bảo kết quả chia tiền được truyền tải tin cậy đến từng thiết bị di động mà không làm nghẽn luồng HTTP chính và không bao giờ báo sai lệch.

---

# 2. MODULE 1: OCR PROCESSING PIPELINE (TRÍCH XUẤT HÓA ĐƠN)

## 2.1. Bản chất kiến trúc & Luồng xử lý dữ liệu bất đồng bộ

Hóa đơn thực tế tại Việt Nam cực kỳ phức tạp: in nhiệt mờ, dập ghim, viết tay, có chiết khấu dòng, phụ phí dịch vụ và VAT gộp. Nếu xử lý đồng bộ trong chu kỳ HTTP Request, hệ thống sẽ gặp các rủi ro chết người: **Client Timeout (3G/4G chập chờn)**, **giữ Connection Pool quá lâu**, và **nguy cơ ghi đè dữ liệu nếu user đang chỉnh sửa tay**.

### Luồng xử lý chuẩn (Durable Candidate Pattern):
1. **Client tải ảnh:** Tải ảnh lên private storage (Cloudinary) thông qua backend, nhận về asset metadata.
2. **Enqueue Job:** Backend đẩy một job phân tích ảnh vào River Queue và trả về `202 Accepted` ngay lập tức cho mobile app.
3. **Worker xử lý:** Worker bốc job, gọi provider AI đa phương thức (**LlamaExtract** qua `OCRProvider` interface).
4. **Chuẩn hóa (Normalization):** Dữ liệu JSON thô từ AI được đưa qua bộ lọc `Normalizer` để kiểm tra tính toàn vẹn và sửa lỗi logic.
5. **Lưu Candidate Staging:** Kết quả được lưu dưới dạng `OCRCandidate` (trạng thái chờ duyệt), liên kết với Bill version hiện tại.
6. **Explicit User Review:** Người dùng buộc phải xem lại màn hình so sánh (Review Screen). Chỉ khi người dùng bấm "Áp dụng", candidate mới được ghi vào dữ liệu chính của hóa đơn.

---

## 2.2. Các phương án kiến trúc đã cân nhắc (Trade-off Analysis)

Khi mentor hỏi: *"Tại sao không gọi OCR trực tiếp trong API upload bill cho nhanh?"*, bạn hãy trả lời dựa trên bảng so sánh kỹ thuật này:

| Tiêu chí | Phương án 1: Gọi OCR đồng bộ (Synchronous) | Phương án 2: Durable Candidate + Worker (Được chọn) | Phương án 3: Dùng giải pháp SaaS trọn gói |
| :--- | :--- | :--- | :--- |
| **Độ trễ API** | 5s – 15s (rất cao, nguy cơ timeout trên mobile). | **< 150ms** (Trả về `202 Accepted` tức thì). | Phụ thuộc vào third-party webhook. |
| **Khả năng chịu lỗi** | Nếu mạng rớt giữa chừng, request chết, client retry làm nhân đôi chi phí API AI. | **River Queue tự động retry** với Exponential Backoff; bảo toàn trạng thái. | Khó kiểm soát retry logic khi webhook lỗi. |
| **Xung đột sửa đổi** | Dễ ghi đè nếu người dùng chỉnh sửa tay trong lúc OCR đang chạy. | **Version Check & Candidate Staging**: Không ghi đè trực tiếp lên bill đang sửa. | Dữ liệu bị phân mảnh giữa 2 hệ thống. |
| **Độ phức tạp** | Rất thấp (vài dòng code). | Trung bình (cần worker, staging table, state machine). | Rất cao (xử lý webhook, bảo mật callback). |

---

## 2.3. Quy trình chuẩn hóa & Xử lý biên (Normalizer & Edge Cases)

Tầng Normalizer (`internal/platform/ocr/llamaextract/normalizer.go`) là chốt chặn kỹ thuật quan trọng nhất để ngăn chặn rác dữ liệu từ AI tràn vào cơ sở dữ liệu tài chính:

### 1. Xử lý dòng khuyến mãi theo món (Item-level Discount):
* **Vấn đề:** Nhiều hóa đơn in dòng món ăn ở trên, dòng ngay dưới là `-20.000đ KM` hoặc `Chiết khấu`.
* **Giải pháp của PaySplit:**
  * Thuật toán nhận diện các marker: `"KM"`, `"Khuyến mãi"`, `"Giảm giá"`, `"Chiết khấu"` hoặc `line_total < 0`.
  * **Case A (Bình thường):** Gộp giá trị giảm trực tiếp vào món liền trước, giảm `line_total` của món đó.
  * **Case B (Orphan Discount):** Nếu dòng khuyến mãi nằm ngay đầu danh sách (không có món liền trước), nó được tự động chuyển thành **Giảm giá chung toàn bill (`discount`)** và phát sinh cảnh báo `WarningOCROrphanItemDiscount`.
  * **Case C (Vượt giá gốc):** Nếu tiền khuyến mãi lớn hơn giá trị món ăn, giá món được đưa về 0, phần chênh lệch dôi dư được chuyển vào giảm giá chung toàn bill.

### 2. Xử lý ngày tháng mập mờ (Ambiguous Date Parsing):
* **Vấn đề:** Định dạng `04/05/2026` không thể biết chắc chắn là ngày 4 tháng 5 hay ngày 5 tháng 4.
* **Giải pháp:** Đối chiếu hai biểu thức chính quy (`dateRegexDMY` vs `dateRegexYMD`). Nếu cả ngày và tháng đều $\le 12$, hệ thống ưu tiên chuẩn hóa theo văn hóa hóa đơn Việt Nam (`DD/MM/YYYY`), đồng thời ghi nhận cờ `WarningOCRDateAmbiguous` để UI hiển thị viền vàng cảnh báo người dùng kiểm tra lại.

### 3. Đối soát số học (Reconciliation Check):
* Hệ thống tự động tính toán: $\text{CalculatedTotal} = \sum \text{ItemTotals} + \text{ServiceCharge} + \text{VAT} - \text{Discount}$.
* Nếu chênh lệch với `total` ghi trên hóa đơn, hệ thống **không tự ý sửa tiền** mà gắn cờ cảnh báo bất đối soát, yêu cầu người dùng xác nhận lại trước khi chốt.

---

## 2.4. Bảo mật dữ liệu hình ảnh nhạy cảm

* **Nguyên tắc bảo vệ thông tin tài chính (Financial Privacy):** Hóa đơn có thể chứa địa chỉ nhà, tên công ty, thói quen ăn uống/sinh hoạt cá nhân.
* **Cơ chế lưu trữ:** Ảnh hóa đơn được lưu dưới dạng **Private Asset** trên Cloudinary (không cho phép truy cập public qua URL thông thường).
* **Truy xuất qua Signed URL:** Khi ứng dụng cần hiển thị ảnh hóa đơn để người dùng đối chiếu, Backend sinh một URL có chữ ký số (HMAC Signed URL) với thời gian hết hạn nghiêm ngặt (**TTL 5 phút**). Sau 5 phút, URL vô hiệu lực, ngăn chặn rò rỉ liên kết.

---

## 2.5. Bộ câu hỏi Mentor dự kiến & Câu trả lời chuẩn mực

### Q1: *"Nếu LlamaExtract bị nghẽn mạng hoặc sập, hệ thống của bạn ứng phó thế nào?"*
> **Trả lời:**  
> "Kiến trúc của chúng em được thiết kế theo nguyên lý **Fail-safe & Decoupled**. LlamaExtract được trừu tượng hóa qua `OCRProvider` interface. Quá trình xử lý chạy ngầm qua River Queue:
> 1. Khi có lỗi mạng tạm thời, River tự động retry với Exponential Backoff (tối đa 3 lần).
> 2. Nếu provider sập hoàn toàn, job được đánh dấu `failed`, hệ thống gửi thông báo cho người dùng và cung cấp tùy chọn nhập liệu thủ công.
> 3. Do thiết kế hướng interface, chúng em có thể chuyển đổi sang Google Vision OCR hoặc AWS Textract chỉ bằng việc viết một Adapter mới mà không cần sửa bất kỳ dòng code nào trong `usecase` hay `domain`."

### Q2: *"Tại sao không tự host model OCR (Tesseract / PaddleOCR) mà lại dùng Cloud AI?"*
> **Trả lời:**  
> "Hóa đơn tiếng Việt có tính đa dạng cực cao (viết tay, mờ, font chữ lạ). Các thư viện OCR truyền thống như Tesseract chỉ làm tốt việc nhận diện ký tự (Text Extraction), nhưng không có khả năng hiểu ngữ nghĩa (Semantic Understanding) để phân biệt đâu là tên món, đâu là đơn giá, dòng nào là phụ phí hay chiết khấu. Việc dùng Multimodal LLM (như Llama Vision) mang lại khả năng bóc tách cấu trúc JSON hoàn chỉnh, tiết kiệm hàng tháng huấn luyện mô hình và phù hợp với quy mô MVP."

---

# 3. MODULE 2: THUẬT TOÁN CHIA TIỀN & QUẢN LÝ VÒNG ĐỜI BILL

## 3.1. Bài toán số học tài chính & Nguyên tắc bất biến

Trong phần mềm tài chính, sai số dù chỉ **1 đồng** cũng có thể dẫn đến lệch sổ sách, mất lòng tin người dùng và lỗi toàn vẹn cơ sở dữ liệu.

### 4 Nguyên tắc bất biến (Financial Invariants):
1. **Zero Float Rule:** Tuyệt đối không dùng kiểu số thực (`float32`, `float64`) để tính toán tiền tệ. Phải dùng số nguyên `int64` (đơn vị VND) và phân số chính xác vô hạn (`math/big.Rat`).
2. **Total Conservation Invariant:** Tổng số tiền mọi người phải trả sau khi làm tròn **bắt buộc phải bằng đúng 100% tổng tiền trên hóa đơn**:
   $$\sum_{m \in \text{Members}} \text{FinalAmount}_m \equiv \text{BillTotal}$$
3. **No Phantom Debt (Không công nợ ma):** Không một thành viên nào có số tiền phải trả bị âm ($\text{FinalAmount}_m \ge 0$).
4. **Immutability After Finalize (Khóa bất biến):** Khi hóa đơn đã chốt (Finalized), dữ liệu phân bổ trở thành snapshot lịch sử kế toán, không bao giờ được phép tính toán lại hay chỉnh sửa.

---

## 3.2. Lịch sử tiến hóa thuật toán (The Evolution Story)
*(Điểm sáng giúp bạn ghi điểm tuyệt đối trước Mentor về tư duy kỹ thuật sâu sắc)*

Nếu Mentor hỏi: *"Thuật toán chia tiền của bạn hoạt động thế nào?"*, hãy tự tin kể lại **3 giai đoạn tiến hóa** mà bạn đã trải qua để đưa ra phiên bản hiện tại:

```text
[Giai đoạn 1: Naive Hamilton] 
       │ (Phát hiện lỗi: Thành viên âm tiền bị ép về 0 làm tổng tiền bị hụt)
       ▼
[Giai đoạn 2: Floor + Creditor Absorption] 
       │ (Phát hiện lỗi: Làm tròn sàn từng món sớm gây thất thoát lũy kế)
       ▼
[Giai đoạn 3: Exact Aggregate + Deterministic Hamilton] (Phiên bản Production)
```

1. **Giai đoạn 1 (Naive Hamilton):**
   * *Cách làm:* Chia từng thành viên, nếu ai bị âm tiền (do giảm giá lớn) thì gán bằng 0.
   * *Lỗ hổng:* Khoản tiền bị gán về 0 biến mất khỏi hệ thống, làm cho $\sum \text{FinalAmount} < \text{BillTotal}$ (lệch tiền toàn hóa đơn).
2. **Giai đoạn 2 (Creditor Absorption - Ngày 20/08/2026):**
   * *Cách làm:* Làm tròn sàn (`floor`) phần tiền của mọi thành viên. Người trả tiền trước (Creditor) sẽ gánh toàn bộ phần tiền lẻ còn thừa.
   * *Lỗ hổng:* Gây ra lỗi **làm tròn sớm lũy kế (Cumulative Early Rounding)**. Ví dụ: 6 người chia 2 món 400.000đ và 800.000đ. Làm tròn sàn từng món khiến 5 người kia mỗi người bị mất 1đ mỗi món, dồn cho Creditor hưởng lợi bất công tới 6đ dù về mặt lý thuyết họ phải trả số tiền nguyên chẵn.
3. **Giai đoạn 3 (Production - Ngày 27/08/2026 - Bản hiện tại):**
   * *Giải pháp:* **Cộng dồn phân số chính xác (`big.Rat`) của tất cả các món lại trước**, chỉ làm tròn duy nhất 1 lần ở bước cuối cùng bằng **Thuật toán phần dư lớn nhất (Hamilton Method)** với cơ chế phá vỡ thế hòa (Tie-breaking) dựa trên byte UUID.

---

## 3.3. Công thức toán học & Thuật toán Hamilton chi tiết

Toàn bộ logic nằm tại `internal/modules/bill/usecase/allocation.go`:

### Bước 1: Tính tiền món chính xác (Exact Item Share)
Với mỗi món $i$ có thành tiền $\text{LineTotal}_i$, thành viên $m$ có trọng số ăn là $w_{m, i}$:
$$\text{ExactItemShare}_{m, i} = \text{LineTotal}_i \times \frac{w_{m, i}}{\sum_{k} w_{k, i}} \quad (\text{dùng } big.Rat)$$
Tổng tiền món của thành viên $m$:
$$\text{ItemSubtotal}_m = \sum_{i} \text{ExactItemShare}_{m, i}$$

### Bước 2: Phân bổ phụ phí, VAT và Giảm giá theo tỷ lệ tiêu dùng
Các chi phí chung được phân bổ theo tỷ lệ tiền món mà thành viên đó đã sử dụng:
$$\text{ServiceShare}_m = \text{TotalService} \times \frac{\text{ItemSubtotal}_m}{\text{ItemsTotal}}$$
$$\text{VATShare}_m = \text{TotalVAT} \times \frac{\text{ItemSubtotal}_m}{\text{ItemsTotal}}$$
$$\text{DiscountShare}_m = \text{TotalDiscount} \times \frac{\text{ItemSubtotal}_m}{\text{ItemsTotal}}$$

### Bước 3: Điều tiết giảm giá dôi dư (Discount Excess Reconciliation)
Nếu một người ăn ít nhưng được hưởng giảm giá vượt quá tổng nghĩa vụ ($\text{DiscountShare}_m > \text{ItemSubtotal}_m + \text{ServiceShare}_m + \text{VATShare}_m$):
* Khoản giảm giá của họ được chặn lại bằng đúng tổng nghĩa vụ (để họ trả 0đ, không bị âm tiền).
* **Phần giảm giá dư thừa được chuyển giao cho Creditor** hấp thụ. Nếu việc hấp thụ này đẩy tổng tiền của Creditor xuống dưới 0, hệ thống từ chối hóa đơn và báo lỗi `ErrDiscountNotAllocatable`.

### Bước 4: Lấy sàn và Thuật toán Hamilton phân bổ phần dư
1. Tính số tiền danh định chính xác: $\text{ExactFinal}_m = \text{ItemSubtotal}_m + \text{Service}_m + \text{VAT}_m - \text{Discount}_m$.
2. Lấy phần nguyên VND: $\text{BaseAmount}_m = \lfloor \text{ExactFinal}_m \rfloor$.
3. Tính phần dư còn thiếu:
   $$\text{RemainingVND} = \text{BillTotal} - \sum_{m} \text{BaseAmount}_m \quad (0 \le \text{RemainingVND} < N)$$
4. **Xếp hạng phân bổ phần dư (Largest Remainder):**
   * Sắp xếp danh sách thành viên theo **phần thập phân giảm dần** ($\text{FractionalPart}_m$).
   * **Quy tắc phá vỡ thế hòa (Tie-Breaking):** Nếu hai người có phần thập phân bằng nhau chằn chặn, sắp xếp theo **thứ tự byte của UUID tăng dần** (`bytes.Compare(UUID_i, UUID_j) < 0`). Điều này đảm bảo thuật toán có tính **nội tại xác định (100% Deterministic)** trên mọi môi trường chạy.
   * Lấy top `RemainingVND` người đầu bảng, mỗi người được cộng đúng **+1 VND**.

---

## 3.4. Vòng đời hóa đơn, Khóa một chiều & Batch Processing

Logic chốt bill và xử lý hàng loạt (`bill_close.go`) tuân thủ nghiêm ngặt mô hình máy trạng thái:

```text
[Draft] ──(Tạo & Sửa món)──► [Draft Locked] ──(Finalize Bill)──► [Finalized] ──► [Settled]
   │                                                                 │
   └───────────────(Void Bill / Hủy bỏ)──────────────────────────────┘
```

1. **Khóa gửi hóa đơn một chiều (`LockSubmissions`):**
   * Khi nhóm chuẩn bị thanh toán cuối chuyến đi, Captain kích hoạt `LockSubmissions`.
   * Thao tác này có tính **Idempotent**: Nhóm đã khóa vẫn trả về `200 OK` kèm timestamp gốc mà không sinh thêm log rác. Sau khi khóa, không ai trong nhóm được tạo thêm bill mới.
2. **Batch Finalization (`StartBulkFinalize`):**
   * Cho phép Captain chốt toàn bộ hàng chục bill trong nhóm cùng lúc.
   * Tạo một `FinalizeBatch` mang UUIDv7. Mọi bill chưa chốt được đóng gói và đẩy vào River Queue để các worker xử lý song song độc lập.
   * Sử dụng mã phản hồi `202 Accepted` kèm ID của batch để mobile client theo dõi tiến độ qua polling hoặc SSE.

---

## 3.5. Xử lý tranh chấp dữ liệu (Concurrency & Idempotency)

* **Chống đúp request (Idempotency Key):**
  * Mọi request chốt bill nhạy cảm đều đi kèm header `Idempotency-Key`.
  * Backend tính mã băm `SHA-256(Idempotency-Key + Body)` và kiểm tra bảng `idempotency_keys` trong transaction.
  * Nếu client bấm 2 lần liên tục do lag mạng, request thứ 2 sẽ nhận lại đúng kết quả đã lưu mà không bị tính toán hay sinh nợ hai lần.
* **Optimistic Concurrency Control (OCC):**
  * Hóa đơn có cột `version`. Mọi thao tác update đều có điều kiện `WHERE id = $1 AND version = $2`. Nếu version không khớp (do người khác đã sửa trước), lệnh cập nhật bị từ chối với lỗi `ErrOptimisticLockConflict`.

---

## 3.6. Bộ câu hỏi Mentor dự kiến & Câu trả lời chuẩn mực

### Q1: *"Tại sao phải dùng math/big phức tạp mà không dùng float64 rồi math.Round()?"*
> **Trả lời:**  
> "Trong chuẩn IEEE 754, số thực dấu phẩy động (`float64`) không thể biểu diễn chính xác các phân số thập phân (ví dụ: $0.1 + 0.2 = 0.30000000000000004$). Khi thực hiện phép chia hóa đơn qua nhiều món và nhiều người, sai số tích lũy sẽ làm tổng tiền của các thành viên bị lệch so với hóa đơn gốc. Với hệ thống tài chính, sự chênh lệch dù chỉ 1 đồng cũng phá vỡ ràng buộc ACID và gây tranh cãi giữa người dùng. Phân số chính xác `big.Rat` triệt tiêu hoàn toàn sai số làm tròn trung gian."

### Q2: *"Nếu hai thành viên có phần dư thập phân giống hệt nhau, ai sẽ chịu trả thêm 1 đồng?"*
> **Trả lời:**  
> "Hệ thống của em sử dụng cơ chế **Deterministic Tie-Breaking**. Khi hai phần dư bằng nhau, thuật toán so sánh thứ tự từ điển của chuỗi byte định danh `UUID`. Vì UUID là cố định và duy nhất, kết quả tính toán sẽ luôn luôn đồng nhất 100% trong mọi lần chạy kiểm toán, loại bỏ hoàn toàn yếu tố ngẫu nhiên (random) trong hệ thống sổ sách."

---

# 4. MODULE 3: NOTIFICATION & BACKGROUND WORKER (RIVER QUEUE)

## 4.1. Kiến trúc hàng đợi dựa trên PostgreSQL (PostgreSQL-backed Queue)

Thay vì dựng một cụm Redis hoặc RabbitMQ riêng biệt, PaySplit lựa chọn **River Queue** (`github.com/riverqueue/river`) chạy trực tiếp trên PostgreSQL 18 thông qua driver native `pgx/v5`.

```text
[HTTP Request Handler] 
       │
       ▼ (Bắt đầu PostgreSQL Transaction: pgx.Tx)
1. Ghi dữ liệu nghiệp vụ (Lưu Bill / Gạch nợ / Đổi trạng thái)
2. Ghi bản ghi In-app Notification vào bảng 'notifications'
3. Enqueue Job gửi push notification vào bảng 'river_job' (InsertTx)
       │
       ▼ (COMMIT TRANSACTION)
       │
   [PostgreSQL Engine] ──(LISTEN/NOTIFY)──► [River Background Worker]
                                                    │
                                                    ▼ Gọi Firebase FCM API
                                            [Mobile Device Push]
```

---

## 4.2. Bài toán Dual-Write & Giải pháp Transactional Enqueue

### Vấn đề kinh điển của hệ thống phân tán (The Dual-Write Dilemma):
Nếu dùng Redis/RabbitMQ tách rời:
* **Kịch bản lỗi A:** Lưu dữ liệu vào PostgreSQL thành công $\rightarrow$ Gửi job vào Redis bị timeout/rớt mạng $\rightarrow$ Người dùng không bao giờ nhận được thông báo về khoản nợ.
* **Kịch bản lỗi B:** Gửi job vào Redis trước $\rightarrow$ Commit dữ liệu PostgreSQL bị lỗi rollback $\rightarrow$ **Ghost Notification!** Người dùng nhận được thông báo nợ nhưng mở app lên lại không thấy hóa đơn đâu.

### Giải pháp của PaySplit: Transactional Enqueue
* Nhờ River Queue lưu job ngay trong bảng của PostgreSQL, hàm `s.enqueuer.EnqueueNotificationTx(ctx, tx, notifID)` thực thi lệnh chèn job **trong cùng một Transaction (`pgx.Tx`)** với dữ liệu nghiệp vụ.
* **Cam kết ACID tuyệt đối:** Dữ liệu hóa đơn và job thông báo cùng được lưu (Commit) hoặc cùng bị hủy (Rollback). Loại bỏ 100% rủi ro thông báo ma.

---

## 4.3. Mô hình Thin Job Pattern & Idempotent Worker

File `internal/modules/notification/jobs/send_notification.go` tuân theo mẫu thiết kế **Thin Job (Job Gọn)**:

```go
type NotificationJobArgs struct {
    NotificationID string `json:"notification_id"`
}
```

* **Tại sao Job chỉ chứa mỗi `NotificationID` mà không chứa Title, Body, FCM Token?**
  1. **Tránh phình to dung lượng hàng đợi:** Bảng `river_job` giữ kích thước siêu nhỏ, tối ưu bộ đệm RAM của PostgreSQL.
  2. **Chống dữ liệu cũ (Stale Data):** Khi worker bốc job lên, nó truy vấn lại bản ghi mới nhất từ bảng `notifications`. Nếu trước đó thông báo đã được hủy hoặc user đã đổi token, worker sẽ nhận được trạng thái mới nhất.
  3. **Idempotency Handle:** `NotificationID` đóng vai trò là khóa định danh duy nhất để tránh gửi trùng thông báo khi có sự cố retry.

---

## 4.4. Tích hợp Firebase Cloud Messaging (FCM) & Xử lý lỗi

Worker xử lý phân loại lỗi từ Firebase cực kỳ chặt chẽ:

```go
if sendErr := w.pushNotifier.SendToDevice(ctx, token, msg); sendErr != nil {
    // 1. Token rác / App đã bị gỡ
    if fcm.IsInvalidTokenError(sendErr) {
        _ = w.repo.ClearFCMToken(ctx, notif.UserID, token)
        return nil // Hoàn tất job an toàn, không retry
    }
    // 2. Lỗi cấu trúc message (Lỗi logic code)
    if fcm.IsInvalidMessageError(sendErr) {
        log.Printf("Lỗi message payload: %v", sendErr)
        return nil // Ghi log kiểm tra, không retry vô nghĩa
    }
    // 3. Lỗi mạng / Firebase timeout tạm thời
    return sendErr // Trả về lỗi để River Queue tự động retry với Exponential Backoff!
}
```

* **Dọn dẹp token rác (Dead Token Pruning):** Khi người dùng gỡ app, Firebase trả về lỗi `UNREGISTERED`. Hệ thống tự động xóa token khỏi DB, tiết kiệm tài nguyên mạng cho những lần gửi sau.
* **Exponential Backoff:** Nếu mạng bị chập chờn, River Queue sẽ tự động thử lại sau 1s, 2s, 4s, 8s,... tránh làm quá tải đường truyền.

---

## 4.5. Cơ chế Deep Link & Đồng bộ đa nền tảng

Mỗi thông báo đẩy gửi qua FCM không chỉ có tiêu đề và nội dung hiển thị, mà luôn kèm theo trường dữ liệu cấu trúc (**Data Payload**):
* `type`: Định danh sự kiện (`payment_reminder`, `new_bill`, `payment_confirmed`).
* `bill_id`, `group_id`: Định danh thực thể.
* **Trải nghiệm phía Flutter App:** Khi người dùng chạm vào thông báo trên thanh trạng thái màn hình khóa, Flutter `go_router` đọc `data["type"]` và các ID liên quan để **điều hướng trực diện đến đúng màn hình hóa đơn hoặc mở pop-up quét mã VietQR chuyển khoản ngay lập tức**.

---

## 4.6. Bộ câu hỏi Mentor dự kiến & Câu trả lời chuẩn mực

### Q1: *"Dùng PostgreSQL làm hàng đợi có làm chậm Database của hệ thống không?"*
> **Trả lời:**  
> "Đối với quy mô hiện tại và trung hạn của PaySplit (vài nghìn giao dịch mỗi ngày), tải I/O của hàng đợi là không đáng kể so với năng lực xử lý của PostgreSQL 18. River Queue sử dụng bảng được index tối ưu, hỗ trợ cơ chế tự động dọn dẹp các job đã hoàn thành (`job retention cleanup`) và tận dụng cơ chế `LISTEN/NOTIFY` để đánh thức worker thay vì liên tục chạy vòng lặp `POLL` gây tốn CPU. Lợi ích lớn nhất là tính toàn vẹn dữ liệu (ACID Transactional Enqueue) hoàn toàn vượt trội so với rủi ro phải vận hành thêm cụm Redis."

### Q2: *"Nếu server bị sập nguồn (SIGKILL / Out-of-memory) lúc worker đang gửi thông báo thì sao?"*
> **Trả lời:**  
> "River Queue áp dụng cơ chế **At-least-once Delivery** với thời gian sống của khóa (Job Rescue / Lease Mechanism). Nếu worker bị sập khi chưa kịp xác nhận hoàn thành (`job completion`), sau khi server khởi động lại, River sẽ phát hiện job bị quá hạn thuê (stuck job) và tự động cấp phát lại cho worker khác xử lý. Kết hợp với việc lưu trữ In-app notification trước, người dùng không bao giờ bị mất lịch sử thông báo."

---

# 5. TỔNG HỢP CHIẾN LƯỢC TRÌNH BÀY & TÂM THẾ BẢO VỆ ĐỒ ÁN

### 🎯 Chiến thuật 3 bước khi trả lời câu hỏi của Mentor:
1. **Bước 1: Nêu rõ Nguyên tắc cốt lõi (First Principles):**  
   * *"Về mặt kiến trúc, ưu tiên hàng đầu của chúng em ở phần này là [Tính toàn vẹn số liệu / Trải nghiệm độ trễ thấp / Sự an toàn dữ liệu]."*
2. **Bước 2: Giải thích Phương án và Lý do chọn (Trade-off):**  
   * *"Chúng em đã cân nhắc giữa phương án X và Y. Chúng em chọn Y vì Y giải quyết được bài toán Z, dù phải đánh đổi một chút ở khía cạnh W."*
3. **Bước 3: Dẫn chứng Thực tế trong Code:**  
   * *"Điều này được thể hiện rõ ở hàm `CalculateAllocation` dùng `math/big.Rat` để tránh lỗi float, hay việc dùng `InsertTx` của River trong cùng PostgreSQL transaction."*

### 💡 Phong thái tự tin:
* Không nói *"Em làm theo mẫu trên mạng"* hay *"Thư viện nó làm sẵn thế"*.
* Luôn dùng các thuật ngữ chuẩn: **ACID Invariant, Transactional Outbox/Enqueue, Idempotency, Deterministic Tie-Breaking, Thin Job Pattern, Fail-safe Normalization**.
* Tự hào về sự tiến hóa của thuật toán chia tiền: Bạn đã tìm thấy bug làm tròn lũy kế và đã tự thiết kế giải pháp `big.Rat` triệt để!
