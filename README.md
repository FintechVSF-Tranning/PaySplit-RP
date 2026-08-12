# 💸 PaySplit – Tài liệu tổng quan hệ thống

PaySplit là ứng dụng chia hoá đơn nhóm và nhắc nợ tự động: quét hoá đơn bằng OCR, tách tiền theo món/theo người, sinh **VietQR động** đúng số tiền và nhắc nợ tự động.

Repo `PaySplit-RP` là repo **tài liệu** (Report / Product): PRD, thiết kế database, báo cáo. Code nằm ở hai repo còn lại.

## 📦 Các repository trong hệ thống

| Repo | Vai trò | Công nghệ | Đường dẫn local |
| --- | --- | --- | --- |
| [PaySplit-BE](https://github.com/FintechVSF-Tranning/PaySplit-BE) | REST API server | Go 1.26, chi, pgx, sqlc, PostgreSQL 17 | `../PaySplit-BE` |
| [PaySplit-FE](https://github.com/FintechVSF-Tranning/PaySplit-FE) | Ứng dụng mobile | Flutter (Dart 3.12), Riverpod, Dio/Retrofit | `../PaySplit-FE` |
| [PaySplit-RP](https://github.com/FintechVSF-Tranning/PaySplit-RP) | Tài liệu sản phẩm | Markdown, SQL | repo này |

Cấu trúc thư mục làm việc nên đặt cả 3 repo cạnh nhau:

```text
ProjectGo/
├── PaySplit-BE/     # Go API
├── PaySplit-FE/     # Flutter app
└── PaySplit-RP/     # Tài liệu (repo này)
```

### Nội dung repo tài liệu

```text
PaySplit-RP/
├── PRD.md                                    # Product Requirements Document (bản làm việc)
├── Report1_Product_Requirement_Document.md   # Báo cáo 1 – bản nộp (kèm .docx/.pdf)
├── dbv1.sql                                  # Schema database v1 đầy đủ cho toàn hệ thống
└── README.md                                 # File này
```

`dbv1.sql` là thiết kế database mục tiêu (users, sessions, groups, bills, bill_items, ledger, debts, notifications…), rộng hơn nhiều so với migration hiện có trong backend — backend mới hiện thực bảng `users`. Khi thêm bảng mới, chép phần tương ứng từ `dbv1.sql` sang `PaySplit-BE/db/migrations/` dưới dạng migration goose.

---

## 🏛 Kiến trúc tổng thể

```text
┌──────────────────────┐        HTTPS / JSON        ┌──────────────────────┐
│   PaySplit-FE        │  ───────────────────────►  │   PaySplit-BE        │
│   Flutter app        │   Bearer <access_token>    │   Go REST API        │
│                      │  ◄───────────────────────  │   (chi router)       │
│ presentation         │                            │ delivery/http        │
│      ↓               │                            │      ↓               │
│ domain (entity/uc)   │                            │ usecase              │
│      ↑               │                            │      ↓               │
│ data (dio/retrofit)  │                            │ repository (pgx)     │
└──────────────────────┘                            └──────────┬───────────┘
                                                               │
                                                     ┌─────────▼──────────┐
                                                     │  PostgreSQL 17     │
                                                     │  (docker compose)  │
                                                     └────────────────────┘
```

Hai bên dùng **cùng một triết lý Clean Architecture**: tầng `domain` ở giữa không phụ thuộc framework, các tầng ngoài (HTTP, database, UI) chỉ là adapter cắm vào. Đổi thư viện HTTP hay đổi DB chỉ ảnh hưởng tầng ngoài cùng.

---

## ⚙️ Backend – PaySplit-BE (Go)

### Stack

* **Ngôn ngữ:** Go 1.26
* **HTTP router:** [chi/v5](https://github.com/go-chi/chi) — middleware `RequestID`, `Logger`, `Recoverer`, `Timeout` (15s)
* **Database:** PostgreSQL 17 qua connection pool [pgx/v5](https://github.com/jackc/pgx)
* **Query layer:** [sqlc](https://sqlc.dev) — sinh code Go type-safe từ file `.sql`
* **Migration:** file SQL định dạng goose, chạy qua `cmd/migrate`
* **Auth:** JWT access token + bcrypt

### Cấu trúc thư mục

```text
PaySplit-BE/
├── cmd/                          # Entrypoint (main mỏng, không chứa business logic)
│   ├── api/main.go               # Khởi chạy HTTP API
│   └── migrate/main.go           # Chạy migration up/down/status
│
├── db/migrations/                # Migration SQL toàn ứng dụng (goose format)
│   └── 00001_create_users.sql
│
├── docs/
│   ├── openapi.yaml              # Đặc tả REST API
│   └── project-structure.md      # Ghi chú cấu trúc chi tiết (tiếng Việt)
│
├── internal/
│   ├── bootstrap/app.go          # Lắp ráp config → DB → router → HTTP server
│   ├── config/                   # Đọc & validate config từ biến môi trường
│   │
│   ├── modules/                  # Mỗi domain nghiệp vụ một thư mục, 4 tầng
│   │   └── auth/
│   │       ├── domain/           # Entity + lỗi nghiệp vụ (không phụ thuộc gì)
│   │       ├── usecase/          # Application service, chỉ phụ thuộc interface
│   │       ├── repository/       # repository.go = port; postgres/ = adapter
│   │       │   └── postgres/
│   │       │       ├── queries/  # SQL do module này sở hữu
│   │       │       └── sqlc/     # Code sinh tự động — KHÔNG sửa tay
│   │       └── delivery/http/    # Handler, route, DTO request/response
│   │
│   ├── platform/                 # Hạ tầng kỹ thuật dùng chung
│   │   ├── database/             # Khởi tạo pgx pool, health check
│   │   ├── auth/jwt/             # Phát hành token
│   │   └── security/password/    # Băm mật khẩu bcrypt
│   │
│   └── transport/http/           # Plumbing HTTP dùng chung mọi module
│       ├── router/               # Tạo chi router, mount route từng module
│       ├── middleware/           # Timeout…
│       └── helpers/              # Ghi JSON, chuẩn hoá lỗi, phân trang
│
├── docker-compose.yaml           # PostgreSQL cho môi trường local
├── Dockerfile                    # Build image API (multi-stage)
├── Makefile                      # run / build / test / fmt / sqlc / migrate
└── sqlc.yaml                     # Cấu hình sinh code sqlc
```

### Nguyên tắc phụ thuộc

```text
delivery/http  →  usecase  →  repository (interface)  →  repository/postgres (adapter)
                     ↓
                  domain
```

* `domain` không import từ tầng nào khác — chỉ entity và lỗi nghiệp vụ thuần.
* `usecase` tự định nghĩa interface mình cần (`repository.Repository`, `PasswordManager`, `TokenIssuer`) và nhận qua constructor. Nó **không bao giờ** import `pgx`, `chi` hay `net/http`.
* `repository/postgres` chịu trách nhiệm map giữa model sqlc và entity domain.
* `bootstrap/app.go` là nơi duy nhất ráp các implementation cụ thể lại với nhau.

**Thêm module mới:** copy layout thư mục `auth/`, đăng ký route trong `internal/transport/http/router/router.go`, và thêm thư mục queries vào `sqlc.yaml`.

### API endpoints hiện có

| Method | Path | Mô tả |
| --- | --- | --- |
| `GET` | `/` | Tên service, trạng thái, version |
| `GET` | `/health` | Liveness probe |
| `POST` | `/api/v1/auth/register` | Đăng ký, trả access token |
| `POST` | `/api/v1/auth/login` | Đăng nhập, trả access token |

Route không tồn tại trả JSON `404`, sai method trả JSON `405`. Mọi request bị giới hạn 15 giây.

---

## 📱 Frontend – PaySplit-FE (Flutter)

### Stack

* **Framework:** Flutter, Dart SDK `^3.12.2`
* **State management:** Riverpod (`flutter_riverpod` + `riverpod_generator`)
* **Dependency injection:** `get_it` + `injectable`
* **Routing:** `go_router`
* **Networking:** `dio` + `retrofit` (+ `pretty_dio_logger`, `connectivity_plus`)
* **Xử lý lỗi hàm:** `fpdart` (`Either<Failure, T>`)
* **Model:** `freezed` + `json_serializable`
* **Lưu trữ:** `flutter_secure_storage` (token), `shared_preferences`
* **Test:** `flutter_test` + `mocktail`

### Cấu trúc thư mục

Áp dụng **Clean Architecture + feature-first**: mỗi feature sở hữu trọn 3 tầng `data → domain → presentation`, có thể test hoặc tách rời độc lập.

```text
PaySplit-FE/lib/
├── main.dart                  # entry mặc định của `flutter run` (= flavor development)
├── main_development.dart      # entry point theo từng flavor
├── main_staging.dart
├── main_production.dart
├── bootstrap.dart             # khởi động dùng chung: EnvConfig → DI → runApp
├── app/
│   ├── app.dart               # widget gốc MaterialApp.router
│   ├── router/                # cấu hình go_router + hằng số route
│   └── theme/                 # theme Material 3 sáng/tối
├── core/                      # hạ tầng dùng chung cho mọi feature
│   ├── config/                # EnvConfig, enum Flavor
│   ├── constants/             # ApiEndpoints, StorageKeys
│   ├── error/                 # Failure (domain) + Exception (data)
│   ├── network/               # Dio module, AuthInterceptor, TokenStorage
│   ├── usecase/               # lớp nền UseCase<ReturnType, Params>
│   └── utils/                 # format tiền tệ, phản hồi UI
├── di/                        # wiring get_it + injectable
└── features/
    ├── auth/                  # bản mẫu đầy đủ (login, register, logout, me)
    ├── bills/                 # bản mẫu tối giản để nhân bản khi thêm feature
    ├── home/                  # màn hình chính + các widget
    └── splash/                # màn hình chờ khôi phục phiên đăng nhập
```

### Nguyên tắc phụ thuộc

```text
presentation  ──→  domain  ←──  data
```

Tầng `domain` không biết Dio, không biết JSON. Tầng `data` hiện thực hoá interface do `domain` định nghĩa. Trong code: một `Page` chỉ được import **entity** và **usecase**, không bao giờ import `Dio` hay `Model`. Nhờ vậy đổi backend hay đổi thư viện HTTP chỉ phải sửa `data/`.

### Hai điểm đáng chú ý

**1. Lỗi được truyền như giá trị, không dùng try/catch ở tầng trên:**

```text
Datasource ném DioException
   └→ Repository bắt, gọi mapDioError() → trả Left(Failure)
        └→ UseCase trả nguyên Either lên
             └→ Controller/Provider đổi thành AsyncError
                  └→ UI hiện SnackBar
```

**2. DI và state management tách vai trò rõ ràng:** `get_it` + `injectable` lo wiring tầng data (repository, datasource, usecase) lúc khởi động; `Riverpod` chỉ lo state UI. Điểm nối nằm ở controller — `AuthController` gọi `getIt<LoginUseCase>()` rồi bọc kết quả vào `AsyncValue`, nên tầng data hoàn toàn không biết Riverpod tồn tại.

Chi tiết đầy đủ (từng file làm gì, luồng auth, cách thêm feature mới) nằm trong [README của PaySplit-FE](../PaySplit-FE/README.md).

---

## ▶️ Cách chạy 2 project

### Yêu cầu môi trường

| Công cụ | Phiên bản | Dùng cho |
| --- | --- | --- |
| Go | 1.26+ | Backend |
| Docker + Docker Compose | mới nhất | PostgreSQL local |
| Flutter SDK | Dart `^3.12.2` | Frontend |
| Android Studio / Xcode | — | Emulator, thiết bị thật |
| `sqlc` | mới nhất | Chỉ cần khi sửa file `.sql` của backend |

### Bước 1 — Chạy backend (PaySplit-BE)

```bash
cd PaySplit-BE

# 1. Tạo file cấu hình
cp .env.example .env
# Nhớ đổi JWT_SECRET_KEY thành một chuỗi ngẫu nhiên đủ dài

# 2. Bật PostgreSQL
docker compose up -d postgres

# 3. Chạy migration
make migrate-up

# 4. Chạy API
make run          # tương đương: go run ./cmd/api
```

Server lắng nghe ở `HTTP_ADDRESS`, mặc định <http://localhost:8080>. Kiểm tra:

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

**Biến môi trường chính** (xem đầy đủ trong `.env.example`):

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `APP_ENV` | `development` | Tên môi trường chạy |
| `HTTP_ADDRESS` | `:8080` | Địa chỉ API lắng nghe |
| `DATABASE_URL` | `postgres://postgres:postgres@localhost:5432/paysplit?sslmode=disable` | DSN PostgreSQL |
| `DB_MAX_CONNS` / `DB_MIN_CONNS` | `10` / `2` | Giới hạn pool pgx |
| `JWT_SECRET_KEY` | — | **Bắt buộc.** Khoá ký token |
| `JWT_ISSUER` | `paysplit-backend` | Claim `iss` |
| `JWT_ACCESS_TOKEN_TTL_MINUTES` | `60` | Thời hạn access token |

**Các lệnh Make khác:**

| Lệnh | Tác dụng |
| --- | --- |
| `make build` | Build binary ra `bin/paysplit-api` |
| `make test` | Chạy toàn bộ test (`go test ./...`) |
| `make fmt` | `gofmt -w ./cmd ./internal` |
| `make tidy` | `go mod tidy` |
| `make sqlc` | Sinh lại code sqlc từ `queries/` + `db/migrations/` |
| `make migrate-up` / `migrate-down` / `migrate-status` | Quản lý migration |

**Chạy bằng Docker thay vì `make run`:**

```bash
docker build -t paysplit-api .
docker run --rm -p 8080:8080 --env-file .env paysplit-api
```

### Bước 2 — Chạy frontend (PaySplit-FE)

```bash
cd PaySplit-FE

# 1. Cài dependency
flutter pub get

# 2. BẮT BUỘC: sinh code *.g.dart / *.freezed.dart
dart run build_runner build --delete-conflicting-outputs

# 3. Chạy app, trỏ về backend local
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8080/api/v1
```

Giải thích tham số:

* `10.0.2.2` là địa chỉ để **Android emulator** gọi về `localhost` của máy host. iOS Simulator dùng `localhost` trực tiếp; **thiết bị thật** phải thay bằng IP LAN của máy bạn (ví dụ `http://192.168.1.10:8080/api/v1`).
* Hậu tố `/api/v1` là bắt buộc — backend mount route auth tại `/api/v1/auth/...`, trong khi giá trị mặc định trong `main_development.dart` đang là `https://dev-api.paysplit.app/v1`. Nếu quên `--dart-define`, app sẽ gọi lên server dev trên mạng chứ không phải backend local.

**Chạy theo flavor khác:**

```bash
flutter run                                   # flavor development (mặc định)
flutter run -t lib/main_staging.dart          # flavor staging
flutter run -t lib/main_production.dart       # flavor production
```

**Khi đang sửa model/provider**, bật codegen chạy nền để khỏi build lại thủ công:

```bash
dart run build_runner watch --delete-conflicting-outputs
```

**Kiểm tra chất lượng:**

```bash
flutter analyze
flutter test
```

**Chạy trong Android Studio:**

1. `File → Open` → chọn thư mục gốc `PaySplit-FE` (không phải thư mục `android/`).
2. Chọn device ở thanh trên, chọn run configuration `main.dart` → bấm ▶.
3. Đổi flavor: `Run → Edit Configurations → Dart entrypoint` trỏ tới `lib/main_staging.dart`, và thêm `--dart-define=API_BASE_URL=...` vào ô *Additional run args*.

### Bước 3 — Kiểm tra kết nối giữa 2 project

Cấu hình Android đã xử lý sẵn để app debug gọi được `http://` local:

| Việc | Nơi cấu hình | Lý do |
| --- | --- | --- |
| Quyền `INTERNET` | `android/app/src/main/AndroidManifest.xml` | Manifest debug của Flutter có sẵn quyền này, nhưng **bản release thì không** |
| `usesCleartextTraffic="true"` | `android/app/src/debug/AndroidManifest.xml` | Android 9+ chặn HTTP không mã hoá. Chỉ bật cho debug, release vẫn bắt buộc HTTPS |

---

## 🔌 Hợp đồng API giữa FE và BE

Frontend đang giả định quy ước `snake_case` như dưới đây. **Cần đối chiếu lại với backend khi các handler được hiện thực xong:**

| Endpoint | Request | Response |
| --- | --- | --- |
| `POST /auth/register` | `{email, password, ...}` | `{access_token, refresh_token, user}` |
| `POST /auth/login` | `{email, password}` | `{access_token, refresh_token, user}` |
| `GET /auth/me` | — | `{id, name, email, avatar_url, phone_number}` |
| `GET /bills` | — | `[{id, title, total_amount, status, created_at}]` với `status` ∈ `"pending"` / `"settled"` |

Đặc tả chuẩn của backend nằm ở `PaySplit-BE/docs/openapi.yaml`.

---

## 🚧 Trạng thái hiện tại

**Backend:** layout, routing và interface đã dựng xong, nhưng nhiều implementation vẫn là scaffold và sẽ `panic("TODO: ...")` khi được gọi — cụ thể là `bootstrap.New`, `config.Load`, usecase auth, handler auth, repository postgres, code sqlc và bcrypt. Vì vậy `make run` hiện **chưa phục vụ được traffic**. Dùng `grep -rn "TODO:" cmd internal` để xem phần việc còn lại.

**Frontend:** `flutter analyze` sạch và `flutter test` pass, nhưng chưa chạy thử trên máy/emulator thật. Hai điểm còn treo:

* `retrofit` đang bị ghim ở `4.7.3` (bản 4.9.x xung đột với `retrofit_generator` 9.x; generator 10.x lại xung đột `build` với `freezed` 2.x). Gỡ ghim được khi nâng lên `freezed` 3.x.
* Refresh token chưa hiện thực — `AuthInterceptor` mới chỉ xoá token khi gặp 401. Logic gọi `/auth/refresh` rồi retry nên đặt ở repository, không nhét vào interceptor.

**Database:** backend mới có migration cho bảng `users`; các bảng còn lại (groups, bills, ledger, debts, notifications…) đã thiết kế trong `dbv1.sql` nhưng chưa chuyển thành migration.
