-- ============================================================================
-- PaySplit — PostgreSQL Schema (DDL)
-- Hệ thống chia tiền thông minh (Group Expense-Splitting Prototype)
-- ============================================================================

-- Khởi tạo các extension cần thiết (An toàn khi chạy nhiều lần)
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- Hỗ trợ sinh UUID (gen_random_uuid)
CREATE EXTENSION IF NOT EXISTS citext;     -- Hỗ trợ kiểu dữ liệu text không phân biệt hoa thường (dùng cho email)

-- ---------------------------------------------------------------------------
-- 1. ENUM TYPES (Kiểu dữ liệu liệt kê)
-- Sử dụng DO block để đảm bảo an toàn (IF NOT EXISTS) khi chạy migration
-- ---------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE account_status   AS ENUM ('pending_verification','active','suspended','locked');
    CREATE TYPE group_role       AS ENUM ('captain','member');
    CREATE TYPE member_status    AS ENUM ('active','inactive');
    CREATE TYPE bill_status      AS ENUM ('draft','finalized');
    CREATE TYPE ocr_job_status   AS ENUM ('queued','processing','succeeded','failed');
    CREATE TYPE ledger_txn_type  AS ENUM ('bill_finalize','settlement','reversal');
    -- Đã thêm trạng thái 'stalled_confirmation' cho logic nhắc nhở quá hạn
    CREATE TYPE debt_status      AS ENUM ('awaiting','pending_confirmation','stalled_confirmation','settled');
    CREATE TYPE admin_action     AS ENUM ('suspend','lock','reactivate');
	CREATE TYPE token_type       AS ENUM ('email_verification', 'password_reset');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- ---------------------------------------------------------------------------
-- 2. USERS & AUTH (Người dùng & Xác thực)
-- ---------------------------------------------------------------------------

-- Bảng users: Lưu trữ thông tin cá nhân, mật khẩu đăng nhập và cấu hình tài khoản ngân hàng.
CREATE TABLE IF NOT EXISTS users (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email                       CITEXT NOT NULL UNIQUE, -- Email đăng nhập (không phân biệt hoa/thường)
    password_hash               TEXT NOT NULL,          -- Mật khẩu đã mã hóa (Bắt buộc vì chỉ dùng đăng nhập thường)
    display_name                TEXT NOT NULL,          -- Tên hiển thị trong nhóm
    avatar_object_key           TEXT,                   -- Đường dẫn lưu ảnh đại diện (trên S3/Object Storage)
    phone_number                TEXT,                   -- Số điện thoại liên hệ
    default_bank_code           TEXT,                   -- Mã ngân hàng NAPAS (VD: VCB, TCB) để tạo VietQR
    default_bank_account_number TEXT,                   -- Số tài khoản ngân hàng mặc định nhận tiền
    default_bank_account_holder TEXT,                   -- Tên chủ tài khoản
    status                      account_status NOT NULL DEFAULT 'pending_verification', -- Trạng thái tài khoản
    email_verified_at           TIMESTAMPTZ,            -- Thời điểm xác thực email
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bảng auth_identities: Tách biệt định danh đăng nhập để dễ dàng mở rộng Social Login (Google, Apple) sau này.
CREATE TABLE IF NOT EXISTS auth_identities (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider       TEXT NOT NULL DEFAULT 'password',   -- Phương thức đăng nhập: 'password', 'google', v.v.
    provider_uid   TEXT,                               -- ID do Google/Apple trả về (NULL nếu dùng password)
    password_hash  TEXT,                               -- Mật khẩu đã mã hóa (NULL nếu là social login)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, provider),
    UNIQUE (provider, provider_uid)
);

-- Bảng sessions: Quản lý các phiên đăng nhập để hỗ trợ tính năng đăng xuất (Revoke Refresh Token).
CREATE TABLE IF NOT EXISTS sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,                          -- Tên nhóm (VD: Du lịch Đà Lạt)
    currency    TEXT NOT NULL DEFAULT 'VND',            -- Tiền tệ sử dụng
    created_by  UUID NOT NULL REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bảng group_members (Quan trọng): 
-- Đây là bảng "Mỏ neo" (Anchor). Các bảng hóa đơn (bills) và sổ cái (ledger) sẽ trỏ về bảng này thay vì users.
-- Giúp lưu lại lịch sử đóng góp kể cả khi thành viên rời nhóm (status = inactive).
CREATE TABLE IF NOT EXISTS group_members (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id    UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id),
    role        group_role NOT NULL DEFAULT 'member',   -- Vai trò (captain hoặc member)
    status      member_status NOT NULL DEFAULT 'active',-- active: Đang trong nhóm, inactive: Đã rời nhóm
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at     TIMESTAMPTZ,
    UNIQUE (group_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_group_members_user  ON group_members(user_id);

-- Bảng group_invites: Quản lý các link/mã mời để người khác tham gia nhóm.
CREATE TABLE IF NOT EXISTS group_invites (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
-- 4. BILLS (Quản lý Hóa đơn & Phân bổ)
-- ---------------------------------------------------------------------------

-- Bảng bills: Thông tin chung của một hóa đơn.
CREATE TABLE IF NOT EXISTS bills (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id            UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    creditor_member_id  UUID NOT NULL REFERENCES group_members(id), -- Người đã ứng tiền trả hóa đơn này
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
    CHECK (subtotal >= 0 AND service_charge >= 0 AND vat >= 0 AND discount >= 0 AND total >= 0)
);
CREATE INDEX IF NOT EXISTS idx_bills_group ON bills(group_id);
CREATE INDEX IF NOT EXISTS idx_bills_group_status ON bills(group_id, status);

-- Bảng bill_items: Danh sách các món ăn/dịch vụ trong hóa đơn.
CREATE TABLE IF NOT EXISTS bill_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bill_id     UUID NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,                          -- Tên món
    quantity    NUMERIC(10,2) NOT NULL DEFAULT 1,       -- Số lượng (có thể là số thập phân nếu chia kg)
    unit_price  BIGINT NOT NULL,                        -- Đơn giá
    line_total  BIGINT NOT NULL,                        -- Tổng tiền của món = quantity * unit_price
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (unit_price >= 0 AND line_total >= 0)
);
CREATE INDEX IF NOT EXISTS idx_bill_items_bill ON bill_items(bill_id);

-- Bảng bill_item_assignments: Ghi nhận thành viên nào dùng món nào.
CREATE TABLE IF NOT EXISTS bill_item_assignments (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bill_item_id  UUID NOT NULL REFERENCES bill_items(id) ON DELETE CASCADE,
    member_id     UUID NOT NULL REFERENCES group_members(id), 			-- Ép buộc NOT NULL. Nếu Creditor tự chịu, gán thẳng ID của Creditor vào đây.
    weight        NUMERIC(10,4) NOT NULL DEFAULT 1,     				-- Trọng số (nếu người ăn nhiều, người ăn ít)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (weight > 0)
);
CREATE INDEX IF NOT EXISTS idx_bill_item_assignments_item   ON bill_item_assignments(bill_item_id);
CREATE INDEX IF NOT EXISTS idx_bill_item_assignments_member ON bill_item_assignments(member_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_bill_item_assignment_member ON bill_item_assignments(bill_item_id, member_id);

-- Bảng bill_participant_shares: Lưu kết quả (Snapshot) số tiền chính xác mỗi người phải trả sau khi Finalize.
CREATE TABLE IF NOT EXISTS bill_participant_shares (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bill_id              UUID NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    member_id            UUID NOT NULL REFERENCES group_members(id),
    share_amount         BIGINT NOT NULL,               -- Phần tiền phải chịu
    rounding_adjustment  BIGINT NOT NULL DEFAULT 0,     -- Tiền điều chỉnh làm tròn (Thuật toán Hamilton chia phần lẻ)
    UNIQUE (bill_id, member_id),
    CHECK (share_amount >= 0)
);

-- ---------------------------------------------------------------------------
-- 5. OCR (Tiến trình trích xuất hình ảnh)
-- ---------------------------------------------------------------------------

-- Bảng ocr_jobs: Theo dõi trạng thái công việc gửi ảnh cho AI đọc.
CREATE TABLE IF NOT EXISTS ocr_jobs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
-- 6. SỔ CÁI KÉP (Ledger - Đảm bảo chính xác tài chính)
-- ---------------------------------------------------------------------------

-- Bảng ledger_transactions: Lịch sử giao dịch sổ cái.
CREATE TABLE IF NOT EXISTS ledger_transactions (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id                    UUID NOT NULL REFERENCES groups(id),
    type                        ledger_txn_type NOT NULL,   -- Loại GD: chốt bill, thanh toán nợ, hoặc hoàn tác
    bill_id                     UUID REFERENCES bills(id),
    debt_id                     UUID,                       -- Khóa ngoại trỏ đến debts (tạo sau bằng ALTER)
    reversal_of_transaction_id  UUID REFERENCES ledger_transactions(id),
    created_by                  UUID REFERENCES group_members(id),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ledger_txn_group ON ledger_transactions(group_id);
CREATE INDEX IF NOT EXISTS idx_ledger_txn_bill  ON ledger_transactions(bill_id);

-- Bảng ledger_postings: Dòng tiền thực tế của từng cá nhân (Luôn bất biến - Append only).
CREATE TABLE IF NOT EXISTS ledger_postings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id  UUID NOT NULL REFERENCES ledger_transactions(id) ON DELETE CASCADE,
    member_id       UUID NOT NULL REFERENCES group_members(id),
    amount          BIGINT NOT NULL,   -- Mức tiền: Dương (+) là số tiền được nhận, Âm (-) là số tiền mắc nợ
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ledger_postings_txn    ON ledger_postings(transaction_id);
CREATE INDEX IF NOT EXISTS idx_ledger_postings_member ON ledger_postings(member_id);

-- Trigger đảm bảo Sổ Cái cân bằng: Tổng amount trong 1 transaction luôn phải bằng 0.
CREATE OR REPLACE FUNCTION check_ledger_transaction_balanced()
RETURNS TRIGGER AS $$
DECLARE
    total BIGINT;
    txn_id UUID := COALESCE(NEW.transaction_id, OLD.transaction_id);
BEGIN
    SELECT COALESCE(SUM(amount), 0) INTO total
    FROM ledger_postings WHERE transaction_id = txn_id;

    IF total <> 0 THEN
        RAISE EXCEPTION 'Ledger transaction % is not balanced (sum = %)', txn_id, total;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ledger_balanced ON ledger_postings;
CREATE CONSTRAINT TRIGGER trg_ledger_balanced
    AFTER INSERT OR UPDATE OR DELETE ON ledger_postings
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_ledger_transaction_balanced();

-- ---------------------------------------------------------------------------
-- 7. DEBTS (Nợ & Thanh toán thủ công, Tạo mã QR)
-- ---------------------------------------------------------------------------

-- Bảng debts: Lưu công nợ 1-1 giữa 2 thành viên (đã được tối giản hóa từ Sổ Cái).
CREATE TABLE IF NOT EXISTS debts (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id                    UUID NOT NULL REFERENCES groups(id),
    bill_id                     UUID NOT NULL REFERENCES bills(id),
    debtor_member_id            UUID NOT NULL REFERENCES group_members(id), -- Người phải trả
    creditor_member_id          UUID NOT NULL REFERENCES group_members(id), -- Người nhận tiền
    amount                      BIGINT NOT NULL CHECK (amount > 0),         -- Số tiền nợ
    reference_code              TEXT NOT NULL UNIQUE,                       -- Mã nội dung CK (dành cho VietQR và đối soát thủ công)
    qr_payload                  TEXT,                                       -- Chuỗi QR string
    status                      debt_status NOT NULL DEFAULT 'awaiting',    -- Trạng thái khoản nợ
    reminder_count              INT NOT NULL DEFAULT 0,                     -- Số lần đã thông báo nhắc Creditor xác nhận
    settlement_transaction_id   UUID REFERENCES ledger_transactions(id),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    settled_at                  TIMESTAMPTZ,                                -- Thời điểm trả nợ xong
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (debtor_member_id <> creditor_member_id)
);
CREATE INDEX IF NOT EXISTS idx_debts_group      ON debts(group_id);
CREATE INDEX IF NOT EXISTS idx_debts_debtor     ON debts(debtor_member_id);
CREATE INDEX IF NOT EXISTS idx_debts_creditor   ON debts(creditor_member_id);
CREATE INDEX IF NOT EXISTS idx_debts_unsettled  ON debts(status) WHERE status <> 'settled';

-- Cập nhật khóa ngoại chéo (Dùng DO block để tránh lỗi nếu đã tồn tại)
DO $$ BEGIN
    ALTER TABLE ledger_transactions ADD CONSTRAINT fk_ledger_txn_debt FOREIGN KEY (debt_id) REFERENCES debts(id);
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Bảng payment_proofs: Bằng chứng (ảnh chụp màn hình CK) do Payer tải lên.
CREATE TABLE IF NOT EXISTS payment_proofs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    debt_id           UUID NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    submitted_by      UUID NOT NULL REFERENCES group_members(id),
    image_object_key  TEXT,                         -- Link ảnh bill chuyển khoản
    note              TEXT,                         -- Lời nhắn
    submitted_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payment_proofs_debt ON payment_proofs(debt_id);

-- ---------------------------------------------------------------------------
-- 8. NOTIFICATIONS & ADMIN (Thông báo & Quản trị)
-- ---------------------------------------------------------------------------

-- Bảng notifications: Lưu trữ thông báo Push gửi cho User.
CREATE TABLE IF NOT EXISTS notifications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type        TEXT NOT NULL,                      -- Loại (VD: debt_reminder, payment_confirmed)
    payload     JSONB,                              -- Dữ liệu động JSON đính kèm
    read_at     TIMESTAMPTZ,                        -- Nếu NULL là chưa đọc
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id) WHERE read_at IS NULL;

-- Bảng admin_audit_logs: Theo dõi hành động của Admin lên hệ thống.
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id        UUID NOT NULL REFERENCES users(id),
    target_user_id  UUID NOT NULL REFERENCES users(id),
    action          admin_action NOT NULL,          -- Hành động (khóa/mở tài khoản)
    reason          TEXT NOT NULL,                  -- Lý do xử lý
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_target ON admin_audit_logs(target_user_id);

-- ---------------------------------------------------------------------------
-- 9. DERIVED VIEWS (Tính toán thời gian thực - Không lưu trữ cứng)
-- ---------------------------------------------------------------------------

-- View group_member_balances: Tính số dư hiện tại của từng cá nhân trong mỗi nhóm.
-- Lấy tổng amount từ bảng ledger_postings. 
-- Nếu balance > 0: Người này đang dư tiền (Cho người khác vay).
-- Nếu balance < 0: Người này đang nợ tiền.
CREATE OR REPLACE VIEW group_member_balances AS
SELECT
    gm.group_id,
    gm.id       AS member_id,
    gm.user_id,
    COALESCE(SUM(lp.amount), 0) AS balance
FROM group_members gm
LEFT JOIN ledger_postings lp ON lp.member_id = gm.id
GROUP BY gm.group_id, gm.id, gm.user_id;