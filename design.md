# Design — PaySplit (Flutter mobile)

> Hallmark · pre-emit critique: P5 H5 E4 S5 R5 V4
> Hallmark · genre: modern-minimal · theme: Cobalt (adapted for Vietnamese type)
> · axes: cool-light paper / grotesk-sans display / electric-cobalt accent
> · nav: bottom tab bar (mobile) · enrichment: none — typography only

Đây là **hệ thống thiết kế đã khoá** cho client Flutter của PaySplit. Mọi phiên build
FE đọc file này trước. Sửa file này có chủ đích — file là luật, không phải gợi ý.

Nguồn context: `PRD/Product_Requirement_Document.md` (FR 4.1.1–4.1.23, NFR 5.1.1
UI-01…UI-04, 5.2.4 EXP-01…03) và `Database/dbv1.sql` (enum trạng thái, mô hình gộp nợ).

---

## 1. Sản phẩm — thứ quyết định mọi lựa chọn hình thức

PaySplit **không giữ tiền**. Nó là dịch vụ *điều phối thanh toán*: tính ai nợ ai bao
nhiêu, sinh VietQR, rồi để chủ nợ tự xác nhận đã nhận. Ba hệ quả trực tiếp lên UI:

1. **Con số là nhân vật chính, không phải minh hoạ.** Mỗi màn hình phải trả lời được
   "bao nhiêu / cho ai / vì hoá đơn nào" trong một lần liếc.
2. **Không được hứa hẹn thay hệ thống.** Người trả bấm "Tôi đã chuyển" — nút đó
   *không* tất toán nợ. Chỉ chủ nợ mới đóng được. Nhãn và màu phải phản ánh đúng
   điều đó, nếu không app đang nói dối người dùng về tiền của họ.
3. **Mọi khoản nợ phải truy ngược được** về hoá đơn và từng món (EXP-03). Không có
   con số nào trong app được phép là hộp đen.

**Audience** · người Việt đi ăn/du lịch theo nhóm, tuổi 18–35, quen app ngân hàng.
**Use case chính** · người nợ mở app → thấy mình nợ ai bao nhiêu → quét QR → nộp
bằng chứng. Mọi thứ khác là phụ trợ cho luồng đó.
**Tone** · utilitarian / technical. Giao diện như một biên lai được in đẹp, không
như một app fintech vui vẻ.

---

## 2. Tokens (canonical)

Anchor hue **256** (cool). Mọi neutral đều nhuốm hue này — không có xám vô sắc.

```css
/* ── Light (default) ─────────────────────────────────────────── */
:root {
  /* Surfaces — không bao giờ #fff */
  --color-paper:        oklch(98.5% 0.004 250);  /* nền app */
  --color-paper-2:      oklch(96.5% 0.006 252);  /* card, list row nhấn */
  --color-paper-3:      oklch(93.5% 0.008 254);  /* input fill, pressed */
  --color-graphite:     oklch(22%   0.016 260);  /* dải tối duy nhất: QR sheet */

  /* Ink — không bao giờ #000 */
  --color-ink:          oklch(24%   0.020 258);  /* tiêu đề, số tiền */
  --color-ink-2:        oklch(34%   0.018 257);  /* body */
  --color-ink-3:        oklch(52%   0.014 256);  /* meta, caption, hint */
  --color-ink-inverse:  oklch(96%   0.006 256);  /* chữ trên graphite */

  /* Hairline — cấu trúc do đường kẻ tạo ra, không do bóng đổ */
  --color-rule:         oklch(89%   0.008 254);
  --color-rule-strong:  oklch(80%   0.010 254);

  /* Accent — MỘT tín hiệu duy nhất, ≤5% mọi viewport */
  --color-accent:       oklch(58%   0.20  256);
  --color-accent-ink:   oklch(99%   0.004 256);  /* chữ trên accent */
  --color-accent-wash:  oklch(95%   0.030 256);  /* nền chip active, rất nhạt */
  --color-focus:        oklch(58%   0.20  256);

  /* Semantic — trạng thái công nợ. Chỉ dùng ở chip/dot, KHÔNG làm nền mảng */
  --color-warn:         oklch(70%   0.14  75);   /* pending_confirmation */
  --color-warn-wash:    oklch(96%   0.035 80);
  --color-stall:        oklch(62%   0.15  45);   /* stalled_confirmation */
  --color-stall-wash:   oklch(95%   0.035 45);
  --color-danger:       oklch(56%   0.17  25);   /* rejected, huỷ, lỗi */
  --color-danger-wash:  oklch(96%   0.030 25);
  --color-success:      oklch(52%   0.13  155);  /* settled */
  --color-success-wash: oklch(95%   0.030 155);

  /* Type — cả ba face đều free, và display+body phủ đủ dấu tiếng Việt */
  --font-display: "Be Vietnam Pro", system-ui, sans-serif;  /* 600/700 */
  --font-body:    "IBM Plex Sans", system-ui, sans-serif;   /* 400/500 */
  --font-mono:    "JetBrains Mono", ui-monospace, monospace;/* 400/500 */

  /* Scale 1.25 (major third), gốc 16px */
  --text-xs:   0.75rem;   /* 12 — chỉ cho nhãn mono UPPERCASE */
  --text-sm:   0.875rem;  /* 14 — caption, meta */
  --text-base: 1rem;      /* 16 — sàn cho body, không thấp hơn */
  --text-md:   1.25rem;   /* 20 — tiêu đề card, tên nhóm */
  --text-lg:   1.5rem;    /* 24 — tiêu đề màn hình */
  --text-xl:   2rem;      /* 32 — số tiền tổng trong list */
  --text-figure: 2.75rem; /* 44 — CON SỐ ANH HÙNG: 1 lần / màn hình */

  /* Spacing 4-pt */
  --space-3xs: 2px;  --space-2xs: 4px;  --space-xs: 8px;
  --space-sm: 12px;  --space-md: 16px;  --space-lg: 24px;
  --space-xl: 32px;  --space-2xl: 48px; --space-3xl: 64px;

  /* Radii — "kẻ bằng thước", không bo tròn mềm */
  --radius-control: 8px;   /* button, input, chip */
  --radius-card:    12px;
  --radius-sheet:   16px;  /* chỉ 2 góc trên của bottom sheet */
  --radius-avatar:  999px; /* ngoại lệ duy nhất */

  /* Motion */
  --ease-out:    cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
  --dur-fast: 140ms;  --dur-base: 200ms;  --dur-slow: 280ms;

  /* Elevation — chỉ 2 mức, và chỉ cho lớp nổi thật sự */
  --shadow-sheet: 0 -2px 16px oklch(24% 0.02 258 / 0.08);
  --shadow-fab:   0 2px 8px  oklch(24% 0.02 258 / 0.12);
}

/* ── Dark ────────────────────────────────────────────────────── */
/* Cùng anchor hue 256. Chỉ lightness/chroma đổi, hue không đổi. */
:root[data-theme="dark"] {
  --color-paper:        oklch(15%   0.012 258);
  --color-paper-2:      oklch(18.5% 0.014 258);  /* nổi hơn = SÁNG hơn */
  --color-paper-3:      oklch(22%   0.016 258);
  --color-graphite:     oklch(11%   0.010 260);

  --color-ink:          oklch(94%   0.006 256);
  --color-ink-2:        oklch(84%   0.008 256);
  --color-ink-3:        oklch(64%   0.010 256);
  --color-ink-inverse:  oklch(18%   0.014 258);

  --color-rule:         oklch(28%   0.012 256);
  --color-rule-strong:  oklch(38%   0.012 256);

  --color-accent:       oklch(68%   0.17  256);  /* +L, −C theo công thức dark */
  --color-accent-ink:   oklch(13%   0.012 258);
  --color-accent-wash:  oklch(26%   0.045 256);
  --color-focus:        oklch(72%   0.17  256);

  --color-warn:    oklch(78% 0.12 75);   --color-warn-wash:    oklch(26% 0.040 78);
  --color-stall:   oklch(72% 0.13 45);   --color-stall-wash:   oklch(26% 0.045 45);
  --color-danger:  oklch(66% 0.15 25);   --color-danger-wash:  oklch(25% 0.045 25);
  --color-success: oklch(64% 0.11 155);  --color-success-wash: oklch(24% 0.035 155);
}
```

**Body weight ở dark mode giảm 50 đơn vị** (400 → 350) để bù độ đậm quang học.

---

## 3. Typography — luật dùng

| Vai trò | Face | Weight | Size | Ghi chú |
|---|---|---|---|---|
| Tiêu đề màn hình | display | 700 | `--text-lg` | tracking `-0.02em` |
| Tên nhóm / tên hoá đơn | display | 600 | `--text-md` | |
| Body, mô tả | body | 400 | `--text-base` | line-height 1.55 |
| Caption, meta, thời gian | body | 400 | `--text-sm` | màu `--color-ink-3` |
| **Nhãn máy** (trạng thái, mã, kbd) | mono | 500 | `--text-xs` | UPPERCASE, tracking `0.06em` |
| **Số tiền trong danh sách** | mono | 500 | `--text-base`→`--text-xl` | `tabular-nums` bắt buộc |
| **Con số anh hùng** (tổng nợ) | display | 700 | `--text-figure` | `tabular-nums`, 1 lần/màn |
| **Mã tham chiếu** | mono | 500 | `--text-base` | tracking `0.08em`, luôn kèm nút copy |

Ba face là **trần cứng**. Không thêm face thứ tư.

**Vì sao lệch khỏi spec Cobalt gốc:** Cobalt chỉ định Space Grotesk + Inter +
JetBrains Mono. Space Grotesk **không có bộ dấu tiếng Việt** — mà UI-01 bắt buộc
default là tiếng Việt, nên display sẽ vỡ dấu ngay dòng tiêu đề đầu tiên. Be Vietnam
Pro giữ đúng register grotesk hơi cơ khí của Cobalt và được thiết kế cho tiếng Việt.
IBM Plex Sans thay Inter ở body vì cùng lý do phủ dấu + là body kỹ thuật trong
allowlist. JetBrains Mono giữ nguyên vì chỉ chạm số và ASCII.

**Bắt buộc kỹ thuật**
- `font-variant-numeric: tabular-nums` trên **mọi** container hiển thị tiền, số lượng, phần trăm.
- `font-display: swap`; khai báo fallback metrics để tránh CLS.
- Sàn body 16px. Không có chữ nào dưới 12px.
- Dấu câu thật: `…` không phải `...`, `—` không phải `--`, nháy cong `" "`.

---

## 4. Định dạng dữ liệu (không thương lượng)

| Loại | Format | Ví dụ |
|---|---|---|
| Tiền VND | dấu chấm phân nhóm nghìn, khoảng trắng hẹp trước ₫, **không thập phân** | `245.000 ₫` |
| Tiền âm (bạn được nhận) | tiền tố `+`, màu `--color-success` | `+120.000 ₫` |
| Tiền dương (bạn phải trả) | tiền tố `−` (U+2212), màu `--color-ink` | `−245.000 ₫` |
| Ngày | `dd/MM/yyyy` | `13/08/2026` |
| Ngày + giờ | `HH:mm · dd/MM` | `19:42 · 13/08` |
| Thời gian tương đối | dùng dưới 24h, sau đó chuyển ngày tuyệt đối | `3 giờ trước` |
| Mã tham chiếu | UPPERCASE mono, chia nhóm 4 ký tự | `PSPL 8K2M 4QN7` |
| Số lượng món | ẩn nếu `= 1`, hiện `×2` nếu > 1 | `×2` |

BIGINT VND từ backend, **không bao giờ** đưa qua float ở client. Parse thẳng sang
`int`. REL-01 nói tổng phần chia phải khớp tuyệt đối tổng hoá đơn — client không
được làm tròn lại bất cứ thứ gì.

---

## 5. Trạng thái công nợ — bảng ánh xạ

Năm giá trị của enum `debt_status` trong `dbv1.sql`. Chip trạng thái **luôn gồm
icon + nhãn chữ**, không bao giờ chỉ có màu (người mù màu đỏ–lục là ~8% nam giới VN).

| DB enum | Nhãn VI | Màu | Icon | Hành động khả dụng |
|---|---|---|---|---|
| `awaiting` | Chờ thanh toán | `--color-ink-3` (trung tính) | `circle-dashed` | Người nợ: *Tạo mã QR* |
| `pending_confirmation` | Chờ xác nhận | `--color-warn` | `clock` | Chủ nợ: *Xác nhận* / *Từ chối* |
| `stalled_confirmation` | Quá hạn xác nhận | `--color-stall` | `alert-triangle` | Cả hai: nhắc lại |
| `rejected` | Bị từ chối | `--color-danger` | `x-circle` | Người nợ: *Tạo QR mới* (kèm lý do) |
| `settled` | Đã tất toán | `--color-success` | `check` | chỉ đọc |

**Trạng thái phổ biến nhất (`awaiting`) là trạng thái im lặng nhất.** Nếu mọi khoản
nợ đều rực màu thì không khoản nào nổi bật. Chỉ những gì cần *hành động của người
đang xem* mới được đeo màu.

`bill_status`: `draft` → chip viền đứt nét, nhãn `BẢN NHÁP`, mono. `finalized` →
không chip, thay bằng icon khoá + dòng meta `Đã chốt · 13/08/2026`. Hoá đơn đã chốt
là **bất biến** (REL-03): không hiển thị nút Sửa dạng disabled — bỏ hẳn nút đó và
thay bằng dòng giải thích *"Hoá đơn đã chốt. Sửa bằng cách huỷ và tạo lại."*

---

## 6. Component specs

### 6.1 Nút

| Loại | Nền | Chữ | Viền | Radius |
|---|---|---|---|---|
| Primary | `--color-accent` | `--color-accent-ink` | none | `--radius-control` |
| Secondary | trong suốt | `--color-ink` | 1px `--color-rule-strong` | `--radius-control` |
| Ghost | trong suốt | `--color-accent` | none | `--radius-control` |
| Destructive | trong suốt | `--color-danger` | 1px `--color-danger` | `--radius-control` |

Chiều cao chạm tối thiểu **48dp**. Padding ngang `--space-md`. **Không pill, không
gradient, không bo tròn mềm.** Tối đa **một** nút primary trên một màn hình.

**Tám trạng thái bắt buộc** cho mọi thành phần tương tác — không có ngoại lệ:

| State | Xử lý |
|---|---|
| default | như bảng trên |
| hover *(chỉ con trỏ thô)* | nền tối/sáng thêm 4% |
| focus | ring 2px `--color-focus`, offset 2px, **hiện tức thì — không transition** |
| pressed | `scale(0.98)` + nền `--color-paper-3`, `--dur-fast` |
| disabled | opacity 0.4, `pointer-events: none`, **kèm lý do bằng chữ bên cạnh** |
| loading | spinner inline thay nhãn, giữ nguyên bề rộng nút; **delay 150ms** mới hiện |
| error | viền `--color-danger` + dòng lỗi phía dưới |
| success | im lặng (xem §8 Motion) |

### 6.2 Thẻ công nợ — component quan trọng nhất của app

Đây là thứ người dùng mở app để xem. Bố cục hàng, không phải card lồng card:

```
┌─────────────────────────────────────────────┐
│  ●  Minh Anh                    −245.000 ₫  │   ← avatar · tên · số tiền (mono, tabular)
│     3 hoá đơn · Đà Lạt 08/2026              │   ← meta, ink-3, text-sm
│     ⏱ Chờ xác nhận                          │   ← chip trạng thái
├─────────────────────────────────────────────┤   ← hairline --color-rule
```

Luật:
- Số tiền **căn phải**, `tabular-nums`, để các hàng thẳng cột khi cuộn.
- Hàng có thể mở rộng (expand) tại chỗ để lộ từng hoá đơn con → từng món. Đây là
  cách app thoả EXP-01/EXP-03; **không** đẩy sang màn hình mới cho bước đầu tiên.
- Không viền bao quanh từng hàng. Hairline phân cách là đủ. **Không card-in-card.**
- Nếu một cặp (người nợ → chủ nợ) có nhiều hoá đơn, gộp thành **một** hàng với
  meta `N hoá đơn` — khớp mô hình gộp nợ 2 tầng trong `dbv1.sql` §7.

### 6.3 Chip trạng thái

Nền `*-wash`, chữ + icon màu `*` đặc, radius `--radius-control`, padding
`--space-2xs --space-xs`, font mono `--text-xs` UPPERCASE. Không viền.

### 6.4 Bottom sheet QR (UI-04: QR ≥ 250×250 px)

Bề mặt tối duy nhất của app — `--color-graphite`, radius `--radius-sheet` 2 góc trên.

Thứ tự dọc, từ trên xuống:
1. Số tiền — display 700 `--text-figure`, `--color-ink-inverse`, tabular-nums.
2. Tên + ngân hàng người nhận — body, `--color-ink-inverse` @ 0.75.
3. **Mã QR** — nền trắng thuần (bắt buộc để máy quét đọc được; đây là ngoại lệ
   *chức năng* duy nhất cho phép `#fff`), tối thiểu 280dp vuông, padding trắng 16dp.
4. **Mã tham chiếu** — mono, tracking rộng, kèm nút copy. Đây là thứ giúp chủ nợ
   đối chiếu thủ công (giảm thiểu R3); phải dễ đọc hơn mọi thứ khác trừ số tiền.
5. Nút primary *"Tôi đã chuyển"* → mở bước nộp bằng chứng.

**Không** re-draw khung điện thoại, khung app ngân hàng, hay bất kỳ chrome giả nào.

### 6.5 Màn hình gán món (bill item assignment)

Màn khó nhất. Mỗi dòng món: tên món trái, `×N` + đơn giá giữa, cụm avatar phải.
Chạm avatar để bật/tắt người gánh món. Chân màn hình cố định một thanh tổng kết
hiển thị **tổng đã gán / tổng hoá đơn** — nếu lệch, thanh chuyển `--color-warn`
kèm số chênh lệch. Người dùng không bao giờ được chốt hoá đơn trong trạng thái mù.

`mismatch_warning` từ OCR hiển thị dưới dạng banner hairline phía trên danh sách
món, không phải dialog — nó là thông tin cần đối chiếu, không phải lỗi chặn.

### 6.6 Input

Nền `--color-paper-3`, viền 1px `--color-rule`, radius `--radius-control`, cao 48dp.
Label **luôn nằm trên**, không dùng floating label, không dùng placeholder thay label.
Lỗi hiện **dưới** field, mono `--text-sm`, `--color-danger`, kèm icon.

Cấu trúc câu lỗi: *chuyện gì xảy ra → vì sao → làm gì tiếp*.
`"Không gửi được bằng chứng. Ảnh vượt quá 5 MB. Chọn ảnh nhỏ hơn hoặc chụp lại."`

### 6.7 Bottom navigation (UI-04)

4 tab, icon + nhãn chữ (luôn hiện nhãn, không chỉ icon):

`Nhóm` · `Công nợ` · `Hoạt động` · `Tài khoản`

Tab active: icon đặc + chữ `--color-accent`. Tab thường: icon nét + `--color-ink-3`.
Hairline `--color-rule` phía trên thanh. Không nền accent, không indicator pill.
Badge số đỏ chỉ trên `Hoạt động`, và chỉ khi có việc **cần người dùng hành động**
(chờ mình xác nhận / nợ bị từ chối) — không badge cho thông báo thuần thông tin.

---

## 7. Bản đồ màn hình → Use Case

| # | Màn hình | UC / FR | Ghi chú thiết kế |
|---|---|---|---|
| 1 | Đăng nhập | UC01 / 4.1.1 | Lỗi 401 dùng thông điệp chung, không tiết lộ email có tồn tại |
| 2 | Đăng ký | UC02 / 4.1.2 | Thanh độ mạnh mật khẩu inline, không dialog |
| 3 | Chờ xác minh email | 4.1.2 | Trạng thái rỗng có ý nghĩa + nút *Gửi lại* có cooldown hiện đếm ngược |
| 4 | Quên / đặt lại mật khẩu | UC03 / 4.1.3 | |
| 5 | Danh sách nhóm *(tab 1)* | UC07 | Mỗi nhóm hiện số dư ròng của **bạn** trong nhóm đó, không phải tổng nhóm |
| 6 | Tạo nhóm | UC07 / 4.1.7 | |
| 7 | Chi tiết nhóm | — | 3 sub-tab: Hoá đơn · Số dư · Nhật ký |
| 8 | Mời thành viên | UC09 / 4.1.8 | QR + link + mã; hiện rõ hạn dùng và số lượt còn lại |
| 9 | Tham gia nhóm | UC08 / 4.1.9 | Deep link → nếu chưa cài app thì rơi về trang tải |
| 10 | Quản lý thành viên | UC10 / 4.1.10 | Nút xoá bị chặn khi `net_balance ≠ 0` — **nêu rõ số dư còn lại**, không disable câm |
| 11 | Chụp / tải hoá đơn | UC11 / 4.1.11 | Overlay khung ngắm + hướng dẫn ánh sáng |
| 12 | OCR đang xử lý | UC12 / 4.1.12 | Skeleton của form hoá đơn, không spinner giữa màn. PERF-02 ≤10s → hiện tiến trình sau 3s |
| 13 | Soát & sửa hoá đơn | UC14 / 4.1.14 | Mọi ô OCR đều sửa được tại chỗ; ô có độ tin cậy thấp gạch chân đứt nét |
| 14 | Gán món cho thành viên | UC13 / 4.1.13 | §6.5 |
| 15 | Chốt hoá đơn | UC15 / 4.1.15 | Màn xem trước bất biến: ai nợ ai bao nhiêu, **kèm phần chênh lệch làm tròn** (EXP-01) |
| 16 | Công nợ của tôi *(tab 2)* | UC16 / 4.1.16 | 2 nhóm: *Tôi nợ* / *Nợ tôi*. Con số anh hùng = số dư ròng |
| 17 | Chi tiết khoản nợ | UC16 | Truy ngược tới từng món (EXP-03) |
| 18 | Bottom sheet QR | UC17 / 4.1.17 | §6.4 |
| 19 | Nộp bằng chứng | UC18 / 4.1.18 | Tải ảnh + ghi chú. Sau khi gửi, nợ sang `pending_confirmation` — **nói rõ là chưa xong** |
| 20 | Hộp chờ xác nhận (chủ nợ) | UC19 / 4.1.19 | Xem ảnh bằng chứng + đối chiếu mã tham chiếu. Từ chối **bắt buộc** nhập lý do |
| 21 | Hoạt động / thông báo *(tab 3)* | 4.2.1 | Từ `group_activities` + `notifications` |
| 22 | Hồ sơ & tài khoản NH *(tab 4)* | UC06 / 4.1.6 | Chọn mã NAPAS bằng list có tìm kiếm, không dropdown dài |
| 23 | Đổi mật khẩu / đăng xuất | UC04, UC05 | Cảnh báo rõ: đổi mật khẩu thu hồi mọi phiên khác |

---

## 8. Motion

Tư thế: **motion-cut**. App tiền bạc cần cảm giác tức thời, không cần biểu diễn.

- Chuyển màn: slide ngang `--dur-base` `--ease-out`. Bottom sheet: trượt lên `--dur-base`.
- Chip trạng thái đổi giá trị: crossfade `--dur-fast`. Không nảy, không scale.
- **Chỉ animate `transform` và `opacity`.** Không animate layout property.
- Focus ring hiện **tức thì**. Không bao giờ transition.
- `prefers-reduced-motion` / `MediaQuery.disableAnimations` → mọi chuyển động không
  gian rút về crossfade opacity ≤150ms.

**Thành công thì im lặng.** Xác nhận đã nhận tiền → hàng đó đổi sang `Đã tất toán`
tại chỗ. Không toast "Thành công!", không confetti, không haptic ăn mừng. Toast chỉ
dành cho: thất bại, tác vụ bất đồng bộ không thấy kết quả, và hành động có Undo.

**Optimistic + Undo** thay cho dialog xác nhận với mọi thao tác đảo ngược được
(xoá món nháp, bỏ gán thành viên). Dialog chỉ dành cho: chốt hoá đơn (bất biến),
rời nhóm, xoá tài khoản.

---

## 9. Copy

Tiếng Việt là mặc định (UI-01). Xưng hô: **"bạn"**, không "quý khách", không "anh/chị".

- **Nút là động từ + tân ngữ cụ thể.** `Tạo mã QR`, `Xác nhận đã nhận`, `Chốt hoá đơn`.
  Không `Tiếp tục`, `Xong`, `OK`, `Gửi`.
- **Nhãn phải nói đúng sự thật về hệ thống.** Nút của người nợ là `Tôi đã chuyển` —
  **không phải** `Thanh toán` hay `Trả nợ`. PaySplit không chuyển tiền; nói khác đi
  là hứa hẹn điều app không làm được.
- Trạng thái rỗng nêu bước tiếp theo, không nêu sự vắng mặt.
  `"Chưa có hoá đơn nào. Chụp biên lai để bắt đầu chia tiền."`
- Cấm: *tối ưu, đột phá, nền tảng, giải pháp toàn diện, trải nghiệm liền mạch*.
- Không bịa số. Không có "tiết kiệm 5 giờ mỗi tuần" ở bất cứ đâu.

---

## 10. Responsive & a11y

- Phủ **5"–10"** không cuộn ngang (UI-01). Kiểm ở bề rộng logic 320 / 360 / 414 / 768.
- Nhãn nút và tab **không bao giờ xuống 2 dòng**. Nhãn dài thì rút ngắn, không wrap.
- Vùng chạm tối thiểu 48×48dp.
- Tương phản: body ≥ 4.5:1, ranh giới UI ≥ 3:1. Chip `*-wash` + chữ `*` đặc đã đạt
  ở cả hai theme — kiểm lại nếu đổi giá trị token.
- Mọi ảnh (biên lai, bằng chứng) có `semanticLabel`.
- Số tiền đọc được bởi screen reader dưới dạng chữ: `"âm hai trăm bốn mươi lăm nghìn đồng"`.
- Toàn bộ luồng thao tác được bằng bàn phím ngoài / TalkBack / VoiceOver.

---

## 11. Cấm tuyệt đối

Đây là danh sách những thứ khiến FE trông như do máy sinh ra. Không có ngoại lệ.

1. **Header nền xanh đặc.** Đây là dấu vân tay của mọi app ngân hàng VN. Accent
   cobalt là *tín hiệu*, không phải mảng nền. ≤5% mọi viewport.
2. Gradient tím→xanh, gradient trên chữ, aurora blob, orb trôi nổi.
3. `#000` hoặc `#fff` — trừ đúng một chỗ: nền của mã QR (§6.4), vì máy quét cần nó.
4. Card lồng card. Chọn một lớp chứa.
5. Thẻ có sọc màu dày một bên (4–6px).
6. Lưới 3 cột icon-trên-tiêu-đề-trên-mô-tả.
7. Emoji thay icon (`✨` `🚀` `⚡` `✅`). Một bộ icon duy nhất cho cả app.
8. Glassmorphism, bóng đổ phát sáng trên nền tối. Nền tối nổi bằng **độ sáng**.
9. Easing nảy / đàn hồi trên UI. Chỉ ba easing đã đặt tên ở §2.
10. `transition-all`.
11. Bảng số không có `tabular-nums`.
12. Chữ nghiêng trong tiêu đề.
13. Eyebrow/số thứ tự mục (`01 · CÔNG NỢ`) — mặc định TẮT.
14. Toast ăn mừng khi thành công.
15. Dialog xác nhận cho thao tác đảo ngược được.
16. Giá trị màu hoặc font viết thẳng trong widget. Mọi thứ đi qua token có tên.
17. Khung trình duyệt giả, khung điện thoại giả, khung app ngân hàng giả.
18. Chỉ dùng màu để phân biệt trạng thái — luôn kèm icon + chữ.

---

## 12. Exports — Flutter

Token gốc là khối CSS ở §2 (để Hallmark đọc lại ở lần chạy sau). Bản dịch sang Dart
để dùng trực tiếp. Dart chưa có OKLCH gốc → dùng giá trị sRGB đã chuyển đổi; nếu sửa
token ở §2 thì chuyển đổi lại, đừng chỉnh tay hai nơi.

```dart
// lib/theme/tokens.dart
import 'package:flutter/material.dart';

abstract final class PsColor {
  // Light
  static const paper       = Color(0xFFF9FAFC);
  static const paper2      = Color(0xFFF1F3F7);
  static const paper3      = Color(0xFFE6E9F0);
  static const graphite    = Color(0xFF22252E);
  static const ink         = Color(0xFF262A35);
  static const ink2        = Color(0xFF474C5A);
  static const ink3        = Color(0xFF787E8E);
  static const inkInverse  = Color(0xFFF2F4F8);
  static const rule        = Color(0xFFDCE0E8);
  static const ruleStrong  = Color(0xFFBFC5D2);
  static const accent      = Color(0xFF2C6BE8);
  static const accentInk   = Color(0xFFFCFDFF);
  static const accentWash  = Color(0xFFE7EEFD);
  static const warn        = Color(0xFFC98A17);
  static const warnWash    = Color(0xFFFBF2E1);
  static const stall       = Color(0xFFC4622A);
  static const stallWash   = Color(0xFFFAEDE5);
  static const danger      = Color(0xFFC0392F);
  static const dangerWash  = Color(0xFFFAE9E7);
  static const success     = Color(0xFF2C7A57);
  static const successWash = Color(0xFFE4F2EB);
}

abstract final class PsSpace {
  static const xs3 = 2.0;  static const xs2 = 4.0;  static const xs = 8.0;
  static const sm  = 12.0; static const md  = 16.0; static const lg = 24.0;
  static const xl  = 32.0; static const xl2 = 48.0; static const xl3 = 64.0;
}

abstract final class PsRadius {
  static const control = 8.0;
  static const card    = 12.0;
  static const sheet   = 16.0;
}

abstract final class PsDur {
  static const fast = Duration(milliseconds: 140);
  static const base = Duration(milliseconds: 200);
  static const slow = Duration(milliseconds: 280);
}

/// Tương đương --ease-out. Dùng cho mọi chuyển động vào.
const psEaseOut = Cubic(0.16, 1, 0.3, 1);

abstract final class PsType {
  static const display = 'Be Vietnam Pro';
  static const body    = 'IBM Plex Sans';
  static const mono    = 'JetBrains Mono';

  /// Bắt buộc cho mọi số tiền.
  static const tabular = <FontFeature>[FontFeature.tabularFigures()];
}
```

`pubspec.yaml` — cả ba face đều trên Google Fonts, đều free thương mại:

```yaml
# Be Vietnam Pro: 600, 700   (display — có đủ dấu tiếng Việt)
# IBM Plex Sans:  400, 500   (body — có đủ dấu tiếng Việt)
# JetBrains Mono: 400, 500   (số, mã — chỉ ASCII nên không cần dấu)
```

Cần export sang định dạng khác (DTCG `tokens.json`, Tailwind `@theme` cho admin web
sau này), nói *"extend design.md with <format> exports"*.

---

## 13. Notes

- **Chưa emit `tokens.css` riêng.** Hallmark mặc định ghi `tokens.css` ở project
  root, nhưng đây là repo Go + Flutter — một file CSS đứng lẻ sẽ là rác. Token
  canonical nằm ở §2, bản dùng được nằm ở §12. Nếu sau này làm admin web, tách §2
  ra `tokens.css` lúc đó.
- **Admin dashboard (UC20–23) chưa nằm trong file này** theo scope bạn chọn. Khi
  làm, thêm mục `## Variants` vào file này thay vì dựng hệ thống riêng — Cobalt
  vốn là theme cho instrument panel, nó sẽ mở rộng sang dashboard rất thẳng.
- **Landing page cũng ngoài scope.**
- Dark mode không có trong PRD nhưng token đã sẵn ở §2. Nếu cắt để kịp deadline
  2 tuần (§7 PRD), cắt phần render chứ đừng cắt token — thêm lại sau sẽ rẻ.
