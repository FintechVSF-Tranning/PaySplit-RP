-- ============================================================================
-- PaySplit — PostgreSQL Schema (DDL)
-- Hệ thống chia tiền thông minh (Group Expense-Splitting Prototype)
-- Kiến trúc: Tinh gọn (No Ledger), Theo dõi hoạt động (Activity Tracking)
-- ============================================================================

-- Khởi tạo các extension cần thiết
CREATE EXTENSION IF NOT EXISTS citext;     -- Hỗ trợ kiểu dữ liệu text không phân biệt hoa thường (dùng cho email)

-- ---------------------------------------------------------------------------
-- 1. ENUM TYPES (Kiểu dữ liệu liệt kê)
-- ---------------------------------------------------------------------------
DO $$ BEGIN CREATE TYPE account_status   AS ENUM ('pending_verification','active','suspended','locked'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE group_role       AS ENUM ('captain','member'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE member_status    AS ENUM ('active','inactive'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE bill_status      AS ENUM ('draft','finalized'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE ocr_job_status   AS ENUM ('queued','processing','succeeded','failed'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE debt_status      AS ENUM ('awaiting','pending_confirmation','stalled_confirmation','rejected','settled'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE admin_action     AS ENUM ('suspend','lock','reactivate'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE token_type       AS ENUM ('email_verification', 'password_reset'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE user_role        AS ENUM ('user', 'admin'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE activity_type    AS ENUM ('created_bill', 'updated_bill', 'deleted_bill', 'finalized_bill', 'submitted_proof', 'confirmed_payment', 'stalled_payment_reminder'); EXCEPTION WHEN duplicate_object THEN null; END $$;

-- ---------------------------------------------------------------------------
-- 2. USERS & AUTH (Người dùng & Xác thực)
-- ---------------------------------------------------------------------------

-- Bảng users: Lưu trữ thông tin cá nhân và cấu hình tài khoản ngân hàng.
CREATE TABLE IF NOT EXISTS users (
    id                          UUID PRIMARY KEY,
    email                       CITEXT NOT NULL UNIQUE, -- Email đăng nhập (không phân biệt hoa/thường)
    password_hash               TEXT NOT NULL,          -- Mật khẩu đã mã hóa (Bắt buộc vì chỉ dùng đăng nhập thường)
    display_name                TEXT NOT NULL,          -- Tên hiển thị trong nhóm
    avatar_object_key           TEXT,                   -- Đường dẫn lưu ảnh đại diện (trên S3/Object Storage)
    phone_number                TEXT,                   -- Số điện thoại liên hệ
    default_bank_code           TEXT,                   -- Mã ngân hàng NAPAS (VD: VCB, TCB) để tạo VietQR
    default_bank_account_number TEXT,                   -- Số tài khoản ngân hàng mặc định nhận tiền
    default_bank_account_holder TEXT,                   -- Tên chủ tài khoản
    role                        user_role NOT NULL DEFAULT 'user',
    status                      account_status NOT NULL DEFAULT 'pending_verification', -- Trạng thái tài khoản
    email_verified_at           TIMESTAMPTZ,            -- Thời điểm xác thực email
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bảng sessions: Quản lý các phiên đăng nhập để hỗ trợ tính năng đăng xuất (Revoke Refresh Token).
CREATE TABLE IF NOT EXISTS sessions (
    id                  UUID PRIMARY KEY,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id           TEXT NOT NULL,          -- ID thiết bị của người dùng
    refresh_token_hash  TEXT NOT NULL,          -- Mã hóa của Refresh Token
    issued_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ NOT NULL,   -- Hạn sử dụng của token
    revoked_at          TIMESTAMPTZ             -- Thời điểm token bị thu hồi (đăng xuất)
);
CREATE INDEX IF NOT EXISTS idx_sessions_active_by_user ON sessions(user_id) WHERE revoked_at IS NULL;

-- Bảng user_tokens: Gộp chung các loại token xác thực dùng 1 lần (quên mật khẩu, xác minh email)
CREATE TABLE IF NOT EXISTS user_tokens (
    id          UUID PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type        token_type NOT NULL,    -- Phân loại: 'email_verification' hoặc 'password_reset'
    token_hash  TEXT NOT NULL UNIQUE,   -- Chuỗi mã hóa của token
    expires_at  TIMESTAMPTZ NOT NULL,   -- Hạn sử dụng của token
    used_at     TIMESTAMPTZ,            -- Đánh dấu thời điểm đã sử dụng (NULL = chưa dùng)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 3. GROUPS (Quản lý Nhóm chi tiêu)
-- ---------------------------------------------------------------------------

-- Bảng groups: Lưu trữ thông tin cơ bản của nhóm chi tiêu.
CREATE TABLE IF NOT EXISTS groups (
    id          UUID PRIMARY KEY,
    name        TEXT NOT NULL,                          -- Tên nhóm (VD: Du lịch Đà Lạt)
    currency    TEXT NOT NULL DEFAULT 'VND',            -- Tiền tệ sử dụng
    created_by  UUID NOT NULL REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bảng group_members (Quan trọng): 
-- Đây là bảng "Mỏ neo" (Anchor). Các bảng hóa đơn (bills) và sổ cái (ledger) sẽ trỏ về bảng này thay vì users.
-- Giúp lưu lại lịch sử đóng góp kể cả khi thành viên rời nhóm (status = inactive).
CREATE TABLE IF NOT EXISTS group_members (
    id          UUID PRIMARY KEY,
    group_id    UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id),
    role        group_role NOT NULL DEFAULT 'member',   -- Vai trò (captain hoặc member)
    status      member_status NOT NULL DEFAULT 'active',-- active: Đang trong nhóm, inactive: Đã rời nhóm
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at     TIMESTAMPTZ,
    UNIQUE (group_id, user_id),
    UNIQUE (id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_group_members_user  ON group_members(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_group_members_active_captain
    ON group_members(group_id) WHERE role = 'captain' AND status = 'active';

-- Bảng group_invites: Quản lý các link/mã mời để người khác tham gia nhóm.
CREATE TABLE IF NOT EXISTS group_invites (
    id          UUID PRIMARY KEY,
    group_id    UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    code        TEXT NOT NULL UNIQUE,                   -- Mã mời (chuỗi ngẫu nhiên)
    created_by  UUID NOT NULL REFERENCES group_members(id),
    expires_at  TIMESTAMPTZ NOT NULL,                   -- Hạn sử dụng của mã mời
    max_uses    INT,                                    -- Số lần sử dụng tối đa (NULL = không giới hạn)
    use_count   INT NOT NULL DEFAULT 0,                 -- Số lần đã sử dụng
    revoked_at  TIMESTAMPTZ,                            -- Thời điểm mã mời bị vô hiệu hóa
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_group_invites_active ON group_invites(group_id) WHERE revoked_at IS NULL;

-- ---------------------------------------------------------------------------
-- 4. BILLS (Quản lý Hóa đơn & Phân bổ Tinh gọn)
-- ---------------------------------------------------------------------------

-- Bảng bills: Thông tin chung của một hóa đơn.
CREATE TABLE IF NOT EXISTS bills (
    id                  UUID PRIMARY KEY,
    group_id            UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    creditor_member_id  UUID NOT NULL,                              -- Người đã ứng tiền trả hóa đơn này
    status              bill_status NOT NULL DEFAULT 'draft',       -- 'draft' (đang nháp) hoặc 'finalized' (đã chốt)
    merchant_name       TEXT,                                       -- Tên cửa hàng/quán ăn
    bill_date           DATE,                                       -- Ngày trên hóa đơn
    image_object_key    TEXT,                                       -- File ảnh hóa đơn chụp lại
    subtotal            BIGINT NOT NULL DEFAULT 0,                  -- Tổng tiền hàng (trước thuế phí)
    service_charge      BIGINT NOT NULL DEFAULT 0,                  -- Phí dịch vụ
    vat                 BIGINT NOT NULL DEFAULT 0,                  -- Thuế VAT
    discount            BIGINT NOT NULL DEFAULT 0,                  -- Tiền giảm giá
    total               BIGINT NOT NULL DEFAULT 0,                  -- Tổng tiền cuối cùng
    is_no_split         BOOLEAN NOT NULL DEFAULT false,             -- BỔ SUNG: TRUE nếu hóa đơn chỉ dùng để lưu trữ/track chi tiêu, không tính toán công nợ
	mismatch_warning    BOOLEAN NOT NULL DEFAULT false,             -- Cảnh báo nếu OCR quét tổng tiền không khớp chi tiết
    version             INT NOT NULL DEFAULT 1,                     -- Dùng cho Optimistic Locking (chống sửa đồng thời)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalized_at        TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (subtotal >= 0 AND service_charge >= 0 AND vat >= 0 AND discount >= 0 AND total >= 0),
    UNIQUE (id, group_id),
    FOREIGN KEY (creditor_member_id, group_id) REFERENCES group_members(id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_bills_group ON bills(group_id);
CREATE INDEX IF NOT EXISTS idx_bills_group_status ON bills(group_id, status);

-- Bảng bill_items: Danh sách các món ăn/dịch vụ trong hóa đơn.
CREATE TABLE IF NOT EXISTS bill_items (
    id          UUID PRIMARY KEY,
    bill_id     UUID NOT NULL,
    group_id    UUID NOT NULL,
    name        TEXT NOT NULL,                          -- Tên món
    quantity    NUMERIC(10,2) NOT NULL DEFAULT 1,       -- Số lượng (có thể là số thập phân nếu chia kg)
    unit_price  BIGINT NOT NULL,                        -- Đơn giá
    line_total  BIGINT NOT NULL,                        -- Tổng tiền của món = quantity * unit_price
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (unit_price >= 0 AND line_total >= 0),
    UNIQUE (id, group_id),
    FOREIGN KEY (bill_id, group_id) REFERENCES bills(id, group_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_bill_items_bill ON bill_items(bill_id);

-- Bảng bill_item_assignments: Ghi nhận thành viên nào gánh món nào.
CREATE TABLE IF NOT EXISTS bill_item_assignments (
    id            UUID PRIMARY KEY,
    bill_item_id  UUID NOT NULL,
    group_id      UUID NOT NULL,
    member_id     UUID NOT NULL, 
    weight        NUMERIC(10,4) NOT NULL DEFAULT 1,     
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (weight > 0),
    FOREIGN KEY (bill_item_id, group_id) REFERENCES bill_items(id, group_id) ON DELETE CASCADE,
    FOREIGN KEY (member_id, group_id) REFERENCES group_members(id, group_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_bill_item_assignment_member ON bill_item_assignments(bill_item_id, member_id);

-- ---------------------------------------------------------------------------
-- 5. GROUP ACTIVITIES (Nhật ký nhóm - Thay thế Sổ cái)
-- ---------------------------------------------------------------------------

-- Bảng group_activities: Lưu mọi biến động (Thêm/Sửa/Xóa hóa đơn, Trả nợ) để đối chiếu
CREATE TABLE IF NOT EXISTS group_activities (
    id              UUID PRIMARY KEY,
    group_id        UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    actor_member_id UUID NOT NULL REFERENCES group_members(id),
    action_type     activity_type NOT NULL,
    description     TEXT NOT NULL,                              -- Ví dụ: "Nam đã chốt hóa đơn Ăn trưa"
    metadata        JSONB,                                      -- Dữ liệu phụ: {"bill_id": "...", "total": 300000}
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_group_activities_group ON group_activities(group_id);
CREATE INDEX IF NOT EXISTS idx_group_activities_created ON group_activities(created_at DESC);

-- ---------------------------------------------------------------------------
-- 6. OCR (Tiến trình trích xuất hình ảnh)
-- ---------------------------------------------------------------------------

-- Bảng ocr_jobs: Theo dõi trạng thái công việc gửi ảnh cho AI đọc.
CREATE TABLE IF NOT EXISTS ocr_jobs (
    id             UUID PRIMARY KEY,
    bill_id        UUID NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    status         ocr_job_status NOT NULL DEFAULT 'queued',
    provider       TEXT NOT NULL DEFAULT 'gemini-flash',
    attempts       INT NOT NULL DEFAULT 0,
    raw_response   JSONB,                               -- Kết quả gốc trả về từ AI
    error_message  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_ocr_jobs_bill ON ocr_jobs(bill_id);
CREATE INDEX IF NOT EXISTS idx_ocr_jobs_pending ON ocr_jobs(status) WHERE status IN ('queued','processing');

-- ---------------------------------------------------------------------------
-- 7. DEBTS (Nợ, Truy vết nguồn gốc & Thanh toán thủ công)
-- ---------------------------------------------------------------------------

-- Bảng debts: Lưu công nợ tổng hợp 1-1. Đã gỡ bỏ bill_id để hỗ trợ gộp nợ từ nhiều bill.
CREATE TABLE IF NOT EXISTS debts (
    id                          UUID PRIMARY KEY,
    group_id                    UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    debtor_member_id            UUID NOT NULL REFERENCES group_members(id),  -- Người phải trả
    creditor_member_id          UUID NOT NULL REFERENCES group_members(id),  -- Người nhận tiền
    amount                      BIGINT NOT NULL CHECK (amount > 0),          -- Tổng số tiền nợ
    reference_code              TEXT NOT NULL UNIQUE,                        -- Mã nội dung chuyển khoản
    qr_payload                  TEXT,                                        -- Chuỗi tạo mã QR
    status                      debt_status NOT NULL DEFAULT 'awaiting',     
    reminder_count              INT NOT NULL DEFAULT 0,                      -- Số lần nhắc nhở
    rejection_reason            TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    rejected_at                 TIMESTAMPTZ,
    settled_at                  TIMESTAMPTZ,                                 
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (debtor_member_id <> creditor_member_id),
    CHECK (
        (status = 'rejected' AND rejected_at IS NOT NULL AND rejection_reason IS NOT NULL)
        OR
        (status <> 'rejected' AND rejected_at IS NULL AND rejection_reason IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_debts_group ON debts(group_id);
CREATE INDEX IF NOT EXISTS idx_debts_unsettled ON debts(debtor_member_id) WHERE status <> 'settled';

-- Bảng debt_sources (MỚI): Truy vết chi tiết khoản nợ đến từ đâu
CREATE TABLE IF NOT EXISTS debt_sources (
    id            UUID PRIMARY KEY,
    debt_id       UUID NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    bill_id       UUID NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    bill_item_id  UUID REFERENCES bill_items(id) ON DELETE CASCADE, -- Cho phép NULL nếu khoản tiền này là chia tiền Thuế (VAT)/Phí dịch vụ của cả hóa đơn
    amount        BIGINT NOT NULL CHECK (amount > 0),               -- Số tiền đóng góp từ item/bill này vào tổng nợ
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_debt_sources_debt ON debt_sources(debt_id);
CREATE INDEX IF NOT EXISTS idx_debt_sources_bill ON debt_sources(bill_id);
CREATE INDEX IF NOT EXISTS idx_debt_sources_item ON debt_sources(bill_item_id);

-- Bảng payment_proofs: Bằng chứng (ảnh chụp màn hình CK) do Payer tải lên.
CREATE TABLE IF NOT EXISTS payment_proofs (
    id                UUID PRIMARY KEY,
    debt_id           UUID NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    submitted_by      UUID NOT NULL REFERENCES group_members(id),
    image_object_key  TEXT,                         
    note              TEXT,                         
    submitted_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payment_proofs_debt ON payment_proofs(debt_id);

-- ---------------------------------------------------------------------------
-- 8. NOTIFICATIONS & ADMIN (Thông báo & Quản trị)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS notifications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type        TEXT NOT NULL,                      
    payload     JSONB,                              
    read_at     TIMESTAMPTZ,                        
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id        UUID NOT NULL REFERENCES users(id),
    target_user_id  UUID NOT NULL REFERENCES users(id),
    action          admin_action NOT NULL,          
    reason          TEXT NOT NULL,                  
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 9. AUTOMATIC TIMESTAMPS (Tự động cập nhật updated_at)
-- ---------------------------------------------------------------------------

-- Dùng chung cho mọi bảng có cột updated_at.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_set_updated_at ON users;
CREATE TRIGGER trg_users_set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_bills_set_updated_at ON bills;
CREATE TRIGGER trg_bills_set_updated_at
    BEFORE UPDATE ON bills
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_bill_items_set_updated_at ON bill_items;
CREATE TRIGGER trg_bill_items_set_updated_at
    BEFORE UPDATE ON bill_items
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_ocr_jobs_set_updated_at ON ocr_jobs;
CREATE TRIGGER trg_ocr_jobs_set_updated_at
    BEFORE UPDATE ON ocr_jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_debts_set_updated_at ON debts;
CREATE TRIGGER trg_debts_set_updated_at
    BEFORE UPDATE ON debts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
