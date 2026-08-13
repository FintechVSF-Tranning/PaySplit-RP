# PaySplit — Luồng màn hình

Sơ đồ điều hướng cho 23 màn ở §7 của [`design.md`](../design.md).
Số màn khớp bảng §7 và [`UI_Screen_Prompts.md`](UI_Screen_Prompts.md).

Mermaid render được trực tiếp trong VS Code (extension Markdown Preview Mermaid)
và trên GitHub.

---

## 1. Sơ đồ tổng

```mermaid
flowchart TD
    Guest(["Khách chưa đăng nhập"]) --> AUTH

    subgraph AUTH["① Xác thực"]
        S1["#1 Đăng nhập"]
        S2["#2 Đăng ký"]
        S3["#3 Chờ xác minh email"]
        S4["#4 Quên mật khẩu"]
    end

    AUTH --> SHELL

    subgraph SHELL["② App shell — 4 tab"]
        T1["#5 Nhóm"]
        T2["#16 Công nợ"]
        T3["#21 Hoạt động"]
        T4["#22 Tài khoản"]
    end

    T1 --> GROUP
    T1 --> BILL
    T2 --> PAY
    T3 --> CONFIRM
    T2 --> CONFIRM
    T4 --> ACCOUNT

    subgraph GROUP["③ Nhóm"]
        S6["#6 Tạo nhóm"]
        S7["#7 Chi tiết nhóm"]
        S8["#8 Mời thành viên"]
        S9["#9 Tham gia nhóm"]
        S10["#10 Quản lý thành viên"]
    end

    subgraph BILL["④ Tạo hoá đơn — luồng dài nhất"]
        S11["#11 Chụp hoá đơn"]
        S12["#12 OCR xử lý"]
        S13["#13 Soát & sửa"]
        S14["#14 Gán món"]
        S15["#15 Chốt hoá đơn"]
    end

    subgraph PAY["⑤ Trả nợ — góc nhìn người nợ"]
        S17["#17 Chi tiết khoản nợ"]
        S18["#18 Sheet QR"]
        S19["#19 Nộp bằng chứng"]
    end

    subgraph CONFIRM["⑥ Xác nhận — góc nhìn chủ nợ"]
        S20["#20 Hộp chờ xác nhận"]
    end

    subgraph ACCOUNT["⑦ Tài khoản"]
        S23["#23 Đổi mật khẩu"]
    end

    S15 -. "sinh công nợ" .-> T2
    S15 -. "ghi nhật ký" .-> T3
    S19 -. "báo chủ nợ" .-> T3
    S20 -. "báo người trả" .-> T3
```

---

## 2. Xác thực — vào app

```mermaid
flowchart TD
    Start(["Mở app"]) --> Check{Đã có phiên?}
    Check -->|Có| Shell(["App shell · tab Công nợ"])
    Check -->|Không| S1["#1 Đăng nhập"]

    S1 -->|"Chưa có tài khoản?"| S2["#2 Đăng ký"]
    S1 -->|"Quên mật khẩu"| S4a["#4 Nhập email"]
    S1 -->|"401 sai thông tin"| S1
    S1 -->|"403 EMAIL_NOT_VERIFIED"| S3

    S2 --> S3["#3 Chờ xác minh email"]
    S3 -->|"Gửi lại · có cooldown"| S3
    S3 -->|"Dùng email khác"| S2
    S3 -.->|"bấm link trong email"| S1

    S4a -.->|"bấm link trong email"| S4b["#4 Đặt mật khẩu mới"]
    S4b --> S1
    S4a -->|"link hết hạn / đã dùng"| S4a

    S1 -->|"đăng nhập thành công"| Shell

    Invite(["Deep link lời mời"]) --> Check2{Đã đăng nhập?}
    Check2 -->|Rồi| S9["#9 Tham gia nhóm"]
    Check2 -->|Chưa| S1
    S1 -.->|"giữ lại lời mời"| S9
```

**Lưu ý:** deep link lời mời khi chưa đăng nhập phải **giữ lại mã mời** qua suốt
luồng đăng nhập/đăng ký rồi mới đưa tới #9. Rơi mất mã ở đây là lỗi hay gặp nhất
của luồng onboarding qua link.

---

## 3. Nhóm

```mermaid
flowchart TD
    S5["#5 Danh sách nhóm · tab 1"]
    S5 -->|"Tạo nhóm"| S6["#6 Tạo nhóm"]
    S6 -->|"người tạo = Captain"| S7
    S5 -->|"chọn một nhóm"| S7["#7 Chi tiết nhóm"]

    S7 --> Tab1["Sub-tab Hoá đơn"]
    S7 --> Tab2["Sub-tab Số dư"]
    S7 --> Tab3["Sub-tab Nhật ký"]

    S7 -->|"Captain · Mời"| S8["#8 Mời thành viên"]
    S7 -->|"Captain · Thành viên"| S10["#10 Quản lý thành viên"]

    S8 -.->|"QR / link / mã"| Other(["Người được mời"])
    Other --> S9["#9 Tham gia nhóm"]
    S9 -->|"mã hợp lệ"| S7
    S9 -->|"hết hạn / hết lượt"| Dead["Ngõ cụt có đường thoát:<br/>xin mã mới"]

    S10 -->|"số dư ≠ 0"| Block["Chặn xoá<br/>nêu rõ số còn lại"]
    S10 -->|"số dư = 0"| Remove["Xoá · dialog xác nhận"]

    Tab1 -->|"+ Hoá đơn mới"| S11(["→ luồng ④"])
    Tab2 -.->|"kiểm chứng tổng = 0"| Tab2
```

---

## 4. Tạo hoá đơn — luồng dài nhất của app

Tám màn từ lúc mở app đến lúc sinh ra công nợ. Đây là đường găng của sản phẩm.

```mermaid
flowchart TD
    S7["#7 Chi tiết nhóm<br/>sub-tab Hoá đơn"] -->|"+"| Choice{Cách nhập}

    Choice -->|"Chụp ảnh"| S11["#11 Chụp hoá đơn"]
    Choice -->|"Chọn từ thư viện"| S11
    Choice -->|"Nhập tay — fallback R1"| S13

    S11 --> S12["#12 OCR đang xử lý<br/>PERF-02 ≤ 10s"]

    S12 -->|"succeeded"| S13["#13 Soát & sửa hoá đơn<br/>REL-02: bắt buộc người soát"]
    S12 -->|"failed sau N lần thử"| S13
    S12 -->|"ảnh quá mờ"| S11

    S13 -->|"mismatch_warning"| Warn["Banner hairline<br/>không phải dialog"]
    Warn --> S13
    S13 --> S14["#14 Gán món cho thành viên"]

    S14 -->|"còn món chưa gán"| S14
    S14 -->|"đã gán đủ 100%"| S15["#15 Chốt hoá đơn"]

    S15 --> Preview["Xem trước bất biến:<br/>ai nợ ai + chênh lệch làm tròn<br/>EXP-01"]
    Preview -->|"Quay lại sửa"| S14
    Preview -->|"Chốt · dialog xác nhận"| Locked["Bill = finalized<br/>BẤT BIẾN · REL-03"]

    Locked -.->|"sinh dòng debts<br/>gộp theo cặp debtor→creditor"| S16(["#16 Công nợ của mọi người"])
    Locked -.->|"finalized_bill"| S21(["#21 Hoạt động"])
    Locked --> S7
```

**Điểm không quay lui:** sau `Locked`, không có đường về #14. Sửa hoá đơn đã chốt
phải huỷ và tạo lại (REL-03). Vì vậy màn #15 phải cho xem trước đầy đủ — nó là
cánh cửa một chiều duy nhất trong app.

---

## 5. Trả nợ & xác nhận — trái tim của sản phẩm

Hai góc nhìn đối xứng trên cùng một khoản nợ.

```mermaid
flowchart TD
    subgraph P["Người nợ"]
        S16a["#16 Công nợ · nhóm 'Tôi nợ'"]
        S17["#17 Chi tiết khoản nợ<br/>truy ngược tới từng món · EXP-03"]
        S18["#18 Sheet QR<br/>VietQR + mã tham chiếu"]
        S19["#19 Nộp bằng chứng"]
    end

    subgraph C["Chủ nợ"]
        S16b["#16 Công nợ · nhóm 'Nợ tôi'"]
        S21["#21 Hoạt động<br/>Cần bạn xử lý"]
        S20["#20 Hộp chờ xác nhận"]
    end

    S16a -->|"mở rộng tại chỗ"| Expand["Danh sách hoá đơn con"]
    S16a --> S17
    Expand --> S17

    S17 -->|"awaiting · Tạo mã QR"| S18
    S18 -->|"Tôi đã chuyển"| S19
    S19 -->|"gửi ảnh + ghi chú"| Pending["debt = pending_confirmation"]
    Pending --> S16a

    Pending -.->|"thông báo"| S21
    S21 --> S20
    S16b --> S20

    S20 -->|"Xác nhận đã nhận<br/>dialog · không hoàn tác"| Settled["debt = settled"]
    S20 -->|"Từ chối<br/>BẮT BUỘC nhập lý do"| Rejected["debt = rejected"]

    Settled --> S16b
    Rejected -.->|"thông báo + lý do"| S16a
    Rejected --> S17
    S17 -->|"rejected · Tạo QR mới"| S18

    Cron(["Reminder scheduler<br/>FR 4.2.1"]) -.->|"quá N lần nhắc"| Stalled["debt = stalled_confirmation"]
    Stalled -.-> S21
```

**Vòng lặp từ chối** là nhánh dễ bị bỏ quên nhất: `rejected` → người nợ xem lý do ở
#17 → tạo QR mới ở #18 → quay lại #19. Nếu #17 không hiện lý do từ chối thì người
dùng bị kẹt mà không biết vì sao.

---

## 6. Máy trạng thái công nợ

Năm giá trị `debt_status` trong `dbv1.sql`, ánh xạ sang màn hình gây ra chuyển đổi.

```mermaid
stateDiagram-v2
    [*] --> awaiting: #15 chốt hoá đơn
    awaiting --> pending_confirmation: #19 nộp bằng chứng
    pending_confirmation --> settled: #20 chủ nợ xác nhận
    pending_confirmation --> rejected: #20 chủ nợ từ chối + lý do
    pending_confirmation --> stalled_confirmation: cron · quá N lần nhắc
    stalled_confirmation --> settled: #20 chủ nợ xác nhận muộn
    stalled_confirmation --> rejected: #20 chủ nợ từ chối muộn
    rejected --> awaiting: #18 tạo QR mới
    settled --> [*]

    note right of stalled_confirmation
        KHÔNG BAO GIỜ tự tất toán.
        Chỉ chủ nợ đóng được khoản nợ.
    end note
```

---

## 7. Tài khoản

```mermaid
flowchart TD
    S22["#22 Tài khoản · tab 4"]
    S22 --> Profile["Hồ sơ: tên, avatar, SĐT"]
    S22 --> Bank["Tài khoản nhận tiền<br/>NH + số TK + tên chủ TK"]
    S22 -->|"Đổi mật khẩu"| S23["#23 Đổi mật khẩu"]
    S22 -->|"Đăng xuất · sheet nhẹ"| S1(["#1 Đăng nhập"])

    S23 -->|"thành công · thu hồi mọi phiên khác"| S1
    Bank -->|"chọn ngân hàng"| BankList["Danh sách NAPAS<br/>có ô tìm kiếm"]

    Bank -.->|"ĐIỀU KIỆN TIÊN QUYẾT"| QR(["#18 Sheet QR<br/>của người trả cho bạn"])
```

---

## 8. Đọc ra được gì từ sơ đồ

**Điểm vào của app chỉ có hai:** #1 (đăng nhập) và deep link lời mời → #9. Mọi màn
còn lại đều nằm sau app shell.

**Đường găng dài 8 màn:** #1 → #5 → #7 → #11 → #12 → #13 → #14 → #15. Đây là việc
một người phải làm để nhóm có khoản nợ đầu tiên. Nếu demo bị bó thời gian (PRD §7
chỉ có 2 tuần), đây là chuỗi phải chạy trơn trước mọi thứ khác.

**Đường của người trả chỉ 4 chạm:** #16 → #17 → #18 → #19. Đúng như vậy — người nợ
là người ít động lực nhất trong hệ thống, luồng của họ phải ngắn nhất.

**Cánh cửa một chiều duy nhất** là #15 → `finalized`. Mọi luồng khác đều quay lui được.

**Ba màn có thể thành ngõ cụt** nếu không thiết kế đường thoát:
- #9 khi mã mời hết hạn hoặc hết lượt
- #12 khi OCR thất bại → phải rơi về #13 dạng nhập tay, không được văng về #11
- #17 khi khoản nợ bị `rejected` → phải hiện lý do và nút tạo QR mới

---

## 9. Một lỗ hổng trong PRD mà sơ đồ làm lộ ra

**Không có gì bắt buộc chủ nợ thiết lập tài khoản ngân hàng trước khi họ ứng tiền.**

Nhìn mục 7: `#22 Bank` là **điều kiện tiên quyết** của `#18` — nhưng #22 nằm ở tab 4,
hoàn toàn tách rời luồng tạo hoá đơn ở mục 4. Kịch bản vỡ:

1. Minh Anh đăng ký, bỏ qua tab Tài khoản (không có gì ép).
2. Minh Anh tạo nhóm, ứng tiền, chụp hoá đơn, gán món, **chốt hoá đơn** (#15).
3. Hệ thống sinh 4 dòng `debts` trỏ về Minh Anh.
4. Tuấn Lâm mở #16 → #17 → bấm "Tạo mã QR" → **#18 không sinh được VietQR**, vì
   `users.default_bank_code` và `default_bank_account_number` của Minh Anh đều NULL.

Bốn người bị kẹt vì một người bỏ trống một field, và họ phát hiện ra ở bước cuối
cùng chứ không phải bước đầu. FR 4.1.17 không nói xử lý ca này thế nào.

**Ba cách chặn, theo thứ tự tôi khuyến nghị:**

1. **Chặn tại #15.** Không cho chốt hoá đơn nếu chủ nợ chưa có tài khoản nhận tiền.
   Nêu rõ và cho đi thẳng tới #22 rồi quay lại. Đây là chỗ rẻ nhất để chặn — mới
   một người bị chặn, chưa ai bị kẹt.
2. **Cảnh báo tại #11.** Banner ngay khi bắt đầu tạo hoá đơn: "Bạn chưa có tài khoản
   nhận tiền — người khác sẽ không trả được cho bạn." Nhẹ hơn, nhưng bỏ qua được.
3. **Xử lý tại #18** (bắt buộc phải có dù chọn cách nào ở trên, vì luôn còn ca
   chủ nợ xoá thông tin NH sau khi đã chốt): thay mã QR bằng thông báo + nút
   "Nhắc Minh Anh cập nhật tài khoản nhận tiền". Không được để màn trắng hay lỗi kỹ thuật.

`#22` trong `design.md` đã có banner cảnh báo cho ca "chưa thiết lập", nhưng banner
đó chỉ hiện khi người dùng **tự mở** tab Tài khoản — mà người bỏ qua nó thì đúng
là người không mở. Cần chốt cách xử lý rồi bổ sung vào PRD §4.1.15 hoặc §4.1.17.
