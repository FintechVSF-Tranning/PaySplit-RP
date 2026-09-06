# Báo cáo khám phá PaySplit-FE (raw)

> **Tài liệu lịch sử, không đại diện HEAD ngày 06/09/2026.** Nội dung explore nguyên văn bên dưới được giữ để truy nguyên; số dòng và một số kết luận đã cũ. Đọc [đối chiếu hiện tại](2026-09-06-flow-sync.md) và [flow 01–08](../README.md) trước khi dùng. Các thay đổi về SSE, notification, unlock, giới hạn nhóm và idempotency được mô tả ở tài liệu mới.

> Nguyên văn kết quả của subagent explore (nghiên cứu codebase Flutter frontend tại `PaySplit-FE`, mức độ very thorough). Dùng làm nguồn tham chiếu thô cho các file flow `01–07`.

---

Đã khảo sát xong toàn bộ codebase. Dưới đây là báo cáo nghiên cứu đầy đủ.

**Kiến trúc tổng thể**: Clean Architecture + Feature-First. DI bằng `get_it` + `injectable` (`lib/di/injection.dart:13` — `configureDependencies()` gọi trong bootstrap). State: Riverpod (mix `riverpod_annotation` và `StateNotifier` thuần). Routing: `go_router`. Mạng: `Dio` + `retrofit` (chỉ auth & groups dùng Retrofit; bills/settlement/notifications gọi Dio trực tiếp). Error: `Either<Failure, T>` qua `fpdart`.

## 0. KHỞI ĐỘNG APP & SPLASH FLOW

### Bootstrap (`lib/bootstrap.dart`)
- `bootstrap()` (:11-22): `WidgetsFlutterBinding.ensureInitialized()` → `EnvConfig.init(flavor, apiBaseUrl, appName)` → `configureDependencies()` (injectable) → `runApp(ProviderScope(App()))`.
- **Không có logic kiểm tra token nào ở đây** — việc check token hoàn toàn do router redirect + `AuthController.build()`.
- Entry points: `main.dart`, `main_development/staging/production.dart` — đều truyền `Flavor` + `API_BASE_URL` (dart-define, default `http://localhost:8080/api/v1`). `EnvConfig` (`core/config/env_config.dart`) là static config; `isProduction` tắt `PrettyDioLogger`.
- Dio client (`core/network/dio_client.dart:12-30`): timeout 90s cả 3 loại, gắn `AuthInterceptor`.

### Splash Page (`features/splash/presentation/pages/splash_page.dart`)
- **Chỉ là UI animation** (glow pulse, logo scale+shimmer, tagline) — không chứa logic điều hướng hay đọc storage.
- Logic khởi động nằm ở 2 nơi:
  1. **`AuthController.build()`** (`features/auth/presentation/providers/auth_controller.dart:28-35`): chạy song song `GetCurrentUserUseCase` (GET `/users/me` với token từ secure storage) và delay 2.5s (giữ splash đủ lâu). Kết quả: user (đã đăng nhập) hoặc `null` (token hết hạn/lỗi).
  2. **Global redirect của GoRouter** (`app/router/app_router.dart:54-85`):
     - `authState.isLoading` → `return null` (ở lại splash, chờ API /users/me trả về).
     - Chưa auth + đang tới `/splash` → chuyển `/welcome`; chưa auth + route protected → `/welcome`.
     - Đã auth + đang ở `/splash` hoặc route auth → `/home`.
- Router lắng nghe thay đổi auth qua `_GoRouterRefreshNotifier` (:35-45) → `refreshListenable`.

## 1. ROUTING & GUARDS (`lib/app/router/`)

### Bảng path → page (`app_routes.dart` + `app_router.dart`)

| Path | Page | Vị trí |
|---|---|---|
| `/splash` | SplashPage | ngoài shell |
| `/welcome` | WelcomePage | ngoài shell |
| `/login` (extra: bool resetSuccess) | LoginPage | ngoài shell |
| `/register` | RegisterPage | ngoài shell |
| `/verify-otp` (extra: email String) | VerifyOtpPage | ngoài shell |
| `/forgot-password` | ForgotPasswordPage | ngoài shell |
| `/reset-password` (extra: email) | ResetPasswordPage | ngoài shell |
| `/home` | HomePage | Shell branch 0 |
| `/groups` | GroupsPage | Shell branch 1 |
| `/bills` và `/settlement` (extra: SettlementTab) | SettlementPage(initialTab) | Shell branch 2 (cùng page!) |
| `/profile`, `/edit-profile`, `/bank-settings`, `/change-password` | Profile* pages | Shell branch 3 |
| `/groups/:groupId` (extra: GroupEntity) | GroupDetailPage | full-screen ngoài shell (:187-212), fallback group "Đang tải..." nếu thiếu extra |
| `/groups/:groupId/add-members` (extra: GroupEntity) | AddMembersPage | con của trên |
| `/scan-bill` (extra: Map{groupId, groupName}) | BillCapturePage | redirect về `/bills` nếu thiếu groupId (:215-222) |
| `/bill-detail` (extra: BillDetailEntity \| Map{bill/billId/groupId/autoStartOcr...}) | BillDetailPage(autoStartOcr khi photos≠empty và items=empty) | validate extra kỹ (:232-293) |
| `/notifications` | NotificationsPage | full-screen |

- **Bottom nav**: `MainNavigationShell` (`main_navigation_shell.dart`) — StatefulShellRoute 4 branch, giữ state từng tab bằng Stack + AnimatedOpacity (không rebuild khi đổi tab); nav bar 4 item: Tổng quan/Nhóm/Hóa đơn/Cài đặt (`app_bottom_nav_bar.dart:38-55`).
- **Guards**: duy nhất global `redirect` mô tả ở mục Splash. Route con của groups/settlement không guard riêng.
- **Deep link**: KHÔNG có cấu hình deep link/app link. `AndroidManifest.xml` chỉ có intent-filter MAIN/LAUNCHER + quyền INTERNET; iOS Info.plist không có scheme. Lời mời nhóm dạng link `paysplit.app/j/<code>` chỉ được **dán tay vào sheet** (`join_by_link_bottom_sheet.dart:228` hint text).

## 2. CORE NETWORK & ERROR HANDLING

### Token storage (`core/network/token_storage.dart`)
- `FlutterSecureStorage`: keys `access_token`, `refresh_token` (`constants/storage_keys.dart`); `getOrCreateDeviceId()` sinh UUID v4 lưu lần đầu (:18-26); `clear()` xoá cả 2 token.

### AuthInterceptor — refresh 401 flow (`core/network/interceptors/auth_interceptor.dart`)
- **onRequest** (:49-55): gắn `Authorization: Bearer <accessToken>` cho mọi request.
- **onError** (:58-88): chỉ thử refresh khi `statusCode == 401` VÀ path không thuộc `_skipRefreshPaths` = {login, register, refresh, forgot-password, reset-password, verify-email, resend-verification} (:38-46) VÀ chưa retry (`_retriedFlag` chống vòng lặp vô hạn :34).
- **Single-flight refresh** (:25-30): field `_refreshing` (Future<bool>?) — nhiều request 401 đồng thời chờ chung 1 future, tránh gọi refresh song song làm hỏng rotation (BE coi là reuse → thu hồi phiên).
- **Refresh fail** (:77-81) hoặc **401 không thể refresh** (:66-71): `await _tokenStorage.clear()` rồi next(err) → AuthController sau đó sẽ fail getCurrentUser → state null → router redirect về `/welcome`. **Lưu ý**: không có cơ chế force-navigate tức thời từ interceptor; logout thực sự phụ thuộc lần build/read tiếp theo của AuthController.
- `_refresh()` (:92-125): Dio RIÊNG không interceptor, POST `/auth/refresh` body `{refresh_token, device_id}`; parse envelope `{data:{access_token, refresh_token}}`; lưu token mới.
- `_retry()` (:127-138): fetch lại request cũ với header Authorization mới + flag retried.

### Error mapping (`core/network/dio_failure_mapper.dart`)
- `mapDioError()` (:59-111): connectionTimeout/sendTimeout/receiveTimeout/connectionError → `NetworkFailure("Không thể kết nối tới máy chủ...")`; badResponse 401/403 → `UnauthorizedFailure`; 400/422 → `ValidationFailure` (kèm `fields` map từ `error.details` hoặc `fields` cũ — đọc khoan dung :133-148); còn lại → `ServerFailure`; cancel → UnexpectedFailure.
- Bảng ~30 mã lỗi BE → message tiếng Việt (:5-57): EMAIL_EXISTS, INVALID_CREDENTIALS, EMAIL_NOT_VERIFIED, RATE_LIMITED, SESSION_REVOKED, INVALID_CURRENT_PASSWORD, GROUP_NOT_FOUND, INVITE_NOT_FOUND, CAPTAIN_REQUIRED, CAPTAIN_TRANSFER_REQUIRED, GROUP_MEMBER_HAS_OPEN_DEBTS, VERSION_CONFLICT (dùng ở bills notifier), v.v.
- `ApiResponse<T>` (`core/network/api_response.dart:14-37`): parse khoan dung — body không có key `success` coi nguyên body là data; `requireData` ném StateError khi null.
- `invalidResponseFailure` (`core/error/failures.dart:56`): dành cho body 2xx sai shape.
- **NetworkInfo** (`core/network/network_info.dart`) đăng ký DI nhưng **không repository nào dùng** → offline detection thực tế dựa trên DioException.connectionError.

## 3. AUTH FEATURE

### Pages & flows
- **WelcomePage** (`welcome_page.dart`): onboarding carousel 3 slide (OCR / chia tiền nhóm / VietQR), nút mũi tên cuối cùng → `context.push(login)` (:44-53). Không có "skip đã xem" (key `onboarding_seen` trong StorageKeys chưa được dùng).
- **LoginPage** (`login_page.dart`):
  - Form validate client-side: email bắt buộc, phải chứa `@` và `.` (:297-301); password bắt buộc (:313-316).
  - `ref.listen` authController (:86-109): error code `EMAIL_NOT_VERIFIED` → hiện banner warning kèm link sang `/verify-otp` (extra: email); code `RATE_LIMITED` → khởi động timer đếm ngược **900s (15 phút)** khóa nút submit + banner đỏ (:96-99, :266-288); lỗi khác → SnackBar đỏ.
  - Nhận `resetSuccess` (extra bool) để hiện alert xanh "Đặt lại mật khẩu thành công" (:196-218).
- **RegisterPage** (`register_page.dart`):
  - Validate: họ tên ≥2 ký tự (:151-155); email như trên; mật khẩu ≥8 + widget `PasswordChecklist` realtime (8–72 ký tự, chữ hoa, chữ thường, chữ số — `core/widgets/password_checklist.dart:16-21`); SĐT regex `^(0[3\|5\|7\|8\|9])[0-9]{8}$`, digitsOnly, maxLength 11 (:218-228); checkbox điều khoản bắt buộc (:49-57).
  - Thành công → `context.push(verifyOtp, extra: email)` (:74). Lỗi → SnackBar (message từ Failure).
- **VerifyOtpPage** (`verify_otp_page.dart`): Pinput 6 ô, auto-submit `onCompleted` (:318); countdown 60s gửi lại (:51-68); resend qua `resendVerification`; verify thành công → haptic + `context.go(login)` (:132); OTP sai → SnackBar đỏ + rung (:135). Copy hiển thị "OTP hiệu lực 10 phút, tối đa 5 lần thử".
- **ForgotPasswordPage** (`forgot_password_page.dart:36-66`): email → `forgotPassword` → push `/reset-password` (extra email).
- **ResetPasswordPage** (`reset_password_page.dart:44-78`): OTP 6 số + mật khẩu mới (+checklist) + xác nhận khớp → `resetPassword` → `context.go(login, extra: true)`.

### State & UseCases
- `AuthController` (riverpod AsyncNotifier, `auth_controller.dart`): state `AsyncValue<UserEntity?>`. Methods: login/register/verifyEmail/resendVerification/forgotPassword/resetPassword/changePassword/updateProfile/uploadAvatar/deleteAvatar/logout/devSignIn (debug only, fake user :156-161). Các method action **throw Failure** để UI catch.
- UseCases (`features/auth/domain/usecases/`): LoginUseCase(LoginParams{email,password}), RegisterUseCase(RegisterParams{name,email,password,phoneNumber?}), VerifyEmailUseCase({email,otp}), ResendVerificationUseCase({email}), ForgotPasswordUseCase({email}), ResetPasswordUseCase({email,otp,newPassword}), ChangePasswordUseCase({currentPassword,newPassword}), GetCurrentUserUseCase(NoParams), LogoutUseCase(NoParams), UpdateProfileUseCase({name?,phoneNumber?,bankCode?,bankAccountNumber?,bankAccountHolder?}), UploadAvatarUseCase(File), DeleteAvatarUseCase.

### API calls (`auth_remote_datasource.dart`)

| Method | Path | Ghi chú |
|---|---|---|
| POST | `/auth/sign-in` | body gồm `device_id`, `device_name` (repo impl :28-34) |
| POST | `/auth/sign-up` | `display_name`, optional `phone_number` |
| POST | `/auth/verify-email` | `{email, otp}` |
| POST | `/auth/resend-verification` | `{email}` |
| POST | `/auth/forgot-password` | `{email}` |
| POST | `/auth/reset-password` | `{email, otp, new_password}` — 204 no content |
| GET | `/users/me` | parse khoan dung `data.user` hoặc `data` |
| PATCH | `/users/me` | partial body |
| PUT | `/users/me/password` | `{current_password, new_password}` — 204 |
| PUT | `/users/me/avatar` | multipart file `avatar` |
| DELETE | `/users/me/avatar` | 204 |

- **Login success** (repo impl :23-46): lưu access+refresh vào secure storage ngay, trả UserEntity. DTO `AuthResponseModel` (freezed: access_token/refresh_token/user).
- **Logout** (repo impl :216-219): **CHỈ clear token local, KHÔNG gọi API sign-out** (endpoint `/auth/sign-out` có khai báo nhưng chưa dùng).

## 4. BILLS FEATURE

### Pages
- **BillCapturePage** (`bill_capture_page.dart`): màn camera tối, nhận `groupId`/`groupName` từ route extra.
  - Chụp máy ảnh (imageQuality 88, max 1920px) hoặc chọn nhiều ảnh thư viện; **tối đa 5 ảnh** (:35); vượt limit → SnackBar lỗi.
  - Validate mỗi ảnh bằng `ImageValidator` (`core/utils/image_validator.dart`): 10MB max, kiểm tra magic bytes JPEG/PNG/WebP/HEIC chống đổi đuôi file (:22-69).
  - Tray ảnh kéo-thả sắp xếp thứ tự, xoay 90°, crop (`PhotoCropDialog`), xoá, xem chi tiết.
  - Nút header động (:391-403): 0 ảnh → "Nhập thủ công" (push bill-detail với bill rỗng id='' status draft); ≥1 ảnh → "Chia tiền (N)" (push bill-detail với photos + `autoStartOcr: true`).
  - Long-press flash button → tips bottom sheet.
  - Fallback desktop/web: camera fail → chèn ảnh dummy PNG (:100-113).
- **BillDetailPage** (`bill_detail_page.dart`, 1342 dòng):
  - initState (:42-67): set currentUserId; nếu `autoStartOcr` && có photos → mở OcrCandidateReviewModal + chạy OCR; ngược lại loadBillDetail.
  - Header: tên quán (edit dialog ≤60 ký tự), badge trạng thái (Nháp/Chờ duyệt/Đã chốt/Đã hủy :1291-1341), người trả + ngày, thumbnail hoá đơn gốc.
  - Body: danh sách món (`BillItemCard`: tap mở EditItemDialog sửa/xoá, toggle avatar gán người, assign-all), switch Chia đều + link chọn người tham gia (`SelectEvenSplitMembersModal`), section Thuế/Phí/Khuyến mãi (`BillAdjustmentsSection`).
  - **Permission rule** (:548-554): `isReadOnlyStatus` = finalized\|voided; `isEditable` = !readOnly && (isCaptain \|\| isCreditor \|\| members empty). isCaptain/isCreditor mặc định true khi chưa rõ (tránh khoá nhầm).
  - Dialogs edge case: `_showUnassignedDetailDialog` liệt kê món chưa gán (:263-377); `_showMismatchDetailDialog` bảng so sánh tổng tính toán vs tổng bill (:379-479); void bill yêu cầu lý do ≥3 ký tự (:1118-1289).

### State — `BillDetailNotifier` (`providers/bill_detail_notifier.dart`, 1235 dòng)
- Provider: `StateNotifierProvider.family<..., BillDetailEntity>` key theo initialBill (:1227-1235).
- `BillDetailState` (:9-44): `bill, breakdown, isLoading, isSaving, isFinalizing, isCalculatingBreakdown, isOcrScanning, ocrScanStep (String tiến trình OCR), ocrCandidate, ocrErrorMessage, errorMessage, successMessage, currentUserId, evenSplitMemberIds, isDirty, isVoiding`.
- Computed getters quan trọng: `computedTotal = sum(line_total) − sum(discount) + serviceCharge + vat − generalDiscount`; `deltaTotal`; `unassignedCount`; `myShareAmount` (client-side estimate: even → total/số người; item_ratio → tỉ lệ weight × món + share phụ thu/VAT :137-197).
- Methods chính:
  - `loadBillDetail` (:357-501): billId rỗng hoặc prefix `draft-` → **không gọi GET**, chỉ load members + tự chọn creditor (current user → captain → first member) + gán even assignments; billId thật → GET detail, merge breakdown, enrich tên/avatar.
  - `runOcrProcess` (:504-559): upload ảnh → candidate; step messages "Đang tải ảnh..." / "AI Llama đang bóc tách...".
  - `applyOcrCandidate` (:562-637): áp món từ OCR, **mặc định bỏ gán tất cả** (item_ratio) hoặc gán đều (even).
  - `setSplitMode('even'\|'item_ratio')` (:645-671): even → gán weight 1/n mọi món cho selected members; quay lại item_ratio giữ nguyên data phân bổ cũ.
  - `toggleMemberAssignment` (:692-736): thêm/bỏ member rồi **re-weight 1/count**.
  - `saveDraft` (:847-948): bill mới → POST createManualBill; bill có id → PUT updateDraft payload gồm version (optimistic locking).
  - `calculateBreakdown/fetchOfficialBreakdown` (:951-1000): POST calculate lấy phân bổ chính thức từ BE.
  - `reviewBillOnly` (:1034-1087): saveDraft trước → POST review.
  - `finalizeBill` (:1090-1168): chuỗi saveDraft → review → finalize; set status='finalized'.
  - `voidBill(reason)` (:1171-1224): yêu cầu lý do không rỗng; captain only (BE chặn).
  - `_friendlyBillError` (:1004-1031): map code BE (ITEM_UNASSIGNED, CREDITOR_REQUIRED, SUBTOTAL_MISMATCH, TOTAL_MISMATCH, DISCOUNT_EXCEEDS_BILL, INACTIVE_MEMBER_ASSIGNED, BILL_ALREADY_VOIDED, PAYMENT_ALREADY_STARTED, CAPTAIN_REQUIRED, VERSION_CONFLICT, GROUP_ARCHIVED) → câu tiếng Việt.

### Sticky bottom bar gating (`widgets/bill_sticky_bottom_bar.dart`)
- Warnings (:74-82): `!hasBankAccount \|\| hasNoItems \|\| hasUnassignedItems \|\| isTotalMismatch` → hàng cảnh báo vàng phía trên, nút chính bị **disable** (outline thay gradient) (:465-469, :561-565, :589-594).
- Nút theo status × role:
  - finalized + captain: [Huỷ hoá đơn] [Xem phân bổ]; finalized khác: [Xem phân bổ].
  - reviewed + captain: [Sửa lại] [Chốt chia tiền]; reviewed + creditor: [Gửi đối soát] (disable khi !isDirty hoặc có warnings — có dòng giải thích "Chưa có thay đổi mới" :477-503); reviewed member: read-only.
  - draft + captain: [Lưu nháp (disable khi !isDirty)] [Chốt hoá đơn]; draft + creditor: [Lưu nháp] [Gửi đối soát]; member: [Xem phân bổ].

### OCR polling edge cases (`data/datasources/bill_remote_datasource.dart:117-214`)
- POST `/bills` multipart (`group_id`, `merchant_name`, files field `images`) → nếu response chưa có items → **poll GET `/bills/{id}?group_id=` mỗi 1.5s, tối đa 40 lần (~60s)**; dừng sớm khi `ocr_job.status == 'failed'` hoặc mọi `ocr_jobs[].status == 'failed'`; lỗi poll từng lần bị bỏ qua (ignore); hết 60s vẫn trả initialBill (rỗng items) → modal cho phép Retry hoặc nhập tay.

### API endpoints bills
GET `/bills?group_id&limit&cursor` · POST `/bills` (JSON manual hoặc multipart scan) · GET `/bills/{id}` · PUT `/bills/{id}` · POST `/bills/{id}/review\|finalize\|void` · POST `/bills/calculate` hoặc `/bills/{id}/calculate` · GET `/groups/{id}` (lấy members, fallback `/groups/{id}/members` :413-439).
Entities (`bill_detail_entity.dart`): `BillDetailEntity` (status draft/reviewed/finalized/voided, splitMethod item_ratio/even, version optimistic lock, mismatchCodes, breakdown), `BillItemEntity`, `BillItemAssignmentEntity` (weight), `BillMemberEntity`, `BillShareBreakdownEntity` (itemsSubtotal/serviceShare/vatShare/generalDiscountShare/finalAmount/isCreditor). Parser fromJson đọc candidate từ `candidate` \| `ocr_job.candidate` \| `ocr_jobs[].candidate` (:408-422).

## 5. HOME FEATURE

- **HomePage** (`home_page.dart`): watch `authControllerProvider` (tên user, avatar initials) + `unreadNotificationCountProvider` (dot đỏ trên chuông :159-176).
  - NetBalanceHeroCard: onPayVietQr → `/settlement` extra `SettlementTab.payable`; onScanBill → `GroupPickerBottomSheet` chọn nhóm → push `/scan-bill` {groupId, groupName}; onCreateGroup → `/groups`.
  - ActionableDebtsSection: view all/pay/review → settlement tương ứng; onRemind hiện "coming soon".
  - MyGroupsCarousel → push `${AppRoutes.groups}/{id}` (kèm extra GroupEntity).
  - RecentActivityTimeline: tap item → nếu có billId → `/bill-detail` {billId, groupId, groupName}; else groupId → group detail (`recent_activity_timeline.dart:324-344`).
- **Providers** (gọi Dio trực tiếp, không qua usecase):
  - `homeGroupsProvider` (`home_groups_provider.dart`): FutureProvider.autoDispose, GET `/groups?limit=3`, **catch mọi lỗi → trả []** (hiển thị fallback thân thiện, kể cả chưa đăng nhập).
  - `homeActivitiesProvider` (`home_activities_provider.dart`): depends groups; GET `/groups/{id}/activities?limit=2` cho tối đa 3 nhóm **song song**, lỗi từng nhóm bỏ qua riêng (:39-41), sort desc createdAt, take 3.

## 6. GROUPS FEATURE

### Pages
- **GroupsPage** (`groups_page.dart`):
  - 2 tile tham gia: "Nhập link vào nhóm" (JoinByLinkBottomSheet) & "Quét QR vào nhóm" (push ScanQrJoinPage). Sau khi sheet/page trả GroupEntity preview → `_join()` gọi `joinGroupByCode(inviteCode)` = POST `/groups/join` rồi `refresh()` danh sách (:220-236); lỗi → SnackBar failure.message.
  - Nút tạo nhóm → CreateGroupBottomSheet → thành công **đi thẳng AddMembersPage** (:196-202).
  - Danh sách: cursor pagination (limit 20, `loadMore`), tabs lifecycle "Đang hoạt động"/"Đã khóa bill" (filter cục bộ), empty state (_EmptyGroupsState với nút tạo nhóm), error state với retry, closed-empty state.
  - "Nhóm gần đây" & danh bạ "Thành viên gần đây": **vẫn mock** (groups_provider.dart:225-233 comment rõ backend chưa có API).
- **ScanQrJoinPage** (`scan_qr_join_page.dart`): khung camera **placeholder** (comment :17-22 — sẽ thay MobileScanner sau); hiện hoạt động: chọn ảnh QR từ gallery → decode thuần Dart bằng `zxing2` + `image` (`data/qr_image_decoder.dart:30-67`, xử lý NotFoundException/Format/Checksum với message riêng, bắt exception ảnh hỏng); hoặc "Nhập link" mở lại JoinByLinkBottomSheet. `_onCodeDetected` (:57-91): extract code → **validate độ dài đúng 8** (`invite_code.dart:2`, Base62 **phân biệt hoa thường** — không chuẩn hoá case) → PreviewInviteUseCase (GET `/groups/invites/{code}`) → pop về GroupsPage với GroupEntity(id: 'preview:$code').
- **AddMembersPage** (`add_members_page.dart`): mở sau khi tạo nhóm; 2 lối mời InviteLinkBottomSheet / InviteQrBottomSheet; tick chọn contacts (mock) — **backend cố ý không có POST members** nên chỉ `bumpMemberCountLocally` (:52-56); "Mời bằng số điện thoại" coming soon.
- **GroupDetailPage** (`group_detail_page.dart`, 1200 dòng): 4 tab Hub — Hóa đơn (mock bills + filter chips + FAB speed-dial quét OCR/thủ công **đều coming soon** :140-145), Công nợ, Thành viên, Hoạt động.
  - **Panels hub dùng MOCK in-memory** (`providers/group_detail_provider.dart:12-14` — GroupDetailMockData), nhưng các thao tác quản trị gọi API thật:
    - Sheet cài đặt nhóm: rename (PATCH `/groups/{id}`, merge giữ memberCount/myBalance vì PATCH không trả — groups_provider.dart:204-218), transfer captain (PUT `/groups/{id}/members/{memberId}/role`), remove member (DELETE cùng endpoint leave), disband (DELETE `/groups/{id}` — BE 409 khi còn nợ/hóa đơn, hiển thị failure.message), leave group, khóa bill.
    - `_tryLeaveGroup` guard sớm (:459-481): myBalance ≠ 0 → chặn "Bạn còn công nợ mở..." không cần đợi 409.
    - Khóa bill `_closeBook` (:265-293): chặn khi còn bill active; dialog xác nhận liệt kê số dư từng member; **markGroupClosedLocally** (chưa nối API thật — comment :140-144, khóa bill BE một chiều không mở lại); ribbon _ClosedRibbon thông báo.
    - Mã mời thật: list/create/revoke qua usecases (:327-357); `resolveGroupInvite` (`data/invite_resolver.dart`): **list invites trước, chỉ tạo mới khi chưa có** tránh spam mã rác.
    - Thanh toán VietQR trong nhóm: VietQrPaymentSheet → submitProof (mock state), ProofReviewSheet approve/reject (mock state).

### Groups API (`datasources/group_remote_datasource.dart` — Retrofit, 13 endpoint)
POST `/groups` · GET `/groups` (limit,cursor) · GET/PATCH/DELETE `/groups/{id}` · GET/POST `/groups/{id}/invites` · DELETE `/groups/{id}/invites/{inviteId}` · GET `/groups/invites/{code}` · POST `/groups/join` · DELETE `/groups/{id}/members/{memberId}` · PUT `/groups/{id}/members/{memberId}/role` · GET `/groups/{id}/activities`.

## 7. SETTLEMENT FEATURE

- **SettlementController** (`providers/settlement_controller.dart`):
  - `SettlementState`: currentTab(payable/receivable/bills/history), isLoading, isMutating, overview, payableDebts, receivableDebts, groupedDebts (batch theo chủ nợ), pendingProofs, settledHistory, bills, selectedDebtIds, remindedCooldowns (Map debtId→giây), errorMessage.
  - `loadData` (:112-150): chọn sẵn tất cả debt awaiting lần đầu; các lần sau **giữ selection cũ ∩ selectable** (:126-128).
  - `_mutate` (:248-268): chặn thao tác song song ("Một thao tác khác đang được xử lý"), reload sau mutate.
  - `remindDebt` → cooldown 60s với Timer.periodic giảm giây (:270-288).
- **Repository aggregation** (`data/repositories/settlement_repository_impl.dart`) — điểm đặc biệt:
  - List TẤT CẢ nhóm (paginate 100/trang, **max 50 trang chống cursor không tiến** — datasource :55-57,76-78) → với mỗi nhóm load debts + bills song song, **throttle tối đa 6 request đồng thời** tránh rate-limit BE (:17-57).
  - Load payment records cho debt pendingConfirmation/settled → tách pendingProofs (mình là creditor) vs settledHistory (confirmed).
  - **Idempotency-Key UUIDv5 deterministic** (:21-32): `qr:$groupId:$creditorId:sortedDebtIds` (bấm lại replay kết quả cũ), `proof:$groupId:$paymentId`, `confirm:...`, `reject:...:$reason` (lý do nằm trong key); riêng remind dùng **UUIDv4 random mỗi lần** vì nhắc nợ là thao tác lặp chủ đích (:279-291).
  - Robustness: record hỏng skip từng cái không làm vỡ màn hình (:459-474); status lạ → voided/superseded (:430-451); BE chưa deploy trường mới (payer_display_name...) vẫn hiển thị '—' (:368-373).
- **UI flow thanh toán** (`pages/settlement_page.dart`):
  - Tab "Cần trả": PayableDebtsTab — nút trả từng khoản → `_generateAndOpenQr([debt.id])`; nút batch → SelectDebtBatchSheet (gom nhóm theo groupId+creditorId, chọn nhiều, tổng tiền) → generate QR chung.
  - **DynamicVietQrSheet** (`widgets/dynamic_vietqr_sheet.dart`): ảnh QR load từ `qrImageUrl` (errorBuilder "Không tải được mã VietQR" :224-230); số tiền; info ngân hàng/STK/chủ TK/nội dung CK với nút copy; ô lời nhắn ≤500 ký tự; nút "Tải ảnh biên lai đã chuyển" → ImagePicker gallery → **validate client: 1 byte–10MB, chỉ JPEG/PNG/HEIC** (:73-86, :130-137) → POST proof multipart → pop + snackbar "Đã nộp biên lai...". Lỗi submit **giữ nguyên message BE** (:93-101).
  - Tab "Cần thu": ReceivableProofsTab — card minh chứng chờ duyệt: "Xác nhận đã nhận tiền" (POST confirm → reload → snackbar) / "✕ Từ chối" → RejectProofDialog nhập lý do (POST reject {reason}); danh sách khoản chờ thu với nút nhắc nợ có **cooldown 60s** hiển thị "Chờ Xs".
  - Tab "Hóa đơn" & "Lịch sử": AllBillsTab (tap chi tiết → coming soon), SettledHistoryTab (tap → `_refreshAndOpenProof` tải lại dữ liệu mới nhất trước khi mở sheet xem biên lai :183-217).
  - Lỗi generate QR: ưu tiên errorMessage từ controller (VD "chủ nợ chưa cài STK") :120-132.
  - Hero summary: tổng cần trả/cần thu + alert pending proofs → tap chuyển tab receivable.

## 8. NOTIFICATIONS FEATURE

- **Data** (Dio trực tiếp, không usecase/repository layer):
  - `NotificationsNotifier` (`providers/notifications_notifier.dart`): state Equatable {items, isLoading, isLoadingMore, hasMore, currentPage/totalPages/totalItems, unreadCount, error}.
  - `loadInitial` (:77-135): **song song** GET `/notifications?page=1&page_size=20` + GET `/notifications/unread-count`.
  - `loadMore` (:190-232): infinite scroll trigger tại pixels ≥ maxExtent−200 (`notifications_page.dart:35-40`).
  - `refresh`: lỗi mạng khi pull-refresh **giữ nguyên state cũ** (:185-187).
  - `markAsRead` (:234-250): **optimistic update** readAt + giảm unreadCount, PATCH `/notifications/{id}/read`, lỗi thì comment "Rollback nếu cần" (thực tế chưa rollback).
  - `markAllAsRead` (:252-265): optimistic toàn bộ + POST `/notifications/read-all`.
- **Page** (`notifications_page.dart`): filter tabs Tất cả/Chưa đọc (client-side filter :54-56); gom nhóm theo ngày "Hôm nay"/"Trước đó" (:256-270); skeleton loading; empty state.
- **Tap handling** (:244-254): markAsRead (nếu chưa đọc) + `_handleNotificationAction`: payload.`bill_id` → push `/bill-detail` {'billId'}; payload.`group_id` → push groupDetail(groupId). Không match → chỉ đánh dấu đã đọc.
- Entity `NotificationEntity`: id, userId, type, title, body, payload(map), createdAt, readAt.

## 9. FCM / PUSH NOTIFICATION

- **KHÔNG có triển khai FCM ở FE**: `pubspec.yaml` không chứa firebase_core/firebase_messaging hay bất kỳ package Firebase nào; `grep firebase\|fcm\|messaging` trong `lib/` trả về 0 kết quả liên quan; `AndroidManifest.xml` chỉ có permission INTERNET, không có service FirebaseMessaging; không có google-services.json wiring, không có foreground/background handler, không có navigation-on-tap cho push. Thông báo hiện chỉ là **in-app polling qua REST** (mục 8). Phía BE có module notification + FCM nhưng FE chưa tích hợp.

## 10. PROFILE FEATURE

- **ProfilePage** (`profile_page.dart`, 1026 dòng):
  - Header avatar: pick camera/gallery → `uploadAvatar` (PUT multipart) → cập nhật state AuthController (copyWith avatarUrl — auth_controller.dart:127-141); option xoá avatar.
  - Card tài khoản ngân hàng: có STK → hiển thị + nút "Cập nhật"; chưa có → box cảnh báo vàng "Chưa liên kết tài khoản ngân hàng" + CTA sang bank-settings (:426-529). Trạng thái này cũng được BillDetailPage dùng làm warning "Chưa cập nhật STK".
  - Menu: Chỉnh sửa thông tin cá nhân → `/edit-profile`; Đổi mật khẩu → `/change-password`.
  - **Đăng xuất** (:592-750): dialog confirm → `AuthController.logout()` → LogoutUseCase → `TokenStorage.clear()` → `state = AsyncData(null)` → refreshListenable của router kích hoạt → redirect về `/welcome`.
- **EditProfilePage** (`edit_profile_page.dart`): form name/phone → `updateProfile` (PATCH `/users/me`) → snackbar thành công + pop (:61-75).
- **BankSettingsPage** (`bank_settings_page.dart`, 789 dòng): pre-select bank từ user.bankCode (:71-73); **bắt buộc chọn ngân hàng** (:103); normalize tên chủ TK bằng `VietnameseUtils.toBankHolderFormat` (UPPERCASE không dấu) (:111); lưu qua updateProfile(bankCode, bankAccountNumber, bankAccountHolder) → "Đã lưu tài khoản ngân hàng VietQR thành công!".
- **ChangePasswordPage** (`change_password_page.dart`): checklist realtime client-side (≥8 ký tự, có chữ hoa A-Z, có chữ số — :50-57); phải pass cả 3 mới cho submit (:62-65); confirm khớp (:68-71); gọi ChangePasswordUseCase (PUT `/users/me/password`); lỗi `INVALID_CURRENT_PASSWORD` map sẵn tiếng Việt trong dio_failure_mapper.

## 11. TỔNG HỢP EDGE CASES THEO CODE THỰC TẾ

1. **Token refresh 401**: single-flight, skip-list endpoint auth, retried-flag chống loop, clear tokens khi refresh fail (auth_interceptor.dart:58-88).
2. **Logout khi phiên chết**: interceptor chỉ clear storage; redirect về welcome xảy ra qua AuthController.build/getCurrentUser fail → router refresh.
3. **Offline/no internet**: mapDioError connectionTimeout/connectionError → NetworkFailure message tiếng Việt; Home providers swallow lỗi → empty state; Notifications refresh giữ state cũ; Settlement hiện banner lỗi + nút "Thử lại" (settlement_page.dart:432-460). Không có cache offline.
4. **OCR scan fail**: poll 60s timeout, dừng sớm khi job failed, modal cho Retry / Dismiss (nhập tay), ảnh dummy fallback khi camera unavailable.
5. **Validation form**: email/password/phone/name/OTP/reason-void/proof-image/magic-bytes — chi tiết từng trang như trên.
6. **Rate limit login**: RATE_LIMITED → timer 15 phút disable nút.
7. **Optimistic locking bills**: version gửi kèm PUT/review/finalize/void; VERSION_CONFLICT → "Dữ liệu đã bị thay đổi, tải lại trang".
8. **Guard nghiệp vụ groups**: chặn rời nhóm khi còn nợ (client), chặn khóa bill khi còn bill active (client), 409 codes từ BE hiển thị qua failure.message.
9. **Idempotency settlement**: UUIDv5 deterministic cho qr/proof/confirm/reject; throttle 6 request; chống cursor-loop 50 trang.
10. **Empty states**: groups (tạo nhóm đầu tiên), closed-tab, bills trong group, notifications, unassigned items, mismatch total — đều có widget riêng.

**Khoảng trống đáng chú ý cho tài liệu**: chưa có deep link/app link; chưa có FCM FE; camera QR scanner là placeholder; Group Hub panels + recent groups/contacts dùng mock; lock-bill backend chưa nối; logout chưa gọi API sign-out; NetworkInfo đã DI nhưng chưa dùng.
