# BÁO CÁO KẾT QUẢ DỰ ÁN PAYSPLIT

**Hệ thống chia hóa đơn & thanh toán nhóm thông minh**

| Mục | Nội dung |
| --- | --- |
| Nhóm thực hiện | Phạm Lê Hoàng Nam, Phạm Thanh Lam, Nguyễn Trọng Tín |
| Mentor | Trần Quang Hiển, Phan Công Huân, Bành Quốc Danh, Nguyễn Mạnh Tể, Nguyễn Nam Trường |
| Sản phẩm | Ứng dụng di động (iOS/Android) + Backend API + Trang quản trị |
| Mã nguồn | [PaySplit-BE](https://github.com/FintechVSF-Tranning/PaySplit-BE) · [PaySplit-FE](https://github.com/FintechVSF-Tranning/PaySplit-FE) |

**Cấu trúc báo cáo**
- **Phần I – Tổng quan** (mục 1–5): kết quả, tiến độ, rủi ro và đề xuất. Đọc trong khoảng 3 phút.
- **Phần II – Chi tiết kỹ thuật** (mục 6–12): kiến trúc, chức năng, giải pháp và quy trình. Dành cho người cần tìm hiểu sâu.

---

# PHẦN I – TỔNG QUAN

## 1. Tóm tắt

Sau 5 tuần, nhóm đã **hoàn thành bản MVP của PaySplit**: một ứng dụng giúp nhóm bạn chia tiền hóa đơn và đòi nợ mà không phải tính tay hay nhắc khó xử. Người dùng chụp hóa đơn, hệ thống tự đọc món, chia tiền cho từng người và sinh mã VietQR đúng số tiền để chuyển khoản.

**Kết quả nổi bật**
- ✅ **Luồng nghiệp vụ chạy thông suốt từ đầu đến cuối**: đăng ký → tạo nhóm → chụp hóa đơn → chia tiền → trả nợ qua VietQR → xác nhận → nhắc nợ.
- ✅ **9/9 hạng mục đã code xong** trên cả backend và ứng dụng di động, chỉ còn 3 bước kiểm thử/tài liệu nhỏ.
- ✅ **Tiền được chia chính xác đến từng đồng**, kể cả khi hóa đơn có VAT, phí dịch vụ và nhiều loại khuyến mãi.
- ✅ **Cập nhật theo thời gian thực**: kết quả quét hóa đơn, trạng thái thanh toán và thông báo hiện ngay trên app, không cần tải lại.
- ✅ **Backend đã chạy production** trên máy chủ Oracle Cloud, có HTTPS.

## 2. Bài toán & giá trị mang lại

| Vấn đề hiện tại khi chia tiền nhóm | PaySplit giải quyết |
| --- | --- |
| Tính tay từng món, chia VAT/phí/khuyến mãi dễ sai | Quét hóa đơn bằng AI OCR, hệ thống tự tính phần của từng người |
| Phải hỏi số tài khoản, gõ tay số tiền | Sinh mã **VietQR động** cho từng người, đúng số tiền và nội dung |
| Ngại nhắc nợ, dễ quên | **Tự động nhắc nợ** qua thông báo đẩy |
| Khó biết ai đã trả, ai chưa | Người nợ gửi biên lai, chủ nợ xác nhận, bảng công nợ nhóm luôn cập nhật |

PaySplit chỉ **điều phối** thanh toán ngang hàng (P2P) và **không giữ tiền** của người dùng, nên không phát sinh rủi ro pháp lý về trung gian thanh toán.

## 3. Phạm vi & tiến độ

| # | Hạng mục | Trạng thái | Ghi chú |
| --- | --- | --- | --- |
| 1 | Tài khoản & xác thực | ✅ Hoàn thành | |
| 2 | Quản lý nhóm | ✅ Hoàn thành | |
| 3 | Hóa đơn & quét OCR | 🟡 Đã code xong | Còn viết test cho bản sửa thuật toán làm tròn |
| 4 | Chia tiền & thanh toán VietQR | ✅ Hoàn thành | |
| 5 | Trang quản trị (Admin) | ✅ Hoàn thành | |
| 6 | Thông báo & hàng đợi xử lý nền | ✅ Hoàn thành | |
| 7 | Chốt sổ hóa đơn cả nhóm | 🟡 Đã code xong | Còn viết tài liệu |
| 8 | Tối ưu kết nối cơ sở dữ liệu | ✅ Hoàn thành | |
| 9 | Đồng bộ thời gian thực toàn app | 🟡 Đã code xong | Còn bước kiểm tra nghiệm thu |

**Chỉ số chính**

| Chỉ số | Giá trị |
| --- | --- |
| Tổng số commit | 280 (Backend 171 · Mobile 109) |
| Khối lượng mã nguồn (không tính code sinh tự động) | ~79.000 dòng (Go ~25.600 · Dart ~53.400) |
| File kiểm thử tự động | 158 (Backend 82 · Mobile 76) |
| API đã cung cấp | 65 endpoint |
| Tài liệu | PRD, Technical Design, 10 đặc tả tính năng, 16 biên bản review code |

## 4. Rủi ro, tồn đọng & đề xuất

**Tồn đọng kỹ thuật**
- Còn 3 bước kiểm thử/tài liệu của các hạng mục 3, 7, 9 (xem mục 3). Mỗi bước dự kiến mất 1–2 ngày.
- Chưa có CI/CD, việc deploy vẫn làm thủ công theo runbook.
- Chưa có dashboard giám sát và cảnh báo (metrics đã được xuất ra nhưng chưa có công cụ hiển thị).

**Rủi ro**

| Rủi ro | Mức độ | Hướng xử lý |
| --- | --- | --- |
| Phụ thuộc dịch vụ OCR bên thứ ba (LlamaExtract) về chi phí và độ ổn định | Trung bình | Đã có retry và tự dọn job lỗi. Nên đánh giá thêm OCR dự phòng |
| Dữ liệu cá nhân (số tài khoản, email) chưa mã hóa ở mức production | Cao nếu ra thị trường | Mã hóa dữ liệu nhạy cảm trước khi phát hành chính thức |
| Việc xác nhận đã nhận tiền vẫn phụ thuộc chủ nợ bấm tay | Thấp | Tích hợp webhook ngân hàng để tự động đối soát |

**Các điểm cần lãnh đạo/mentor quyết định**
1. Có bổ sung **đăng nhập bằng số điện thoại** cho phiên bản tiếp theo không?
2. Có đầu tư **mã hóa dữ liệu cá nhân và dịch vụ email giao dịch** cho production không?
3. Có triển khai **tự động đối soát qua webhook ngân hàng** không?

## 5. Kế hoạch tiếp theo

| Ưu tiên | Công việc |
| --- | --- |
| Ngắn hạn | Hoàn tất 3 bước kiểm thử/tài liệu còn lại. Thiết lập CI/CD và dashboard giám sát |
| Trung hạn | Mã hóa dữ liệu cá nhân, đăng nhập bằng số điện thoại, quy định số nhóm tối đa mỗi người được tham gia |
| Dài hạn | Tự động đối soát qua ngân hàng, nhắc nợ qua Zalo/Messenger, báo cáo chi tiêu cá nhân |

---

# PHẦN II – CHI TIẾT KỸ THUẬT

## 6. Kiến trúc tổng thể

```text
┌────────────────────┐   HTTPS/REST + SSE    ┌──────────────────────────────┐
│  Mobile App        │ ────────────────────▶ │  Caddy (HTTPS reverse proxy) │
│  Flutter (iOS/And) │ ◀──────────────────── └──────────────┬───────────────┘
└─────────▲──────────┘                                      │
          │ Push (FCM)                       ┌──────────────▼───────────────┐
          │                                  │  Backend API – Go            │
┌─────────┴──────────┐                       │  auth · group · bill ·       │
│ Firebase Cloud     │ ◀──────────────────── │  settlement · notification · │
│ Messaging          │                       │  admin (+ Admin Portal web)  │
└────────────────────┘                       │  River Queue workers         │
                                             └──┬──────────┬─────────┬──────┘
                        ┌───────────────────────┘          │         │
               ┌────────▼────────┐        ┌────────────────▼┐  ┌─────▼──────────────────┐
               │ PostgreSQL 18   │        │ LlamaExtract    │  │ Cloudinary · VietQR ·  │
               │ (dữ liệu, queue,│        │ (AI OCR)        │  │ Gmail SMTP             │
               │ LISTEN/NOTIFY)  │        └─────────────────┘  └────────────────────────┘
               └─────────────────┘
```

- **Backend – Clean Architecture theo module.** Mỗi module có 4 tầng `delivery/http → usecase → repository (interface) ← repository/postgres`. Tầng `domain` không phụ thuộc framework hay DB. Phần hạ tầng dùng chung (OCR, storage, queue, realtime, VietQR…) nằm trong `internal/platform/`.
- **Mobile – Clean Architecture + Feature-first.** Mỗi feature (`auth`, `home`, `groups`, `bills`, `settlement`, `notifications`, `profile`) chia thành `data / domain / presentation`. UI chỉ làm việc với Entity và UseCase.
- **Hợp đồng API** được định nghĩa tập trung trong `docs/openapi.yaml`. Response thống nhất dạng envelope `{success, data, message}` / `{success, error}`, field đặt tên theo snake_case.

## 7. Công nghệ sử dụng

| Thành phần | Công nghệ |
| --- | --- |
| Backend | Go, chi router, PostgreSQL 18 + pgx/v5, sqlc, Goose migration, River Queue, JWT + refresh token rotation, bcrypt |
| Mobile | Flutter/Dart, Riverpod, get_it + injectable, Dio + Retrofit, freezed, go_router, flutter_secure_storage, camera, mobile_scanner |
| Dịch vụ ngoài | LlamaExtract (OCR), Cloudinary (ảnh), VietQR, Gmail SMTP (OTP), Firebase Cloud Messaging |
| Hạ tầng | Docker Compose, Caddy, VM Oracle Cloud ARM64, Prometheus metrics |

## 8. Chức năng chi tiết theo module

| Module | Chức năng |
| --- | --- |
| **Tài khoản & xác thực** | Đăng ký, xác minh email bằng OTP 6 số, đăng nhập (mỗi tài khoản 1 thiết bị), access token 15 phút + refresh token 7 ngày có xoay vòng và phát hiện dùng lại token, quên/đổi mật khẩu, cập nhật hồ sơ và tài khoản ngân hàng, avatar WebP |
| **Nhóm** | Tạo/đổi tên/giải tán nhóm, mời thành viên qua link hoặc QR (Base62), chuyển quyền trưởng nhóm, rời nhóm (bị chặn khi còn nợ), nhật ký hoạt động, khóa/mở nhận hóa đơn |
| **Hóa đơn & OCR** | Tạo hóa đơn thủ công hoặc chụp nhiều ảnh, OCR chạy bất đồng bộ, sửa kết quả OCR có quản lý version, giảm giá theo món và giảm giá chung, gán món theo tỉ lệ, duyệt, chốt sổ, hủy và thay thế hóa đơn |
| **Chốt sổ cả nhóm** | Trưởng nhóm khóa nhận hóa đơn mới rồi chốt sổ hàng loạt. Mỗi hóa đơn xử lý độc lập, lỗi ở hóa đơn này không ảnh hưởng hóa đơn khác |
| **Chia tiền & thanh toán** | Bảng chi tiêu cá nhân, ma trận công nợ nhóm, gộp nợ nhiều hóa đơn vào một mã VietQR, gửi ảnh biên lai, chủ nợ xác nhận/từ chối, nhắc nợ thủ công (có cooldown) và tự động |
| **Thông báo** | Thông báo trong app và push FCM, deep link tới đúng màn hình, tự xóa FCM token hết hạn |
| **Realtime** | Toàn app dùng một kết nối SSE cho mỗi phiên: Home, nhóm, hóa đơn, OCR và thanh toán cập nhật tức thời. Khi mất kết nối, app đồng bộ bù qua `/sync` |
| **Quản trị** | Admin Portal nhúng trong backend: tìm kiếm/khóa/mở tài khoản kèm thu hồi phiên, ghi audit log, health check, biểu đồ số liệu runtime |

## 9. Các bài toán kỹ thuật & giải pháp

| Bài toán | Giải pháp |
| --- | --- |
| Chia tiền theo tỉ lệ và khuyến mãi bị lệch vài đồng | Tính bằng số hữu tỉ/số nguyên chính xác, phân bổ phần dư theo phương pháp **Largest Remainder (Hamilton)** với thứ tự cố định, kèm test hoán vị và test biên |
| Kết quả OCR không ổn định, job bị kẹt | Chuẩn hóa schema OCR, chạy qua River Queue có retry, không ghi đè khi người dùng đã sửa, tự dọn job kẹt ở `queued/processing` |
| Nhiều người thao tác cùng lúc (chốt sổ, hủy hóa đơn, thanh toán) | Khóa theo thứ tự cố định, dùng idempotency key và version, trả lỗi `409` khi xung đột |
| Hết kết nối DB khi deploy serverless | Chuyển sang VM. Mọi kênh realtime dùng chung một phiên PostgreSQL `LISTEN`, River chuyển sang chế độ poll |
| Gửi lại request khi mạng chập chờn gây trùng giao dịch | Idempotency key dạng UUIDv4 cho thanh toán và gửi biên lai |

## 10. Quy trình làm việc & đảm bảo chất lượng

- **Spec trước, code sau**: mỗi tính năng có đặc tả với tiêu chí nghiệm thu (AC) trong `docs/specs/`. Hợp đồng API được chốt trong OpenAPI trước khi hai bên BE và FE bắt đầu code.
- **Phát triển theo lát cắt dọc**: mỗi tính năng làm xuyên suốt DB → nghiệp vụ → API → app, xong lát này mới mở rộng.
- **Chu trình chất lượng cho mỗi tính năng**: Develop → Verify theo AC → Test → Review code chéo → Viết tài liệu. Có 16 biên bản review lưu trong `docs/reviews/`.
- **Ứng dụng AI agent**: dùng `AGENTS.md`/`CLAUDE.md` làm ngữ cảnh chung và bộ skill để tăng tốc viết spec, code, test và review.

## 11. Triển khai & vận hành

- Backend và PostgreSQL chạy chung trên **VM Oracle Cloud ARM64**, Caddy lo HTTPS. Có runbook deploy, script backup DB và image migration riêng.
- Lý do chọn VM thay vì serverless: River Queue, `LISTEN/NOTIFY` và SSE đều cần tiến trình chạy liên tục. Serverless làm số kết nối DB tăng theo số instance và không tắt được một cách an toàn (graceful shutdown).
- Có endpoint `/health` và `/metrics` (Prometheus) để theo dõi.

## 12. Phân công & bài học

| Thành viên | Backend | Mobile |
| --- | --- | --- |
| **Phạm Lê Hoàng Nam** | Auth & account, Split & settlement, Group bill close, realtime SSE theo người dùng, Admin, deploy production | Màn đối soát/thanh toán, realtime một kênh SSE, danh sách ngân hàng VietQR, sửa lỗi UI/camera |
| **Nguyễn Trọng Tín** | Middleware (CORS, rate limit, auth), cấu hình, River Queue, Notification + FCM, Bill & OCR | Giao diện đăng nhập/đăng ký, Home dashboard, Profile, chụp hóa đơn, đối chiếu OCR, push FCM, trung tâm thông báo |
| **Phạm Thanh Lam** | Phân trang, Group management, API admin, chuẩn hóa response envelope, đồng bộ nhóm realtime, bộ lọc hóa đơn, nhắc nợ, giao diện Admin Portal, tài liệu TDD | Dựng khung dự án Flutter theo Clean Architecture, nối màn Nhóm với API, `ApiResponse` wrapper, cooldown nhắc nợ, tìm kiếm nhóm, cơ chế phiên đăng nhập |

**Bài học rút ra**
- Áp dụng được Clean Architecture ở cả backend Go lẫn mobile Flutter.
- Xử lý bài toán liên quan đến tiền: tính toán chính xác, idempotency, giao dịch đồng thời, lưu vết hoạt động.
- Làm chủ xử lý bất đồng bộ, realtime (SSE, `LISTEN/NOTIFY`) và tích hợp dịch vụ bên ngoài.
- Làm việc nhóm theo quy trình: spec, review chéo, chốt hợp đồng API trước khi code, cộng tác cùng AI agent.
- Tự deploy và vận hành hệ thống thực tế.

---

**Phụ lục – Tài liệu tham chiếu** (trong repo `PaySplit-BE/docs/`): `Product_Requirement_Document.md`, `Technical_Design_Document.md`, `openapi.yaml`, `screen_flow.md`, `specs/`, `reviews/`, `scope/scope.md`, `../deploy/README.md`.
