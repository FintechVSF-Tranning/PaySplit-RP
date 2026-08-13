# 23 màn hình PaySplit — prompt cho Claude Design

Dùng sau khi đã dán **Prompt A** ở [UI_Prompt.md](UI_Prompt.md) kèm file `design.md`.

Mỗi mục dưới đây là một prompt hoàn chỉnh, dán nguyên khối. Thứ tự trong file là
theo số màn (khớp bảng §7 của `design.md`) — nhưng **đừng dựng theo thứ tự này**.
Xem §Thứ tự dựng ở cuối file.

---

## §0. Bộ dữ liệu mẫu dùng chung — dán 1 lần, ngay sau Prompt A

Dán khối này trước khi giao màn đầu tiên. Nó là lý do các màn hình ghép lại thành
một luồng thay vì 23 mockup rời rạc.

```
Dùng bộ dữ liệu sau cho MỌI màn hình từ giờ. Đừng bịa số mới; nếu cần dữ liệu
chưa có ở đây thì hỏi tôi.

NGƯỜI DÙNG ĐANG ĐĂNG NHẬP: Tuấn Lâm (tuanlam@gmail.com)
Tài khoản nhận tiền: Vietcombank · 0071000512345 · PHAM TUAN LAM

NHÓM A — "Đà Lạt 08/2026" · 5 thành viên
  Minh Anh (captain) · Tuấn Lâm · Thu Hà · Quốc Bảo · Lan Chi

NHÓM B — "Cơm trưa văn phòng" · 4 thành viên
  Đức Huy (captain) · Tuấn Lâm · Thu Hà · Lan Chi

HOÁ ĐƠN (nhóm A)
  B1 · "Nhà hàng Cỏ Hồng" · 13/08/2026 · chủ nợ Minh Anh · ĐÃ CHỐT
       Lẩu gà lá é      ×1   450.000
       Cơm chiên        ×2   160.000
       Rau nhúng        ×3    90.000
       Nước suối        ×5    50.000
       Bia Saigon       ×6   180.000
       Tạm tính 930.000 · Phí dịch vụ 5% 46.500 · VAT 8% 78.120
       TỔNG 1.054.620 ₫   → phần của Tuấn Lâm: 186.400 ₫
  B2 · "Homestay Mây Lang Thang" · 12/08/2026 · chủ nợ Quốc Bảo · ĐÃ CHỐT
       TỔNG 2.400.000 ₫   → phần của Tuấn Lâm: 480.000 ₫
  B3 · "Cà phê Mê Linh" · 13/08/2026 · chủ nợ Minh Anh · BẢN NHÁP
       TỔNG 320.000 ₫ (chưa chốt, chưa sinh nợ)
  B4 · "Vé cáp treo Robin Hill" · 12/08/2026 · chủ nợ Minh Anh · ĐÃ CHỐT
       TỔNG 293.000 ₫    → phần của Tuấn Lâm: 58.600 ₫

CÔNG NỢ CỦA TUẤN LÂM
  Tôi nợ:
    → Minh Anh   245.000 ₫  · 2 hoá đơn (B1 + B4) · CHỜ XÁC NHẬN
       mã tham chiếu PSPL 8K2M 4QN7 · nộp bằng chứng 19:42 · 13/08
    → Quốc Bảo   480.000 ₫  · 1 hoá đơn (B2)      · CHỜ THANH TOÁN
    → Đức Huy     85.000 ₫  · nhóm B              · BỊ TỪ CHỐI
       lý do: "Mình chưa thấy tiền về, mã tham chiếu không khớp."
  Nợ tôi:
    ← Thu Hà     120.000 ₫  · nhóm A · CHỜ XÁC NHẬN (chờ BẠN xác nhận)
    ← Quốc Bảo    95.000 ₫  · nhóm A · QUÁ HẠN XÁC NHẬN
    ← Lan Chi     60.000 ₫  · nhóm A · ĐÃ TẤT TOÁN

  Số dư ròng của Tuấn Lâm: −595.000 ₫
  (810.000 phải trả − 215.000 sẽ nhận; khoản đã tất toán không tính)

Kiểm tra: tổng phải khớp. Nếu bạn thấy con số nào không cộng đúng, báo tôi thay vì
tự sửa cho vừa.
```

---

## Nhóm 1 — Xác thực (màn 1–4)

### #1 · Đăng nhập — UC01 / FR 4.1.1

```
Dựng màn hình #1 "Đăng nhập" — §7 design.md, dòng 1.
Component: §6.6 (input), §6.1 (nút).

Nội dung: wordmark PaySplit, input email, input mật khẩu có nút hiện/ẩn,
nút primary "Đăng nhập", link ghost "Quên mật khẩu", dòng cuối "Chưa có tài khoản?
Đăng ký".

Cho tôi xem 4 biến thể trong cùng artifact, xếp dọc và ghi nhãn rõ:
1. Mặc định
2. Đang gửi (nút loading, giữ nguyên bề rộng, delay 150ms mới hiện spinner)
3. Sai thông tin đăng nhập — FR 4.1.1 yêu cầu thông điệp CHUNG, không được tiết lộ
   email có tồn tại hay không. Viết câu lỗi đúng cấu trúc §6.6:
   chuyện gì → vì sao → làm gì tiếp.
4. Tài khoản chưa xác minh email (403 EMAIL_NOT_VERIFIED) — kèm hành động
   "Gửi lại email xác minh" ngay trong khối lỗi.

Không dùng social login (ngoài scope PRD). Không nền gradient.
```

### #2 · Đăng ký — UC02 / FR 4.1.2

```
Dựng màn hình #2 "Đăng ký" — §7 dòng 2.

Input: tên hiển thị, email, mật khẩu, xác nhận mật khẩu.
Thanh độ mạnh mật khẩu hiển thị INLINE ngay dưới field, không dialog, không tooltip.
Thanh này dùng --color-danger / --color-warn / --color-success và LUÔN kèm nhãn chữ
("Yếu" / "Trung bình" / "Mạnh") — §11 điều 18 cấm phân biệt chỉ bằng màu.
Liệt kê yêu cầu mật khẩu dạng checklist, tick dần khi người dùng gõ.

Biến thể cần xem: mặc định · đang gõ (mật khẩu yếu) · email đã tồn tại (lỗi ở field)
· đang gửi.
```

### #3 · Chờ xác minh email — FR 4.1.2

```
Dựng màn hình #3 "Chờ xác minh email" — §7 dòng 3.

Đây là trạng thái rỗng CÓ Ý NGHĨA, không phải màn báo lỗi: nói rõ đã gửi tới đâu,
cần làm gì, và mất bao lâu. Đọc §9 về copy trạng thái rỗng.

Nút "Gửi lại email" có cooldown — hiện đếm ngược trên chính nhãn nút
("Gửi lại sau 47 giây"), không disable câm. §6.1 nói disabled phải kèm lý do bằng chữ.
Có link phụ "Dùng email khác".

Biến thể: vừa vào màn · đang trong cooldown · đã gửi lại thành công (im lặng —
đổi trạng thái tại chỗ, KHÔNG toast ăn mừng, §8).
```

### #4 · Quên & đặt lại mật khẩu — UC03 / FR 4.1.3

```
Dựng màn hình #4 "Quên mật khẩu" — §7 dòng 4. Hai bước trong cùng artifact:

Bước 1 — nhập email. Sau khi gửi, hiện xác nhận CHUNG chung ("Nếu email này có
tài khoản, chúng tôi đã gửi liên kết đặt lại") — không xác nhận email có tồn tại.
Bước 2 — màn đặt mật khẩu mới (từ deep link), có thanh độ mạnh như màn #2.

Thêm biến thể: liên kết đã hết hạn hoặc đã dùng rồi — nêu rõ và cho đường thoát
("Gửi liên kết mới").
```

---

## Nhóm 2 — Nhóm chi tiêu (màn 5–10)

### #5 · Danh sách nhóm (tab 1) — UC07

```
Dựng màn hình #5 "Danh sách nhóm", tab 1 của bottom nav — §7 dòng 5, §6.7.

QUAN TRỌNG: mỗi thẻ nhóm hiện số dư ròng CỦA BẠN trong nhóm đó, không phải tổng
chi tiêu của nhóm. Người dùng mở app để biết mình đứng ở đâu, không phải để biết
nhóm tiêu bao nhiêu.

Mỗi hàng: tên nhóm · số thành viên (cụm avatar chồng, tối đa 4 + "+N") ·
hoạt động gần nhất · số dư ròng của bạn căn phải, mono tabular-nums,
màu theo dấu (§4: âm = --color-ink, dương = --color-success).

Dữ liệu: nhóm A "Đà Lạt 08/2026" (bạn −650.000 ₫), nhóm B "Cơm trưa văn phòng"
(bạn −85.000 ₫), và một nhóm cũ "Sinh nhật Lan Chi" đã tất toán hết (0 ₫).

Có FAB hoặc nút primary "Tạo nhóm" — dùng --shadow-fab, đây là một trong hai chỗ
duy nhất được phép có bóng đổ (§2).

Cho tôi xem thêm: trạng thái rỗng (chưa có nhóm nào) và skeleton đang tải.
```

### #6 · Tạo nhóm — UC07 / FR 4.1.7

```
Dựng màn hình #6 "Tạo nhóm" — §7 dòng 6.

Chỉ 2 field: tên nhóm (bắt buộc, không được rỗng theo CHECK trong dbv1.sql) và
tiền tệ (mặc định VND, khoá — prototype chỉ hỗ trợ VND).
Sau khi tạo, người tạo tự động thành Captain — nói rõ điều này bằng một dòng
giải thích, đừng để người dùng tự đoán.

Biến thể: mặc định · tên rỗng (lỗi inline) · đang tạo.
```

### #7 · Chi tiết nhóm — 3 sub-tab

```
Dựng màn hình #7 "Chi tiết nhóm" cho nhóm A "Đà Lạt 08/2026" — §7 dòng 7.

Header: tên nhóm, cụm avatar 5 thành viên, nút mời.
Ba sub-tab: "Hoá đơn" · "Số dư" · "Nhật ký".

Cho tôi xem CẢ BA tab trong cùng artifact, xếp dọc, ghi nhãn rõ:

TAB HOÁ ĐƠN — danh sách B1, B2, B3, B4 (§0). B3 là bản nháp → chip viền đứt nét
nhãn "BẢN NHÁP" mono. Bốn cái còn lại đã chốt → KHÔNG chip, thay bằng icon khoá +
dòng meta "Đã chốt · <ngày>" (§5).

TAB SỐ DƯ — số dư ròng từng thành viên (view v_member_balances). Dương = được nhận,
âm = phải trả. Sắp xếp từ âm nhất đến dương nhất. Tổng cả cột phải bằng 0 — hiện
dòng kiểm tra đó ở cuối, đây là bằng chứng cho người dùng rằng hệ thống không
tạo ra hay làm mất tiền.

TAB NHẬT KÝ — dòng thời gian từ bảng group_activities, mới nhất trước. Các loại:
created_bill, finalized_bill, submitted_proof, confirmed_payment, rejected_payment.
Mỗi dòng: avatar người thực hiện + câu mô tả + thời gian tương đối (§4).

Sub-tab active dùng --color-accent cho chữ + gạch chân 2px. Không nền pill.
```

### #8 · Mời thành viên — UC09 / FR 4.1.8

```
Dựng màn hình #8 "Mời thành viên" (bottom sheet) — §7 dòng 8.

Ba cách mời, cùng một mã: QR · link · mã chữ.
QR tối thiểu 280dp, nền trắng thuần (ngoại lệ chức năng duy nhất, §6.4 điều 3).
Link và mã đều có nút copy riêng.

BẮT BUỘC hiện rõ: hạn dùng ("Hết hạn 20/08/2026 · còn 6 ngày") và số lượt còn lại
("Đã dùng 2/10 lượt"). Đây là dữ liệu trong bảng group_invites — người dùng cần
biết trước khi gửi cho người khác.

Chỉ Captain thấy màn này. Có nút destructive "Vô hiệu hoá mã" (§6.1) —
thao tác này KHÔNG đảo ngược được nên dùng dialog xác nhận (§8).
```

### #9 · Tham gia nhóm — UC08 / FR 4.1.9

```
Dựng màn hình #9 "Tham gia nhóm" — §7 dòng 9.

Người dùng mở từ deep link. Hiện: tên nhóm, số thành viên, ai mời, rồi nút primary
"Tham gia nhóm".

Cho tôi 4 biến thể:
1. Mã hợp lệ — xem trước nhóm + nút tham gia
2. Mã hết hạn
3. Mã đã hết lượt dùng
4. Bạn đã là thành viên rồi → chuyển thẳng vào nhóm

Ba trạng thái lỗi đều phải có đường thoát bằng chữ ("Xin người tạo nhóm gửi mã mới"),
không phải ngõ cụt.
```

### #10 · Quản lý thành viên — UC10 / FR 4.1.10

```
Dựng màn hình #10 "Quản lý thành viên" nhóm A — §7 dòng 10.

Danh sách 5 thành viên: avatar, tên, huy hiệu vai trò (Captain / Thành viên),
số dư ròng trong nhóm, nút xoá.

ĐIỂM QUAN TRỌNG NHẤT CỦA MÀN NÀY: FR 4.1.10 chặn xoá thành viên khi số dư ròng ≠ 0.
Đừng disable nút xoá một cách câm lặng — §6.1 bắt buộc disabled phải kèm lý do
bằng chữ. Hiện đúng số còn lại:
  "Không thể xoá — Quốc Bảo còn được nhận 95.000 ₫ trong nhóm."
Thành viên có số dư = 0 thì nút xoá hoạt động bình thường.

Xoá thành viên là thao tác cần dialog xác nhận (§8 — không đảo ngược dễ dàng vì
lịch sử hoá đơn vẫn giữ member_id cũ).

Chỉ Captain thấy nút xoá. Cho tôi xem cả góc nhìn thành viên thường (chỉ đọc).
```

---

## Nhóm 3 — Hoá đơn & OCR (màn 11–15)

### #11 · Chụp / tải hoá đơn — UC11 / FR 4.1.11

```
Dựng màn hình #11 "Chụp hoá đơn" — §7 dòng 11.

Toàn màn là khung ngắm camera (giả lập bằng nền --color-graphite). Overlay:
khung ngắm 4 góc bằng --color-accent, dòng hướng dẫn ngắn về ánh sáng và
đặt phẳng hoá đơn. Nút chụp lớn ở dưới, nút phụ "Chọn từ thư viện" và
"Nhập tay" (fallback bắt buộc theo R1 trong PRD §8).

KHÔNG vẽ khung điện thoại giả bao ngoài (§11 điều 17). Chỉ dựng nội dung màn hình.
```

### #12 · OCR đang xử lý — UC12 / FR 4.1.12

```
Dựng màn hình #12 "OCR đang xử lý" — §7 dòng 12.

Dùng SKELETON của chính form hoá đơn sắp hiện ra, KHÔNG spinner giữa màn trống.
Người dùng phải thấy trước cấu trúc thứ sắp đến.

PERF-02 cho phép tối đa 10 giây. Sau 3 giây, thêm một dòng tiến trình bằng chữ
("Đang đọc hoá đơn… 4 giây") — dưới 3 giây thì im lặng.

Ba biến thể:
1. Đang xử lý (skeleton)
2. Thất bại sau nhiều lần thử (ocr_jobs.status = failed) — nêu lý do và cho đường
   thoát "Nhập tay", đây là fallback bắt buộc của R1
3. Chất lượng ảnh kém — đề nghị chụp lại, kèm gợi ý cụ thể
```

### #13 · Soát & sửa hoá đơn — UC14 / FR 4.1.14

```
Dựng màn hình #13 "Soát & sửa hoá đơn" cho B1 "Nhà hàng Cỏ Hồng" — §7 dòng 13.
Dữ liệu đầy đủ ở §0.

Mọi ô đều SỬA ĐƯỢC TẠI CHỖ, không mở màn phụ: tên quán, ngày, từng dòng món
(tên · số lượng · đơn giá · thành tiền), tạm tính, phí dịch vụ, VAT, giảm giá, tổng.

Ô có độ tin cậy OCR thấp → gạch chân đứt nét --color-warn. Đặt "Bia Saigon" và
dòng VAT vào diện này để tôi thấy cách xử lý.

REL-02: kết quả OCR chưa được soát thì không được chia. Nút "Tiếp tục" chỉ bật sau
khi người dùng đã xem hết — nêu rõ điều kiện đó bằng chữ.

Thêm biến thể có banner mismatch_warning: OCR đọc tổng 1.054.620 nhưng cộng chi tiết
ra 1.054.600. Banner này là HAIRLINE phía trên danh sách món, KHÔNG phải dialog —
nó là thông tin cần đối chiếu, không phải lỗi chặn (§6.5).

Có nút thêm dòng món thủ công và nút xoá từng dòng (xoá dùng optimistic + Undo, §8).
```

### #14 · Gán món cho thành viên — UC13 / FR 4.1.13

```
Dựng màn hình #14 "Gán món cho thành viên" cho B1 — §7 dòng 14, spec đầy đủ ở §6.5.
Đây là màn khó nhất của app, làm kỹ.

Mỗi dòng món: tên món bên trái · "×N" và đơn giá ở giữa · cụm avatar bên phải.
Chạm avatar để bật/tắt người gánh món đó. Avatar đang bật: viền --color-accent 2px.
Avatar tắt: opacity 0.4, không viền.

Thanh tổng kết CỐ ĐỊNH ở chân màn, luôn hiện: "Đã gán 930.000 / 1.054.620 ₫".
Khi lệch, thanh chuyển --color-warn và hiện số chênh lệch cụ thể. Người dùng không
bao giờ được phép chốt hoá đơn trong trạng thái mù.

Có nút "Chia đều cho tất cả" áp cho toàn bộ món, và nút chia đều theo từng dòng.

Dùng đúng 5 thành viên nhóm A. Gán như sau để tôi thấy đủ các kiểu:
- Lẩu gà lá é: cả 5 người
- Bia Saigon: chỉ Minh Anh, Quốc Bảo, Đức Huy → KHÔNG có Tuấn Lâm
- Nước suối: cả 5
- Cơm chiên: Tuấn Lâm + Thu Hà
- Rau nhúng: CHƯA GÁN AI → dòng này phải nổi bật là đang thiếu

Cho tôi xem thêm: trạng thái thanh tổng kết khi đã gán đủ (--color-success).
```

### #15 · Chốt hoá đơn — UC15 / FR 4.1.15

```
Dựng màn hình #15 "Chốt hoá đơn" cho B1 — §7 dòng 15.

Đây là màn XEM TRƯỚC KHÔNG THỂ HOÀN TÁC. Hiện bảng ai nợ ai bao nhiêu, gộp theo
cặp debtor→creditor đúng như mô hình debts trong dbv1.sql:
  Tuấn Lâm → Minh Anh   186.400 ₫
  Thu Hà   → Minh Anh   ...
  Quốc Bảo → Minh Anh   ...
  Lan Chi  → Minh Anh   ...
(bạn tự tính từ phần gán ở màn #14; tổng phải bằng đúng 1.054.620 ₫)

BẮT BUỘC theo EXP-01: hiện dòng chênh lệch làm tròn riêng ("Chênh lệch làm tròn:
+20 ₫ tính vào phần của Minh Anh"). REL-01 nói tổng các phần phải khớp tuyệt đối
tổng hoá đơn — màn này là nơi người dùng KIỂM CHỨNG được điều đó, đừng giấu nó đi.

Nút primary "Chốt hoá đơn". Đây là thao tác bất biến (REL-03) nên phải có dialog
xác nhận (§8) nói thẳng hậu quả: "Sau khi chốt, hoá đơn không sửa được nữa. Muốn
sửa phải huỷ và tạo lại."

Cho tôi xem thêm: trạng thái sau khi chốt — nút Sửa BIẾN MẤT hoàn toàn, thay bằng
dòng giải thích, KHÔNG phải nút disabled (§5).
```

---

## Nhóm 4 — Công nợ & thanh toán (màn 16–20)

### #16 · Công nợ của tôi (tab 2) — UC16 / FR 4.1.16

```
Dựng màn hình #16 "Công nợ của tôi", tab 2 — §7 dòng 16, component §6.2.
Đây là component quan trọng nhất của app, làm kỹ nhất.

Bố cục:
- Con số anh hùng đầu màn: −595.000 ₫ ở --text-figure, display 700, tabular-nums.
  Dưới nó một dòng meta giải thích ("Bạn phải trả 810.000 ₫ và sẽ nhận 215.000 ₫").
- Hai nhóm danh sách: "Tôi nợ" (3 hàng) và "Nợ tôi" (3 hàng). Dữ liệu §0.
- Mỗi hàng theo đúng anatomy §6.2: avatar · tên · meta (số hoá đơn + tên nhóm) ·
  chip trạng thái · số tiền căn phải mono tabular-nums.
- KHÔNG viền bao quanh từng hàng. Chỉ hairline --color-rule phân cách. Không card
  lồng card (§11 điều 4).

Sáu hàng này phủ đủ 5 trạng thái của enum debt_status. Trạng thái awaiting phải là
trạng thái IM LẶNG NHẤT (--color-ink-3 trung tính) — nếu mọi hàng đều rực màu thì
không hàng nào nổi bật (§5).

Cho tôi xem thêm trong cùng artifact:
1. Một hàng ở trạng thái MỞ RỘNG, lộ danh sách hoá đơn con (hàng "→ Minh Anh
   245.000 ₫" mở ra thành B1 186.400 và B4 58.600). Mở tại chỗ, không sang màn mới.
2. Trạng thái rỗng của cả màn ("Bạn không nợ ai và không ai nợ bạn").
3. Skeleton đang tải.
```

### #17 · Chi tiết khoản nợ — UC16 / EXP-03

```
Dựng màn hình #17 "Chi tiết khoản nợ" cho khoản "Tuấn Lâm → Minh Anh 245.000 ₫" —
§7 dòng 17.

Màn này tồn tại để thoả EXP-03: mọi khoản nợ phải truy ngược được về hoá đơn và
TỪNG MÓN. Cấu trúc phân cấp 3 tầng, hiện hết trong một màn:

  Tổng 245.000 ₫ · chờ xác nhận
  └ B1 "Nhà hàng Cỏ Hồng" 13/08 · 186.400 ₫
     └ Lẩu gà lá é   chia 5 người   90.000 ₫
     └ Cơm chiên     chia 2 người   80.000 ₫
     └ ... (kèm phần phí dịch vụ + VAT phân bổ)
  └ B4 "Vé cáp treo Robin Hill" 12/08 · 58.600 ₫
     └ ...

Hiện rõ phần phí dịch vụ và VAT được phân bổ vào phần của bạn như thế nào (EXP-01).
Không có con số nào được phép là hộp đen.

Header có: thông tin người nhận, mã tham chiếu PSPL 8K2M 4QN7 (mono, tracking rộng,
nút copy), thời điểm nộp bằng chứng, và ảnh bằng chứng đã gửi.

Nút primary tuỳ trạng thái: awaiting → "Tạo mã QR"; pending_confirmation → không có
nút hành động, chỉ dòng "Đang chờ Minh Anh xác nhận".
```

### #18 · Bottom sheet QR — UC17 / FR 4.1.17

```
Dựng màn hình #18 "Bottom sheet thanh toán QR" — §7 dòng 18, spec đầy đủ §6.4.
Đây là bề mặt tối DUY NHẤT của app.

Nền --color-graphite, radius --radius-sheet chỉ 2 góc trên, --shadow-sheet.
Thứ tự dọc bắt buộc:
1. Số tiền 245.000 ₫ — display 700, --text-figure, --color-ink-inverse, tabular-nums
2. Người nhận: Minh Anh · Techcombank · 1903 **** 4521 · NGUYEN MINH ANH
3. Mã QR — nền TRẮNG THUẦN (ngoại lệ chức năng duy nhất trong toàn app, vì máy quét
   cần nó), tối thiểu 280dp vuông, padding trắng 16dp quanh mã
4. Mã tham chiếu PSPL 8K2M 4QN7 — mono, tracking 0.08em, nút copy. Đây là thứ giúp
   chủ nợ đối chiếu thủ công; phải dễ đọc hơn mọi thứ khác trừ số tiền
5. Nút primary "Tôi đã chuyển"

NHÃN NÚT: "Tôi đã chuyển", KHÔNG phải "Thanh toán" hay "Trả nợ" (§9). PaySplit
không chuyển tiền; nhãn sai ở đây là app nói dối người dùng về tiền của họ.

Thêm một dòng giải thích ngắn phía dưới nút, nói thẳng: bấm nút này chỉ báo cho
Minh Anh, khoản nợ chỉ đóng khi Minh Anh xác nhận đã nhận.

KHÔNG vẽ khung app ngân hàng giả (§11 điều 17). Kiểm tương phản kỹ — đây là chỗ
dễ trượt 4.5:1 nhất trong app.
```

### #19 · Nộp bằng chứng — UC18 / FR 4.1.18

```
Dựng màn hình #19 "Nộp bằng chứng chuyển khoản" — §7 dòng 19.

Nội dung: vùng tải ảnh (chụp màn hình giao dịch), ô ghi chú tuỳ chọn, nhắc lại
số tiền và mã tham chiếu để người dùng đối chiếu trước khi gửi.

SAU KHI GỬI THÀNH CÔNG: nói rõ khoản nợ chuyển sang "Chờ xác nhận" và CHƯA XONG.
Đây là chỗ dễ khiến người dùng hiểu nhầm nhất trong toàn app — viết câu xác nhận
cho đúng, đừng dùng chữ "Hoàn tất" hay "Thành công".
Thành công thì im lặng đổi trạng thái tại chỗ, không toast ăn mừng (§8).

Biến thể: chưa chọn ảnh · đã chọn ảnh (xem trước + nút xoá) · đang tải lên
(có % tiến trình) · lỗi ảnh quá 5MB (dùng đúng cấu trúc câu lỗi ở §6.6).
```

### #20 · Hộp chờ xác nhận (chủ nợ) — UC19 / FR 4.1.19

```
Dựng màn hình #20 "Chờ bạn xác nhận" — §7 dòng 20. Đây là góc nhìn CHỦ NỢ.

Danh sách khoản người khác báo đã trả cho bạn. Dữ liệu §0:
- Thu Hà 120.000 ₫ · chờ bạn xác nhận · nộp bằng chứng 2 giờ trước
- Quốc Bảo 95.000 ₫ · QUÁ HẠN XÁC NHẬN (stalled_confirmation) — trạng thái này
  nghĩa là BẠN chưa xử lý sau nhiều lần nhắc; câu chữ phải nói đúng điều đó,
  không được đổ lỗi cho người trả

Mỗi khoản mở ra: ảnh bằng chứng xem được toàn màn, số tiền, mã tham chiếu để đối
chiếu với app ngân hàng, ghi chú của người trả.
Hai nút: primary "Xác nhận đã nhận" · destructive "Từ chối".

Từ chối BẮT BUỘC nhập lý do (CHECK trong dbv1.sql: rejected_at và rejection_reason
luôn đi cùng nhau). Dựng sheet nhập lý do, có vài lý do gợi ý bấm nhanh
("Chưa thấy tiền về", "Số tiền không khớp", "Mã tham chiếu không khớp") nhưng
vẫn cho gõ tự do.

Xác nhận đã nhận là thao tác KHÔNG đảo ngược → dialog xác nhận (§8).
Sau khi xác nhận: hàng đó đổi sang "Đã tất toán" TẠI CHỖ, im lặng, không confetti.

Thêm trạng thái rỗng ("Không có khoản nào chờ bạn xác nhận").
```

---

## Nhóm 5 — Hoạt động & tài khoản (màn 21–23)

### #21 · Hoạt động / thông báo (tab 3) — FR 4.2.1

```
Dựng màn hình #21 "Hoạt động", tab 3 — §7 dòng 21.

Gộp từ group_activities và notifications. Chia 2 phần:

CẦN BẠN XỬ LÝ (lên đầu, đây là thứ sinh badge đỏ ở bottom nav):
- Thu Hà báo đã chuyển 120.000 ₫ · chờ bạn xác nhận
- Quốc Bảo 95.000 ₫ quá hạn xác nhận
- Đức Huy đã từ chối khoản 85.000 ₫ của bạn

THÔNG TIN (không sinh badge):
- Minh Anh đã chốt hoá đơn "Nhà hàng Cỏ Hồng"
- Lan Chi đã tham gia nhóm "Đà Lạt 08/2026"
- Nhắc: bạn còn nợ Quốc Bảo 480.000 ₫ (từ reminder scheduler, FR 4.2.1)

§6.7 nói badge đỏ CHỈ đếm nhóm đầu. Thông báo thuần thông tin không sinh badge —
nếu mọi thứ đều kêu thì không thứ gì kêu.

Mục chưa đọc: chấm --color-accent nhỏ bên trái. Đã đọc: không chấm, chữ --color-ink-2.
Thêm trạng thái rỗng và skeleton.
```

### #22 · Hồ sơ & tài khoản ngân hàng (tab 4) — UC06 / FR 4.1.6

```
Dựng màn hình #22 "Tài khoản", tab 4 — §7 dòng 22.

Phần 1 — Hồ sơ: avatar (có nút đổi), tên hiển thị, email (chỉ đọc), số điện thoại.

Phần 2 — TÀI KHOẢN NHẬN TIỀN. Đây là phần quan trọng: thiếu nó thì không sinh được
VietQR và người khác không trả được tiền cho bạn. Ba field: ngân hàng, số tài khoản,
tên chủ tài khoản.
Chọn ngân hàng bằng MÀN HÌNH DANH SÁCH CÓ Ô TÌM KIẾM, không phải dropdown dài —
Việt Nam có hơn 50 ngân hàng trong danh mục NAPAS.
Dữ liệu §0: Vietcombank · 0071000512345 · PHAM TUAN LAM

Nếu chưa thiết lập tài khoản nhận tiền, hiện banner hairline --color-warn ở đầu màn
nói rõ hậu quả: "Chưa có tài khoản nhận tiền — người khác chưa trả được tiền cho bạn."

Phần 3 — liên kết: Đổi mật khẩu · Đăng xuất (destructive).

Cho tôi xem cả 2 trạng thái: đã thiết lập tài khoản NH, và chưa thiết lập.
```

### #23 · Đổi mật khẩu & đăng xuất — UC04, UC05 / FR 4.1.4, 4.1.5

```
Dựng màn hình #23 "Đổi mật khẩu" — §7 dòng 23.

Ba field: mật khẩu hiện tại, mật khẩu mới, xác nhận mật khẩu mới.
Thanh độ mạnh như màn #2.

CẢNH BÁO BẮT BUỘC, hiện TRƯỚC khi bấm nút, không phải sau: FR 4.1.5 nói đổi mật
khẩu sẽ thu hồi mọi phiên đăng nhập khác. Viết thẳng: "Đổi mật khẩu sẽ đăng xuất
tài khoản của bạn khỏi mọi thiết bị khác."

Trong cùng artifact, thêm dialog đăng xuất (UC04) — đây là thao tác đảo ngược được
dễ dàng nên KHÔNG cần dialog nặng, chỉ cần một sheet xác nhận nhẹ với hai nút.

Biến thể: mặc định · sai mật khẩu hiện tại · mật khẩu mới trùng mật khẩu cũ · đang gửi.
```

---

## Thứ tự dựng đề xuất

Đừng dựng theo thứ tự số. Ba màn đầu chốt được ~80% ngôn ngữ hình ảnh; xong ba màn
đó thì phần còn lại chủ yếu là lắp ráp.

| Lượt | Màn | Vì sao |
|---|---|---|
| 1 | **#16** Công nợ của tôi | Chứa thẻ công nợ §6.2 — component quan trọng nhất. Chốt nó là chốt nhịp cả app |
| 2 | **#18** Bottom sheet QR | Bề mặt graphite duy nhất. Chốt tương phản dark + hierarchy số tiền / mã tham chiếu |
| 3 | **#14** Gán món | Màn khó nhất. Sống sót ở đây thì sống sót mọi nơi |
| 4 | #17 Chi tiết khoản nợ | Kiểm chứng EXP-03 — cấu trúc phân cấp 3 tầng |
| 5 | #20 Hộp chờ xác nhận | Luồng chủ nợ + nhánh từ chối bắt buộc lý do |
| 6 | #15 Chốt hoá đơn | Chênh lệch làm tròn (EXP-01) + tính bất biến (REL-03) |
| 7 | #13 Soát & sửa hoá đơn | Sửa inline + ô OCR tin cậy thấp |
| 8 | #7, #5 Nhóm | Điều hướng cấp trên, tái dùng ngôn ngữ đã chốt |
| 9 | #21, #22 Hoạt động, Tài khoản | |
| 10 | #10, #8, #9, #6 Thành viên & lời mời | |
| 11 | #11, #12 Camera & OCR | |
| 12 | #1–#4, #19, #23 | Đơn giản nhất, để cuối |

## Sau khi dựng xong nhóm màn

Yêu cầu một artifact tổng hợp:

```
Ghép các màn đã dựng thành một artifact duy nhất, xếp lưới ngang, mỗi màn một khung
390px có nhãn tên + số. Mục đích là soi tính nhất quán, không phải để dùng thật.
Rồi liệt kê cho tôi mọi chỗ các màn KHÔNG khớp nhau: khác spacing ở cùng vai trò,
khác cách hiển thị cùng một trạng thái, khác cách format cùng một loại dữ liệu.
Đừng tự sửa — chỉ liệt kê, tôi sẽ quyết định.
```
