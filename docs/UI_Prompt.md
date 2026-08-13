# Prompt dùng với Claude Design — sinh giao diện PaySplit

Đính kèm `design.md` (ở project root) vào cuộc trò chuyện, rồi dán **Prompt A** một
lần duy nhất ở tin nhắn đầu. Sau đó mỗi màn hình dùng **Prompt B**.

---

## Prompt A — mở đầu (dán 1 lần, kèm file `design.md`)

```
Tôi đính kèm design.md — hệ thống thiết kế đã khoá cho PaySplit, một app Flutter
chia tiền nhóm cho người Việt. Bạn sẽ dựng mockup giao diện cho tôi qua nhiều lượt.

QUY TẮC BẤT BIẾN

1. design.md là luật, không phải gợi ý. Mọi màu, font, spacing, radius, duration
   phải lấy từ token có tên ở §2. Tuyệt đối không viết giá trị màu hay font thẳng
   vào CSS. Nếu cần một giá trị chưa có token, thêm token mới vào :root trước rồi
   mới tham chiếu, và nói cho tôi biết bạn đã thêm gì.

2. Đọc §11 "Cấm tuyệt đối" trước khi viết dòng code đầu tiên. 18 điều đó là lý do
   tồn tại của file này. Đặc biệt: không header nền xanh đặc, không card lồng card,
   không toast ăn mừng, không chip chỉ có màu mà thiếu icon + chữ.

3. Copy bằng tiếng Việt, xưng "bạn". Nút là động từ + tân ngữ cụ thể (§9).
   Nút của người nợ ghi "Tôi đã chuyển", KHÔNG phải "Thanh toán" — PaySplit không
   chuyển tiền và không tự tất toán nợ.

4. Số liệu phải hợp lý và nhất quán giữa các màn hình. Tên người dùng tên Việt thật
   (Minh Anh, Thu Hà, Quốc Bảo, Lan Chi, Đức Huy) — không "Nguyễn Văn A", không
   "User 1". Tiền định dạng đúng §4: 245.000 ₫. Đừng bịa số liệu thống kê.

ĐỊNH DẠNG OUTPUT

- Mỗi lần: MỘT artifact HTML self-contained, chạy được ngay.
- Khung nội dung rộng đúng 390px, căn giữa trang, nền ngoài khung màu
  var(--color-paper-3) để thấy mép. KHÔNG vẽ khung điện thoại giả, không notch,
  không thanh trạng thái iOS giả — §11 điều 17 cấm.
- Nhúng <link> Google Fonts cho Be Vietnam Pro (600,700), IBM Plex Sans (400,500),
  JetBrains Mono (400,500). Nếu môi trường chặn font ngoài, để chuỗi fallback
  system-ui nhưng KHÔNG được đổi sang Inter/Roboto/Poppins rồi coi đó là thiết kế.
- Dán toàn bộ khối token §2 (cả light lẫn dark) vào :root, kể cả token màn này
  không dùng. Thêm nút toggle dark ở góc trên ngoài khung 390px.
- Dựng đủ 8 state ở §6.1 cho mọi thành phần tương tác. State nào không kích hoạt
  được bằng chuột thì thêm class .is-hover / .is-focus / .is-pressed / .is-loading
  để tôi xem được, và ghi chú rõ đó là class demo.

TRƯỚC KHI TRẢ KẾT QUẢ, tự soát và báo cho tôi:
- Accent cobalt chiếm bao nhiêu % diện tích màn hình? Phải ≤5%.
- Mọi con số tiền đã có tabular-nums chưa?
- Mọi chip trạng thái đã có đủ icon + chữ + màu chưa?
- Có giá trị màu/font nào không đi qua var(--token) không?
- Vùng chạm nào dưới 48dp không?

Xác nhận bạn đã đọc design.md và tóm tắt trong 3 câu: theme, bộ ba font, và điều
cấm nào bạn thấy dễ vi phạm nhất. Rồi dừng, chờ tôi giao màn hình.
```

---

## Prompt B — mỗi màn hình (lặp lại)

```
Dựng màn hình #<số> "<tên>" — xem dòng tương ứng ở bảng §7 của design.md.

Spec component liên quan: §<6.x>
Trạng thái cần thể hiện: <liệt kê>
Dữ liệu mẫu: <mô tả, hoặc "bạn tự chọn cho hợp lý">

Ngoài trạng thái mặc định, cho tôi xem thêm: trạng thái rỗng, trạng thái đang tải
(skeleton, không spinner giữa màn), và trạng thái lỗi mạng.
```

---

## Thứ tự dựng đề xuất

Dựng theo giá trị giảm dần, không theo số thứ tự. Ba màn đầu chốt được 80% ngôn ngữ
hình ảnh của app; xong ba màn đó thì các màn còn lại chỉ là lắp ráp.

| Lượt | Màn | Vì sao trước |
|---|---|---|
| 1 | **#16 Công nợ của tôi** | Chứa thẻ công nợ §6.2 — component quan trọng nhất. Chốt được nó là chốt được nhịp toàn app |
| 2 | **#18 Bottom sheet QR** | Bề mặt graphite duy nhất. Chốt tương phản dark + hierarchy của số tiền / mã tham chiếu |
| 3 | **#14 Gán món cho thành viên** | Màn khó nhất (§6.5). Nếu ngôn ngữ thiết kế sống sót ở đây thì sống sót ở mọi nơi |
| 4 | #17 Chi tiết khoản nợ | Kiểm chứng EXP-03: truy ngược tới từng món |
| 5 | #20 Hộp chờ xác nhận | Luồng của chủ nợ, có nhánh từ chối bắt buộc nhập lý do |
| 6 | #13 Soát & sửa hoá đơn | Sửa inline + đánh dấu ô OCR độ tin cậy thấp |
| 7 | #5, #7 Nhóm | Điều hướng cấp trên |
| 8 | #1–#4 Auth | Đơn giản nhất, để cuối |

---

## Prompt mẫu đã điền sẵn — lượt 1

```
Dựng màn hình #16 "Công nợ của tôi" (tab 2) — xem §7 và §6.2 của design.md.

Bố cục:
- Con số anh hùng ở đầu: số dư ròng của tôi trên tất cả các nhóm, dùng --text-figure,
  display 700, tabular-nums. Bên dưới là một dòng meta giải thích con số đó.
- Hai nhóm danh sách: "Tôi nợ" và "Nợ tôi". Mỗi hàng theo đúng anatomy §6.2.
- Số tiền căn phải, thẳng cột khi cuộn.
- Không viền bao quanh từng hàng — chỉ hairline --color-rule phân cách.

Dữ liệu mẫu: tôi đang nợ 3 người và được 2 người nợ lại, trải trên 2 nhóm
("Đà Lạt 08/2026" và "Cơm trưa văn phòng"). Trong đó phải có đủ 5 trạng thái của
enum debt_status (§5): awaiting, pending_confirmation, stalled_confirmation,
rejected, settled. Một hàng gộp nhiều hoá đơn (meta ghi "3 hoá đơn").

Cho tôi xem thêm: một hàng ở trạng thái mở rộng (expand) lộ danh sách hoá đơn con,
và trạng thái rỗng của cả màn.
```

---

## Lưu ý khi dùng

- **Claude Design render HTML/React, không render Flutter.** Đây là mockup để chốt
  hình thức. Khi wire sang Flutter, token Dart đã sẵn ở §12 của design.md.
- Nếu output trôi khỏi spec, đừng mô tả lại spec — chỉ cần trả lời:
  *"Vi phạm §11 điều <số>. Sửa lại."* File đã là nguồn chân lý, nhắc số điều là đủ.
- Sau vài màn, nếu bạn muốn siết thêm, thêm phát hiện mới vào design.md rồi đính kèm
  lại bản cập nhật — đừng tích luỹ luật trong lịch sử chat.
