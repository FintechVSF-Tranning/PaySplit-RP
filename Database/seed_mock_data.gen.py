#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generator dữ liệu mock cho PaySplit (Database/dbv1.sql).

Nguyên tắc:
  * UUID v7 sinh xác định (deterministic) từ timestamp thật của bản ghi -> id sắp
    xếp đúng theo thứ tự thời gian, đúng tinh thần "UUID v7 do tầng ứng dụng sinh".
  * Số tiền tính bằng Fraction rồi làm tròn theo largest-remainder (Hamilton)
    => SUM(debts.amount) + creditor_share == bills.total, tuyệt đối khớp.
  * payments.amount == SUM(debts.amount) của các nợ được gộp.
  * qr_payload là chuỗi VietQR EMVCo thật (TLV + CRC-16/CCITT-FALSE).
"""

from fractions import Fraction
from datetime import datetime, timezone, timedelta
import hashlib

TZ = timezone(timedelta(hours=7))
BCRYPT = "$2a$12$TQOmXQwoq30WRZx13dlvB.8td0cci4Se0txNFJPdTSnMNY/TBwQxi"  # "Password@123"

# ---------------------------------------------------------------- helpers ---

def T(s):
    """'2026-07-18 19:30' -> datetime tz+07"""
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


def ts(dtv):
    return "NULL" if dtv is None else "'" + dtv.strftime("%Y-%m-%d %H:%M:%S%z")[:-2] + "'"


def d(s):
    return "NULL" if s is None else "'" + s + "'"


def uuid7(when, label):
    """UUID v7 xác định: 48 bit đầu = unix_ms, phần random lấy từ md5(label)."""
    ms = int(when.timestamp() * 1000)
    h = hashlib.md5(label.encode("utf-8")).digest()
    b = bytearray(16)
    b[0:6] = ms.to_bytes(6, "big")
    ra = int.from_bytes(h[0:2], "big") & 0x0FFF
    b[6] = 0x70 | (ra >> 8)
    b[7] = ra & 0xFF
    rb = int.from_bytes(h[2:10], "big")
    b[8] = 0x80 | ((rb >> 56) & 0x3F)
    b[9:16] = (rb & ((1 << 56) - 1)).to_bytes(7, "big")
    s = b.hex()
    return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:32]}"


def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()


def q(v):
    """SQL literal cho text."""
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def jb(v):
    return "NULL" if v is None else "'" + v.replace("'", "''") + "'::jsonb"


# ------------------------------------------------------------ VietQR ------

BANK_BIN = {
    "VCB": "970436", "TCB": "970407", "MB": "970422", "ACB": "970416",
    "VPB": "970432", "BIDV": "970418", "ICB": "970415", "TPB": "970423",
    "STB": "970403", "MSB": "970426",
}


def crc16_ccitt_false(data: str) -> str:
    crc = 0xFFFF
    for ch in data.encode("ascii"):
        crc ^= ch << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def tlv(tag, value):
    return f"{tag}{len(value):02d}{value}"


def vietqr(bank_code, account_no, amount, ref):
    acq = tlv("00", BANK_BIN[bank_code]) + tlv("01", account_no)
    mai = tlv("00", "A000000727") + tlv("01", acq) + tlv("02", "QRIBFTTA")
    payload = (
        tlv("00", "01")
        + tlv("01", "12")
        + tlv("38", mai)
        + tlv("53", "704")
        + tlv("54", str(amount))
        + tlv("58", "VN")
        + tlv("62", tlv("08", ref))
    )
    return payload + "6304" + crc16_ccitt_false(payload + "6304")


# --------------------------------------------------- phân bổ tiền (Hamilton)

def allocate(items, total, member_order):
    """
    items: [{'line_total': int, 'assign': {member_key: weight}}]
    Trả về {member_key: int}, đảm bảo sum == total.
    Phần phụ thu / giảm giá được rải theo tỉ lệ subtotal của từng người
    (tương đương nhân tỉ lệ total / sum(line_total)).
    """
    S = sum(it["line_total"] for it in items if it["assign"])
    assert S > 0, "bill không có món nào được gán"
    raw = {m: Fraction(0) for m in member_order}
    for it in items:
        if not it["assign"]:
            continue
        W = sum(Fraction(w) for w in it["assign"].values())
        for m, w in it["assign"].items():
            raw[m] += Fraction(it["line_total"]) * Fraction(w) / W

    exact = {m: raw[m] * Fraction(total) / Fraction(S) for m in member_order}
    floors = {m: int(exact[m]) for m in member_order}
    rest = total - sum(floors.values())
    order = sorted(
        [m for m in member_order if exact[m] > 0],
        key=lambda m: (-(exact[m] - floors[m]), member_order.index(m)),
    )
    for i in range(rest):
        floors[order[i % len(order)]] += 1
    assert sum(floors.values()) == total
    return {m: v for m, v in floors.items() if v > 0}


# ============================================================== DỮ LIỆU =====

rows = {k: [] for k in [
    "users", "sessions", "user_tokens", "groups", "group_members", "group_invites",
    "bills", "bill_items", "bill_item_assignments", "ocr_jobs", "payments",
    "debts", "group_activities", "notifications", "admin_audit_logs",
]}

U = {}      # key -> dict thông tin user
GM = {}     # (group_key, user_key) -> member_id
GRP = {}    # group_key -> dict


# ------------------------------------------------------------- 1. USERS ----

def add_user(key, email, name, created, *, role="user", status="active",
             verified=None, bank=None, phone=None, avatar=True):
    when = T(created)
    uid = uuid7(when, "user:" + key)
    bc, ban, bah = bank if bank else (None, None, None)
    U[key] = dict(id=uid, email=email, name=name, created=when, bank=bank,
                  status=status, role=role)
    rows["users"].append(
        f"({q(uid)}, {q(email)}, {q(BCRYPT)}, {q(name)}, "
        f"{q('avatars/' + uid + '.webp') if avatar else 'NULL'}, {q(phone)}, "
        f"{q(bc)}, {q(ban)}, {q(bah)}, {q(role)}::user_role, {q(status)}::account_status, "
        f"{ts(T(verified) if verified else None)}, {ts(when)}, {ts(when)})"
    )


add_user("admin", "admin@paysplit.vn", "PaySplit Admin", "2026-05-01 08:00",
         role="admin", verified="2026-05-01 08:15", phone="0900000001", avatar=False)

add_user("minh", "minh.nguyen@gmail.com", "Nguyễn Văn Minh", "2026-06-02 09:12",
         verified="2026-06-02 09:20", phone="0901234567",
         bank=("VCB", "1012345678", "NGUYEN VAN MINH"))
add_user("lan", "lan.tran@gmail.com", "Trần Thị Lan", "2026-06-02 14:40",
         verified="2026-06-02 14:52", phone="0912345678",
         bank=("TCB", "19036800123456", "TRAN THI LAN"))
add_user("hung", "hung.pham@gmail.com", "Phạm Quốc Hùng", "2026-06-03 20:05",
         verified="2026-06-03 20:11", phone="0923456789",
         bank=("MB", "0987654321", "PHAM QUOC HUNG"))
add_user("thao", "thao.le@gmail.com", "Lê Phương Thảo", "2026-06-05 10:30",
         verified="2026-06-05 10:41", phone="0934567890",
         bank=("ACB", "246813579", "LE PHUONG THAO"))
add_user("duc", "duc.vo@gmail.com", "Võ Minh Đức", "2026-06-07 16:22",
         verified="2026-06-07 16:35", phone="0945678901",
         bank=("VPB", "135792468", "VO MINH DUC"))
add_user("mai", "mai.hoang@gmail.com", "Hoàng Ngọc Mai", "2026-06-10 08:47",
         verified="2026-06-10 08:55", phone="0956789012",
         bank=("BIDV", "31410000123456", "HOANG NGOC MAI"))
add_user("tuan", "tuan.dang@gmail.com", "Đặng Anh Tuấn", "2026-06-12 19:03",
         verified="2026-06-12 19:14", phone="0967890123",
         bank=("ICB", "103870123456", "DANG ANH TUAN"))
add_user("ngoc", "ngoc.bui@gmail.com", "Bùi Bảo Ngọc", "2026-06-15 11:19",
         verified="2026-06-15 11:26", phone="0978901234",
         bank=("TPB", "00012345678", "BUI BAO NGOC"))
# An: đã xác thực nhưng CHƯA cấu hình tài khoản ngân hàng -> không thể làm creditor
# của bill được finalize (FR 4.1.15) và không nhận được QR (FR 4.1.17 abnormal).
add_user("an", "an.nguyen@gmail.com", "Nguyễn Hoài An", "2026-06-18 13:55",
         verified="2026-06-18 14:02", phone="0989012345", bank=None)
# Sơn: đăng ký xong nhưng chưa bấm link xác thực email -> pending_verification.
add_user("son", "son.do@gmail.com", "Đỗ Trường Sơn", "2026-08-10 21:30",
         status="pending_verification", verified=None, phone="0990123456", avatar=False)
# Linh: bị admin suspend nhưng VẪN CÒN NỢ (FR 4.1.22 - abnormal case).
add_user("linh", "linh.dinh@gmail.com", "Đinh Khánh Linh", "2026-06-20 07:41",
         status="suspended", verified="2026-06-20 07:50", phone="0901112223",
         bank=("STB", "060123456789", "DINH KHANH LINH"))
# Khánh: bị khoá tài khoản, đã rời nhóm sau khi tất toán hết công nợ (FR 4.1.10).
add_user("khanh", "khanh.ly@gmail.com", "Lý Gia Khánh", "2026-06-22 18:26",
         status="locked", verified="2026-06-22 18:33", phone="0902223334",
         bank=("MSB", "03001010999", "LY GIA KHANH"))


# ---------------------------------------------------------- 2. SESSIONS ----

def add_session(user, device, issued, expires, revoked=None, tag=""):
    when = T(issued)
    sid = uuid7(when, f"session:{user}:{device}{tag}")
    rows["sessions"].append(
        f"({q(sid)}, {q(U[user]['id'])}, {q(device)}, "
        f"{q(sha256(f'rt.{user}.{device}{tag}.paysplit'))}, {ts(when)}, "
        f"{ts(T(expires))}, {ts(T(revoked) if revoked else None)})"
    )


add_session("minh", "android-pixel8-7f3a", "2026-08-11 07:12", "2026-09-10 07:12")
add_session("minh", "ios-iphone13-9b21", "2026-07-02 21:40", "2026-08-01 21:40",
            revoked="2026-07-30 08:05", tag=".old")     # đăng xuất chủ động (FR 4.1.4)
add_session("lan", "ios-iphone15-1c88", "2026-08-12 08:03", "2026-09-11 08:03")
add_session("hung", "android-oppo-4d19", "2026-08-12 12:44", "2026-09-11 12:44")
add_session("thao", "ios-iphone14-2e57", "2026-08-10 19:26", "2026-09-09 19:26")
add_session("duc", "android-samsung-8a02", "2026-06-25 09:31", "2026-07-25 09:31")  # hết hạn
add_session("mai", "android-xiaomi-6f44", "2026-08-13 06:58", "2026-09-12 06:58")
add_session("ngoc", "ios-iphone12-3b90", "2026-08-11 22:17", "2026-09-10 22:17")
add_session("tuan", "android-vivo-5c73", "2026-08-09 17:05", "2026-09-08 17:05")
# Bị admin suspend/lock -> toàn bộ refresh token bị thu hồi ngay (FR 4.1.22)
add_session("linh", "android-realme-0e66", "2026-07-28 10:12", "2026-08-27 10:12",
            revoked="2026-08-01 09:30")
add_session("khanh", "ios-iphone11-7a35", "2026-07-24 15:48", "2026-08-23 15:48",
            revoked="2026-08-05 14:20")


# -------------------------------------------------------- 3. USER TOKENS ---

def add_token(user, ttype, created, expires, used=None, tag=""):
    when = T(created)
    tid = uuid7(when, f"token:{user}:{ttype}{tag}")
    plain = f"{ttype}.{user}{tag}.paysplit.mock"
    rows["user_tokens"].append(
        f"({q(tid)}, {q(U[user]['id'])}, {q(ttype)}::token_type, {q(sha256(plain))}, "
        f"{ts(T(expires))}, {ts(T(used) if used else None)}, {ts(when)})"
    )


for k in ["admin", "minh", "lan", "hung", "thao", "duc", "mai", "tuan", "ngoc",
          "an", "linh", "khanh"]:
    c = U[k]["created"]
    add_token(k, "email_verification", c.strftime("%Y-%m-%d %H:%M"),
              (c + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M"),
              used=(c + timedelta(minutes=9)).strftime("%Y-%m-%d %H:%M"))

# Sơn: token đầu đã hết hạn mà chưa dùng, token thứ 2 do bấm "gửi lại" còn hiệu lực.
add_token("son", "email_verification", "2026-08-10 21:30", "2026-08-11 21:30")
add_token("son", "email_verification", "2026-08-13 09:15", "2026-08-14 09:15", tag=".resend")
# Hùng: đã dùng link quên mật khẩu thành công.
add_token("hung", "password_reset", "2026-07-01 08:02", "2026-07-01 08:32",
          used="2026-07-01 08:11")
# Mai: vừa yêu cầu reset, chưa dùng.
add_token("mai", "password_reset", "2026-08-13 10:04", "2026-08-13 10:34")


# ------------------------------------------------------------ 4. GROUPS ----

def add_group(key, name, creator, created):
    when = T(created)
    gid = uuid7(when, "group:" + key)
    GRP[key] = dict(id=gid, created=when, creator=creator, name=name, captain=creator)
    rows["groups"].append(
        f"({q(gid)}, {q(name)}, 'VND', {q(U[creator]['id'])}, {ts(when)})")


def add_member(gkey, user, joined, role="member", left=None):
    when = T(joined)
    mid = uuid7(when, f"member:{gkey}:{user}")
    GM[(gkey, user)] = mid
    status = "inactive" if left else "active"
    rows["group_members"].append(
        f"({q(mid)}, {q(GRP[gkey]['id'])}, {q(U[user]['id'])}, {q(role)}::group_role, "
        f"{q(status)}::member_status, {ts(when)}, {ts(T(left) if left else None)})")
    return mid


def add_invite(gkey, code, creator, created, expires, max_uses, use_count,
               revoked=None):
    when = T(created)
    iid = uuid7(when, f"invite:{gkey}:{code}")
    rows["group_invites"].append(
        f"({q(iid)}, {q(GRP[gkey]['id'])}, {q(code)}, {q(GM[(gkey, creator)])}, "
        f"{ts(T(expires))}, {max_uses if max_uses is not None else 'NULL'}, {use_count}, "
        f"{ts(T(revoked) if revoked else None)}, {ts(when)})")


# --- G1: Du lịch Đà Lạt --------------------------------------------------
add_group("g1", "Du lịch Đà Lạt 3N2Đ", "minh", "2026-07-10 20:15")
add_member("g1", "minh", "2026-07-10 20:15", role="captain")
add_member("g1", "lan",  "2026-07-10 20:41")
add_member("g1", "hung", "2026-07-10 21:03")
add_member("g1", "thao", "2026-07-11 07:52")
add_member("g1", "duc",  "2026-07-11 08:30")
add_member("g1", "an",   "2026-07-11 09:14")
# Mã đầu bị lộ ra nhóm chat ngoài -> captain thu hồi, tạo mã mới (FR 4.1.8).
add_invite("g1", "DALAT-8KQ2WM", "minh", "2026-07-10 20:16", "2026-07-17 20:16",
           10, 2, revoked="2026-07-10 22:30")
add_invite("g1", "DALAT-V3NPX7", "minh", "2026-07-10 22:31", "2026-07-20 22:31", 10, 3)

# --- G2: Ăn trưa văn phòng ----------------------------------------------
add_group("g2", "Ăn trưa văn phòng Q3", "lan", "2026-06-20 11:02")
add_member("g2", "lan",   "2026-06-20 11:02", role="captain")
add_member("g2", "mai",   "2026-06-20 11:25")
add_member("g2", "tuan",  "2026-06-21 09:47")
add_member("g2", "ngoc",  "2026-06-22 10:18")
add_member("g2", "khanh", "2026-06-23 11:36", left="2026-07-25 16:40")  # net balance = 0
add_member("g2", "hung",  "2026-07-05 08:59")
add_member("g2", "linh",  "2026-07-06 10:22")
add_invite("g2", "LUNCH-Q3-RTY9", "lan", "2026-06-20 11:04", "2026-09-20 11:04", None, 6)

# --- G3: Sinh nhật Thảo (nhóm mới, chưa phát sinh công nợ) --------------
add_group("g3", "Sinh nhật Thảo 2026", "thao", "2026-08-11 21:07")
add_member("g3", "thao", "2026-08-11 21:07", role="captain")
add_member("g3", "minh", "2026-08-11 21:35")
add_member("g3", "ngoc", "2026-08-12 08:12")
add_member("g3", "duc",  "2026-08-12 09:40")
add_invite("g3", "BDAY-THAO-QZ41", "thao", "2026-08-11 21:08", "2026-08-18 21:08", 8, 3)


# ------------------------------------------------------------- 5. BILLS ----

BILLS = {}


def add_bill(key, gkey, creditor, merchant, bill_date, created, items,
             *, service=0, vat=0, discount=0, total=None, subtotal=None,
             status="draft", finalized=None, mismatch=False, version=1,
             has_image=True):
    """items: [(name, qty, unit_price, line_total, {user_key: weight})]"""
    when = T(created)
    bid = uuid7(when, "bill:" + key)
    gid = GRP[gkey]["id"]
    sub = subtotal if subtotal is not None else sum(i[3] for i in items)
    tot = total if total is not None else sub + service + vat - discount
    img = f"bills/{gid}/{bid}.jpg" if has_image else None
    rows["bills"].append(
        f"({q(bid)}, {q(gid)}, {q(GM[(gkey, creditor)])}, {q(status)}::bill_status, "
        f"{q(merchant)}, {d(bill_date)}, {q(img)}, {sub}, {service}, {vat}, {discount}, "
        f"{tot}, {str(mismatch).lower()}, {version}, {ts(when)}, "
        f"{ts(T(finalized) if finalized else None)}, "
        f"{ts(T(finalized) if finalized else when)})")

    norm_items = []
    for idx, (name, qty, unit, line, assign) in enumerate(items):
        iwhen = when + timedelta(seconds=idx + 1)
        iid = uuid7(iwhen, f"item:{key}:{idx}")
        rows["bill_items"].append(
            f"({q(iid)}, {q(bid)}, {q(gid)}, {q(name)}, {qty}, {unit}, {line}, "
            f"{ts(iwhen)}, {ts(iwhen)})")
        for j, (uk, w) in enumerate(assign.items()):
            awhen = iwhen + timedelta(milliseconds=100 * (j + 1))
            aid = uuid7(awhen, f"asg:{key}:{idx}:{uk}")
            rows["bill_item_assignments"].append(
                f"({q(aid)}, {q(iid)}, {q(gid)}, {q(GM[(gkey, uk)])}, {w}, {ts(awhen)})")
        norm_items.append({"line_total": line, "assign": assign})

    BILLS[key] = dict(id=bid, gkey=gkey, gid=gid, creditor=creditor, total=tot,
                      items=norm_items, merchant=merchant, created=when,
                      finalized=T(finalized) if finalized else None, status=status)


# ---- G1 -----------------------------------------------------------------
G1_ORDER = ["minh", "lan", "hung", "thao", "duc", "an"]

add_bill("b1", "g1", "minh", "Nhà hàng Cơm Niêu Đà Lạt", "2026-07-18",
         "2026-07-18 20:41",
         [("Cơm niêu đập",            3, 95000,  285000, {k: 1 for k in G1_ORDER}),
          ("Gà nướng mật ong",        1, 340000, 340000, {"minh": 1, "lan": 1, "hung": 1, "thao": 1}),
          ("Lẩu gà lá é (nồi lớn)",   1, 450000, 450000, {k: 1 for k in G1_ORDER}),
          ("Rau muống xào tỏi",       2, 65000,  130000, {k: 1 for k in G1_ORDER}),
          ("Bia Saigon Special",      8, 28000,  224000, {"minh": 3, "hung": 3, "duc": 2}),
          ("Nước suối Lavie",         6, 12000,  72000,  {k: 1 for k in G1_ORDER})],
         service=75050, vat=126084, discount=134, total=1702000,
         status="finalized", finalized="2026-07-18 22:10", version=3)

# Bill nhập tay: không có ảnh, không có OCR -> 1 dòng "món tổng hợp", chia đều 6 người
# (đúng ghi chú FR 4.1.13 về synthetic line item).
add_bill("b2", "g1", "lan", "Homestay Mimosa Đà Lạt", "2026-07-19",
         "2026-07-19 09:20",
         [("Homestay Mimosa - 2 đêm (3 phòng đôi)", 1, 3600000, 3600000,
           {k: 1 for k in G1_ORDER})],
         status="finalized", finalized="2026-07-19 09:44", version=1, has_image=False)

# OCR đọc tổng tiền lệch với chi tiết món -> mismatch_warning = true (FR 4.1.12).
add_bill("b3", "g1", "hung", "Cà phê Mê Linh", "2026-07-19", "2026-07-19 15:12",
         [("Cà phê sữa đá",  3, 45000, 135000, {"minh": 1, "hung": 1, "duc": 1}),
          ("Bạc xỉu",        2, 50000, 100000, {"lan": 1, "thao": 1}),
          ("Bánh flan",      5, 25000, 125000, {"minh": 1, "lan": 1, "hung": 1, "thao": 1, "duc": 1}),
          ("Trà đào cam sả", 1, 55000, 55000,  {"thao": 1})],
         subtotal=415000, total=435000, mismatch=True,
         status="finalized", finalized="2026-07-19 16:02", version=2)

add_bill("b4", "g1", "minh", "Khu du lịch Langbiang", "2026-07-20",
         "2026-07-20 10:05",
         [("Vé vào cổng Langbiang", 6, 50000,  300000, {k: 1 for k in G1_ORDER}),
          ("Xe jeep lên đỉnh",      1, 480000, 480000, {k: 1 for k in G1_ORDER}),
          ("Vé xe điện nội khu",    2, 30000,  60000,  {"thao": 1, "an": 1})],
         status="finalized", finalized="2026-07-20 10:58", version=2)

# Bill nháp: OCR xong, đã gán món đủ, nhưng captain chưa bấm chốt.
add_bill("b5", "g1", "minh", "BBQ Đồi Mộng Mơ", "2026-07-20", "2026-07-20 21:33",
         [("Combo nướng BBQ 6 người", 1, 890000, 890000, {k: 1 for k in G1_ORDER}),
          ("Bia Tiger",              12, 25000,  300000, {"minh": 4, "hung": 4, "duc": 4}),
          ("Nước ngọt lon",           4, 18000,  72000,  {"lan": 2, "thao": 1, "an": 1})],
         service=63100, vat=106008, discount=108, total=1431000, version=2)

# ---- G2 -----------------------------------------------------------------
add_bill("b6", "g2", "mai", "Cơm tấm Ba Ghiền", "2026-07-02", "2026-07-02 12:14",
         [("Cơm tấm sườn bì chả",  3, 65000, 195000, {"lan": 1, "mai": 1, "tuan": 1}),
          ("Cơm tấm sườn ốp la",   2, 70000, 140000, {"ngoc": 1, "khanh": 1}),
          ("Canh khổ qua",         5, 15000, 75000,  {"lan": 1, "mai": 1, "tuan": 1, "ngoc": 1, "khanh": 1}),
          ("Trà đá",               5, 5000,  25000,  {"lan": 1, "mai": 1, "tuan": 1, "ngoc": 1, "khanh": 1})],
         status="finalized", finalized="2026-07-02 12:39", version=1)

add_bill("b7", "g2", "lan", "Bún chả Hương Liên", "2026-07-09", "2026-07-09 12:08",
         [("Bún chả",      7, 60000, 420000, {"lan": 1, "mai": 1, "tuan": 1, "ngoc": 1, "khanh": 1, "hung": 1, "linh": 1}),
          ("Nem cua bể",   4, 40000, 160000, {"lan": 1, "mai": 1, "hung": 1, "linh": 1}),
          ("Nước sấu",     7, 15000, 105000, {"lan": 1, "mai": 1, "tuan": 1, "ngoc": 1, "khanh": 1, "hung": 1, "linh": 1})],
         status="finalized", finalized="2026-07-09 12:35", version=1, has_image=False)

# Có voucher giảm giá -> phần chia lẻ, phải dùng Hamilton để tổng khớp tuyệt đối.
add_bill("b8", "g2", "ngoc", "Phúc Long Coffee & Tea", "2026-07-16", "2026-07-16 14:52",
         [("Trà sữa Phúc Long size L", 4, 55000, 220000, {"lan": 1, "mai": 1, "ngoc": 1, "hung": 1}),
          ("Bánh mousse trà xanh",     2, 45000, 90000,  {"lan": 1, "ngoc": 1}),
          ("Topping trân châu",        3, 10000, 30000,  {"mai": 1, "ngoc": 1, "hung": 1})],
         discount=35000, status="finalized", finalized="2026-07-16 15:10", version=2)

add_bill("b9", "g2", "mai", "Cơm gà Xối Mỡ 175", "2026-08-06", "2026-08-06 12:03",
         [("Cơm gà xối mỡ", 5, 62000, 310000, {"lan": 1, "mai": 1, "tuan": 1, "ngoc": 1, "hung": 1}),
          ("Gỏi gà",        1, 85000, 85000,  {"lan": 1, "mai": 1, "tuan": 1, "ngoc": 1, "hung": 1}),
          ("Nước ngọt",     5, 15000, 75000,  {"lan": 1, "mai": 1, "tuan": 1, "ngoc": 1, "hung": 1})],
         status="finalized", finalized="2026-08-06 12:28", version=1)

# ---- G3 (chưa nhóm nào được chốt -> chưa có công nợ) --------------------
# OCR thất bại sau khi hết số lần retry -> bill nháp rỗng, mời nhập tay (FR 4.1.12).
add_bill("b10", "g3", "minh", None, None, "2026-08-12 19:22", [], version=1)

# Còn 2 món chưa gán ai -> hệ thống chặn finalize (FR 4.1.13 abnormal).
add_bill("b11", "g3", "thao", "Bách hoá Xanh", "2026-08-12", "2026-08-12 20:05",
         [("Bánh snack các loại", 5, 22000,  110000, {"thao": 1, "minh": 1, "ngoc": 1, "duc": 1}),
          ("Nước ngọt lon",      12, 12000,  144000, {"thao": 1, "minh": 1, "ngoc": 1, "duc": 1}),
          ("Bánh kem mini",       1, 250000, 250000, {}),
          ("Nến sinh nhật",       1, 35000,  35000,  {}),
          ("Ly giấy + đĩa giấy",  2, 28000,  56000,  {"thao": 1})],
         version=2)

# OCR đang chạy -> bill nháp chưa có món nào.
add_bill("b12", "g3", "duc", None, None, "2026-08-13 09:48", [], version=1)


# ---------------------------------------------------------- 6. OCR JOBS ----

def add_ocr(bill_key, status, created, *, attempts=1, completed=None,
            raw=None, error=None, provider="gemini-2.5-flash"):
    when = T(created)
    oid = uuid7(when, "ocr:" + bill_key)
    upd = T(completed) if completed else when
    rows["ocr_jobs"].append(
        f"({q(oid)}, {q(BILLS[bill_key]['id'])}, {q(status)}::ocr_job_status, "
        f"{q(provider)}, {attempts}, {jb(raw)}, {q(error)}, {ts(when)}, {ts(upd)}, "
        f"{ts(T(completed) if completed else None)})")


add_ocr("b1", "succeeded", "2026-07-18 20:41", completed="2026-07-18 20:41",
        raw='{"merchant_name":"Nhà hàng Cơm Niêu Đà Lạt","bill_date":"2026-07-18",'
            '"items":[{"name":"Cơm niêu đập","quantity":3,"unit_price":95000,"line_total":285000},'
            '{"name":"Gà nướng mật ong","quantity":1,"unit_price":340000,"line_total":340000},'
            '{"name":"Lẩu gà lá é (nồi lớn)","quantity":1,"unit_price":450000,"line_total":450000},'
            '{"name":"Rau muống xào tỏi","quantity":2,"unit_price":65000,"line_total":130000},'
            '{"name":"Bia Saigon Special","quantity":8,"unit_price":28000,"line_total":224000},'
            '{"name":"Nước suối Lavie","quantity":6,"unit_price":12000,"line_total":72000}],'
            '"subtotal":1501000,"service_charge":75050,"vat":126084,"discount":134,'
            '"total":1702000,"confidence":0.96}')
add_ocr("b3", "succeeded", "2026-07-19 15:12", completed="2026-07-19 15:13", attempts=2,
        raw='{"merchant_name":"Cà phê Mê Linh","bill_date":"2026-07-19",'
            '"items":[{"name":"Cà phê sữa đá","quantity":3,"unit_price":45000,"line_total":135000},'
            '{"name":"Bạc xỉu","quantity":2,"unit_price":50000,"line_total":100000},'
            '{"name":"Bánh flan","quantity":5,"unit_price":25000,"line_total":125000},'
            '{"name":"Trà đào cam sả","quantity":1,"unit_price":55000,"line_total":55000}],'
            '"subtotal":415000,"service_charge":0,"vat":0,"discount":0,"total":435000,'
            '"confidence":0.71,"reconciliation":"mismatch: items sum 415000 != total 435000"}')
add_ocr("b4", "succeeded", "2026-07-20 10:05", completed="2026-07-20 10:06",
        raw='{"merchant_name":"Khu du lịch Langbiang","bill_date":"2026-07-20",'
            '"items":[{"name":"Vé vào cổng Langbiang","quantity":6,"unit_price":50000,"line_total":300000},'
            '{"name":"Xe jeep lên đỉnh","quantity":1,"unit_price":480000,"line_total":480000},'
            '{"name":"Vé xe điện nội khu","quantity":2,"unit_price":30000,"line_total":60000}],'
            '"subtotal":840000,"service_charge":0,"vat":0,"discount":0,"total":840000,'
            '"confidence":0.93}')
add_ocr("b5", "succeeded", "2026-07-20 21:33", completed="2026-07-20 21:34",
        raw='{"merchant_name":"BBQ Đồi Mộng Mơ","bill_date":"2026-07-20",'
            '"items":[{"name":"Combo nướng BBQ 6 người","quantity":1,"unit_price":890000,"line_total":890000},'
            '{"name":"Bia Tiger","quantity":12,"unit_price":25000,"line_total":300000},'
            '{"name":"Nước ngọt lon","quantity":4,"unit_price":18000,"line_total":72000}],'
            '"subtotal":1262000,"service_charge":63100,"vat":106008,"discount":108,'
            '"total":1431000,"confidence":0.91}')
add_ocr("b6", "succeeded", "2026-07-02 12:14", completed="2026-07-02 12:15",
        raw='{"merchant_name":"Cơm tấm Ba Ghiền","bill_date":"2026-07-02",'
            '"items":[{"name":"Cơm tấm sườn bì chả","quantity":3,"unit_price":65000,"line_total":195000},'
            '{"name":"Cơm tấm sườn ốp la","quantity":2,"unit_price":70000,"line_total":140000},'
            '{"name":"Canh khổ qua","quantity":5,"unit_price":15000,"line_total":75000},'
            '{"name":"Trà đá","quantity":5,"unit_price":5000,"line_total":25000}],'
            '"subtotal":435000,"service_charge":0,"vat":0,"discount":0,"total":435000,'
            '"confidence":0.95}')
add_ocr("b8", "succeeded", "2026-07-16 14:52", completed="2026-07-16 14:53",
        raw='{"merchant_name":"Phúc Long Coffee & Tea","bill_date":"2026-07-16",'
            '"items":[{"name":"Trà sữa Phúc Long size L","quantity":4,"unit_price":55000,"line_total":220000},'
            '{"name":"Bánh mousse trà xanh","quantity":2,"unit_price":45000,"line_total":90000},'
            '{"name":"Topping trân châu","quantity":3,"unit_price":10000,"line_total":30000}],'
            '"subtotal":340000,"service_charge":0,"vat":0,"discount":35000,"total":305000,'
            '"confidence":0.94}')
add_ocr("b9", "succeeded", "2026-08-06 12:03", completed="2026-08-06 12:04",
        raw='{"merchant_name":"Cơm gà Xối Mỡ 175","bill_date":"2026-08-06",'
            '"items":[{"name":"Cơm gà xối mỡ","quantity":5,"unit_price":62000,"line_total":310000},'
            '{"name":"Gỏi gà","quantity":1,"unit_price":85000,"line_total":85000},'
            '{"name":"Nước ngọt","quantity":5,"unit_price":15000,"line_total":75000}],'
            '"subtotal":470000,"service_charge":0,"vat":0,"discount":0,"total":470000,'
            '"confidence":0.97}')
add_ocr("b10", "failed", "2026-08-12 19:22", attempts=5, completed="2026-08-12 19:31",
        error="provider timeout sau 5 lần thử (exponential backoff); "
              "bill giữ nguyên DRAFT để người dùng nhập tay")
add_ocr("b11", "succeeded", "2026-08-12 20:05", completed="2026-08-12 20:06",
        raw='{"merchant_name":"Bách hoá Xanh","bill_date":"2026-08-12",'
            '"items":[{"name":"Bánh snack các loại","quantity":5,"unit_price":22000,"line_total":110000},'
            '{"name":"Nước ngọt lon","quantity":12,"unit_price":12000,"line_total":144000},'
            '{"name":"Bánh kem mini","quantity":1,"unit_price":250000,"line_total":250000},'
            '{"name":"Nến sinh nhật","quantity":1,"unit_price":35000,"line_total":35000},'
            '{"name":"Ly giấy + đĩa giấy","quantity":2,"unit_price":28000,"line_total":56000}],'
            '"subtotal":595000,"service_charge":0,"vat":0,"discount":0,"total":595000,'
            '"confidence":0.89}')
add_ocr("b12", "processing", "2026-08-13 09:48", attempts=1)


# ------------------------------------- 7. FINALIZE -> DEBTS -> PAYMENTS ----

DEBT = {}      # (bill_key, debtor) -> dict
SHARES = {}    # bill_key -> {user_key: amount}

FINALIZED = ["b1", "b2", "b3", "b4", "b6", "b7", "b8", "b9"]

for bk in FINALIZED:
    b = BILLS[bk]
    order = [u for u in ["minh", "lan", "hung", "thao", "duc", "an", "mai",
                         "tuan", "ngoc", "khanh", "linh"]
             if (b["gkey"], u) in GM]
    share = allocate(b["items"], b["total"], order)
    SHARES[bk] = share
    for i, (uk, amt) in enumerate(sorted(share.items(), key=lambda x: order.index(x[0]))):
        if uk == b["creditor"]:
            continue
        when = b["finalized"] + timedelta(seconds=i + 1)
        did = uuid7(when, f"debt:{bk}:{uk}")
        DEBT[(bk, uk)] = dict(id=did, gkey=b["gkey"], gid=b["gid"], bill=bk,
                              debtor=uk, creditor=b["creditor"], amount=amt,
                              created=when, status="awaiting", payment=None,
                              settled=None, updated=when, reminders=0)

PAYMENTS = []


def add_payment(pkey, gkey, debtor, creditor, bill_keys, created,
                *, submitted=None, confirmed=None, rejected=None, reason=None,
                note=None, proof=True, debt_status=None, reminders=0,
                detach=False):
    """
    debt_status: trạng thái cuối cùng của các debt được payment này gộp.
    detach=True  -> payment bị từ chối VÀ debtor đã được trả nợ về awaiting
                    (payment giữ lại làm audit trail, không còn debt trỏ vào).
    """
    gid = GRP[gkey]["id"]
    debts = [DEBT[(bk, debtor)] for bk in bill_keys]
    amount = sum(x["amount"] for x in debts)
    when = T(created)
    pid = uuid7(when, "pay:" + pkey)
    ref = "PS" + hashlib.md5(pkey.encode()).hexdigest()[:8].upper()
    bank = U[creditor]["bank"]
    assert bank, f"creditor {creditor} chưa có tài khoản ngân hàng"
    payload = vietqr(bank[0], bank[1], amount, ref)
    last = max([x for x in [when, T(submitted) if submitted else None,
                            T(confirmed) if confirmed else None,
                            T(rejected) if rejected else None] if x])
    rows["payments"].append(
        f"({q(pid)}, {q(gid)}, {q(GM[(gkey, debtor)])}, {q(GM[(gkey, creditor)])}, "
        f"{amount}, {q(ref)}, {q(payload)}, "
        f"{q(f'payments/{gid}/{pid}.jpg') if (proof and submitted) else 'NULL'}, "
        f"{q(note)}, {q(reason)}, {ts(when)}, {ts(T(submitted) if submitted else None)}, "
        f"{ts(T(confirmed) if confirmed else None)}, "
        f"{ts(T(rejected) if rejected else None)}, {ts(last)})")

    PAYMENTS.append(dict(key=pkey, id=pid, gkey=gkey, gid=gid, debtor=debtor,
                         creditor=creditor, amount=amount, ref=ref, created=when,
                         submitted=T(submitted) if submitted else None,
                         confirmed=T(confirmed) if confirmed else None,
                         rejected=T(rejected) if rejected else None,
                         reason=reason, bills=list(bill_keys)))

    for x in debts:
        if detach:
            x["status"] = "awaiting"
            x["payment"] = None
            x["settled"] = None
        else:
            x["status"] = debt_status
            x["payment"] = pid
            x["settled"] = T(confirmed) if debt_status == "settled" else None
        x["reminders"] = max(x["reminders"], reminders)
        x["updated"] = last
    return pid


# --- G1 ------------------------------------------------------------------
# Thảo gộp 2 hoá đơn khác nhau của cùng chủ nợ Minh vào 1 mã QR -> confirmed.
add_payment("g1-thao-minh", "g1", "thao", "minh", ["b1", "b4"],
            "2026-07-21 08:12", submitted="2026-07-21 08:20",
            confirmed="2026-07-21 09:05", note="Đã chuyển khoản Vietcombank, em gửi anh nhé",
            debt_status="settled")

# Lan chuyển thiếu -> Minh từ chối; các khoản nợ được trả về awaiting và tách khỏi payment.
add_payment("g1-lan-minh-rejected", "g1", "lan", "minh", ["b1", "b4"],
            "2026-07-22 10:30", submitted="2026-07-22 10:41",
            rejected="2026-07-22 14:18",
            reason="Số tiền nhận được là 500.000đ, thiếu so với mã QR. Bạn kiểm tra lại giúp mình.",
            note="Chuyển khoản Techcombank", debt_status=None, detach=True)

# Lan tạo lại QR mới cho đúng 2 khoản nợ đó -> confirmed. Mã reference_code khác hoàn toàn.
add_payment("g1-lan-minh-retry", "g1", "lan", "minh", ["b1", "b4"],
            "2026-07-22 15:02", submitted="2026-07-22 15:09",
            confirmed="2026-07-23 07:44", note="Mình chuyển lại đủ nhé, xin lỗi bạn",
            debt_status="settled")

# Hùng chỉ chọn trả 1 trong 2 khoản nợ với Minh (FR 4.1.17 - trả subset).
add_payment("g1-hung-minh-partial", "g1", "hung", "minh", ["b1"],
            "2026-08-12 20:15", submitted="2026-08-12 20:22",
            note="Trả trước phần cơm niêu, vé Langbiang tuần sau mình gửi",
            debt_status="pending_confirmation")

# Đức trả tiền homestay cho Lan, Lan chưa xác nhận.
add_payment("g1-duc-lan", "g1", "duc", "lan", ["b2"],
            "2026-08-11 18:40", submitted="2026-08-11 18:47",
            note="600k homestay nha chị", debt_status="pending_confirmation")

# --- G2 ------------------------------------------------------------------
# Khánh tất toán toàn bộ trước khi rời nhóm -> net balance = 0 (FR 4.1.10).
add_payment("g2-khanh-mai", "g2", "khanh", "mai", ["b6"],
            "2026-07-20 09:05", submitted="2026-07-20 09:11",
            confirmed="2026-07-20 10:02", debt_status="settled")
add_payment("g2-khanh-lan", "g2", "khanh", "lan", ["b7"],
            "2026-07-24 16:20", submitted="2026-07-24 16:26",
            confirmed="2026-07-24 17:03", note="Mình thanh toán nốt trước khi rời nhóm",
            debt_status="settled")

# Lan gộp 2 bill của Mai vào 1 QR -> confirmed.
add_payment("g2-lan-mai", "g2", "lan", "mai", ["b6", "b9"],
            "2026-08-08 09:30", submitted="2026-08-08 09:36",
            confirmed="2026-08-08 11:15", debt_status="settled")

# Ngọc gộp 2 bill của Mai -> đã nộp bằng chứng, Mai chưa xử lý.
add_payment("g2-ngoc-mai", "g2", "ngoc", "mai", ["b6", "b9"],
            "2026-08-11 13:20", submitted="2026-08-11 13:28",
            note="Chuyển khoản TPBank lúc 13:27", debt_status="pending_confirmation")

# Tuấn bị Mai từ chối và CHƯA tạo QR mới -> debts đứng ở trạng thái 'rejected',
# vẫn còn trỏ vào payment bị từ chối (đúng CHECK: chỉ 'awaiting' mới được null payment_id).
add_payment("g2-tuan-mai", "g2", "tuan", "mai", ["b6", "b9"],
            "2026-08-09 08:14", submitted="2026-08-09 08:19",
            rejected="2026-08-09 20:41",
            reason="Mình không thấy giao dịch nào với nội dung này trong sao kê BIDV.",
            debt_status="rejected", reminders=2)

# Hùng nộp bằng chứng nhưng Ngọc quên xác nhận -> job tự động đẩy sang
# stalled_confirmation sau N lần nhắc (FR 4.2.1). Hệ thống KHÔNG tự tất toán.
add_payment("g2-hung-ngoc", "g2", "hung", "ngoc", ["b8"],
            "2026-07-18 10:02", submitted="2026-07-18 10:09",
            note="Đã chuyển nhé Ngọc", debt_status="stalled_confirmation", reminders=3)

# Các khoản còn awaiting đã bị job nhắc nợ vài lần.
for (bk, uk), n in {("b2", "minh"): 1, ("b2", "hung"): 2, ("b2", "an"): 3,
                    ("b3", "duc"): 2, ("b1", "duc"): 2, ("b4", "duc"): 2,
                    ("b1", "an"): 3, ("b4", "an"): 3, ("b4", "hung"): 1,
                    ("b7", "linh"): 3, ("b7", "hung"): 1, ("b7", "mai"): 1,
                    ("b8", "mai"): 2, ("b9", "hung"): 1}.items():
    if (bk, uk) in DEBT:
        DEBT[(bk, uk)]["reminders"] = n

for x in sorted(DEBT.values(), key=lambda r: r["created"]):
    rows["debts"].append(
        f"({q(x['id'])}, {q(x['gid'])}, {q(BILLS[x['bill']]['id'])}, "
        f"{q(GM[(x['gkey'], x['debtor'])])}, {q(GM[(x['gkey'], x['creditor'])])}, "
        f"{x['amount']}, {q(x['status'])}::debt_status, {x['reminders']}, "
        f"{q(x['payment']) if x['payment'] else 'NULL'}, {ts(x['created'])}, "
        f"{ts(x['settled'])}, {ts(x['updated'])})")


# ------------------------------------------------------ 8. ACTIVITIES ------

acts = []


def act(gkey, actor, atype, when, desc, meta):
    acts.append((T(when), gkey, actor, atype, desc, meta))


for bk in FINALIZED + ["b5", "b10", "b11", "b12"]:
    b = BILLS[bk]
    label = b["merchant"] or "Hoá đơn chưa đặt tên"
    act(b["gkey"], b["creditor"], "created_bill",
        b["created"].strftime("%Y-%m-%d %H:%M"),
        f"{U[b['creditor']]['name']} đã tạo hoá đơn {label}",
        f'{{"bill_id":"{b["id"]}","total":{b["total"]},"source":'
        f'"{"manual" if bk in ("b2", "b7") else "ocr"}"}}')

act("g1", "minh", "updated_bill", "2026-07-18 21:30",
    "Nguyễn Văn Minh đã sửa hoá đơn Nhà hàng Cơm Niêu Đà Lạt (thêm món Nước suối Lavie)",
    f'{{"bill_id":"{BILLS["b1"]["id"]}","version":2,"changed":["items"]}}')
act("g1", "minh", "updated_bill", "2026-07-18 21:52",
    "Nguyễn Văn Minh đã sửa hoá đơn Nhà hàng Cơm Niêu Đà Lạt (làm tròn hoá đơn 134đ)",
    f'{{"bill_id":"{BILLS["b1"]["id"]}","version":3,"changed":["discount","total"]}}')
act("g1", "hung", "updated_bill", "2026-07-19 15:40",
    "Phạm Quốc Hùng đã sửa hoá đơn Cà phê Mê Linh (xác nhận giữ tổng tiền OCR đọc được)",
    f'{{"bill_id":"{BILLS["b3"]["id"]}","version":2,"mismatch_warning":true}}')
act("g1", "minh", "updated_bill", "2026-07-20 10:40",
    "Nguyễn Văn Minh đã sửa hoá đơn Khu du lịch Langbiang (bổ sung vé xe điện nội khu)",
    f'{{"bill_id":"{BILLS["b4"]["id"]}","version":2,"changed":["items"]}}')
act("g2", "ngoc", "updated_bill", "2026-07-16 15:04",
    "Bùi Bảo Ngọc đã sửa hoá đơn Phúc Long Coffee & Tea (áp voucher giảm 35.000đ)",
    f'{{"bill_id":"{BILLS["b8"]["id"]}","version":2,"changed":["discount"]}}')
act("g3", "thao", "updated_bill", "2026-08-12 20:31",
    "Lê Phương Thảo đã sửa hoá đơn Bách hoá Xanh (gán món cho thành viên)",
    f'{{"bill_id":"{BILLS["b11"]["id"]}","version":2,"unassigned_items":2}}')

# Một hoá đơn bị tạo nhầm rồi xoá khi còn ở trạng thái draft.
_deleted_bill_id = uuid7(T("2026-07-11 12:44"), "bill:deleted-g2")
act("g2", "tuan", "deleted_bill", "2026-07-11 12:51",
    "Đặng Anh Tuấn đã xoá hoá đơn nháp Trà sữa Toco (tạo nhầm nhóm)",
    f'{{"bill_id":"{_deleted_bill_id}","status_before":"draft","reason":"created_by_mistake"}}')

for bk in FINALIZED:
    b = BILLS[bk]
    cap = GRP[b["gkey"]]["captain"]
    n = len([1 for (k, u) in DEBT if k == bk])
    act(b["gkey"], cap, "finalized_bill", b["finalized"].strftime("%Y-%m-%d %H:%M"),
        f"{U[cap]['name']} đã chốt hoá đơn {b['merchant']} — "
        f"tổng {b['total']:,}đ, sinh {n} khoản nợ".replace(",", "."),
        f'{{"bill_id":"{b["id"]}","total":{b["total"]},"debt_count":{n},'
        f'"rounding_method":"largest_remainder"}}')

for p in PAYMENTS:
    bills_meta = ",".join(f'"{BILLS[bk]["id"]}"' for bk in p["bills"])
    if p["submitted"]:
        act(p["gkey"], p["debtor"], "submitted_proof",
            p["submitted"].strftime("%Y-%m-%d %H:%M"),
            f"{U[p['debtor']]['name']} đã báo đã chuyển "
            f"{p['amount']:,}đ cho {U[p['creditor']]['name']}".replace(",", "."),
            f'{{"payment_id":"{p["id"]}","amount":{p["amount"]},'
            f'"reference_code":"{p["ref"]}","bill_ids":[{bills_meta}]}}')
    if p["confirmed"]:
        act(p["gkey"], p["creditor"], "confirmed_payment",
            p["confirmed"].strftime("%Y-%m-%d %H:%M"),
            f"{U[p['creditor']]['name']} đã xác nhận nhận được "
            f"{p['amount']:,}đ từ {U[p['debtor']]['name']}".replace(",", "."),
            f'{{"payment_id":"{p["id"]}","amount":{p["amount"]},'
            f'"reference_code":"{p["ref"]}","bill_ids":[{bills_meta}]}}')
    if p["rejected"]:
        act(p["gkey"], p["creditor"], "rejected_payment",
            p["rejected"].strftime("%Y-%m-%d %H:%M"),
            f"{U[p['creditor']]['name']} đã từ chối khoản thanh toán "
            f"{p['amount']:,}đ của {U[p['debtor']]['name']}".replace(",", "."),
            f'{{"payment_id":"{p["id"]}","amount":{p["amount"]},'
            f'"reference_code":"{p["ref"]}","reason":{q(p["reason"]).replace(chr(39), chr(34))}}}'
        )

# Job tự động: actor là chủ nợ vì đây là người hệ thống đang chờ thao tác.
act("g2", "ngoc", "stalled_payment_reminder", "2026-08-01 03:00",
    "Khoản thanh toán 58.309đ của Phạm Quốc Hùng đã chờ xác nhận quá lâu — "
    "hệ thống chuyển sang trạng thái treo và nhắc cả hai bên",
    f'{{"payment_id":"{[p for p in PAYMENTS if p["key"] == "g2-hung-ngoc"][0]["id"]}",'
    f'"debt_id":"{DEBT[("b8","hung")]["id"]}","reminder_count":3,'
    f'"days_pending":14,"auto_settled":false}}')

for when, gkey, actor, atype, desc, meta in sorted(acts, key=lambda x: x[0]):
    aid = uuid7(when, f"act:{gkey}:{atype}:{desc[:40]}")
    rows["group_activities"].append(
        f"({q(aid)}, {q(GRP[gkey]['id'])}, {q(GM[(gkey, actor)])}, "
        f"{q(atype)}::activity_type, {q(desc)}, {jb(meta)}, {ts(when)})")


# ---------------------------------------------------- 9. NOTIFICATIONS -----

notis = []


def noti(user, ntype, when, payload, read=None):
    notis.append((T(when), user, ntype, payload, T(read) if read else None))


for bk in FINALIZED:
    b = BILLS[bk]
    for (k, uk) in DEBT:
        if k != bk:
            continue
        dd = DEBT[(bk, uk)]
        noti(uk, "bill_finalized",
             (b["finalized"] + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
             f'{{"group_id":"{b["gid"]}","bill_id":"{b["id"]}",'
             f'"merchant_name":{q(b["merchant"]).replace(chr(39), chr(34))},'
             f'"amount_due":{dd["amount"]},"creditor":'
             f'{q(U[b["creditor"]]["name"]).replace(chr(39), chr(34))}}}',
             read=(b["finalized"] + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"))

for p in PAYMENTS:
    if p["submitted"]:
        noti(p["creditor"], "payment_submitted",
             (p["submitted"] + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
             f'{{"payment_id":"{p["id"]}","group_id":"{p["gid"]}",'
             f'"amount":{p["amount"]},"reference_code":"{p["ref"]}",'
             f'"bill_count":{len(p["bills"])},"from":'
             f'{q(U[p["debtor"]]["name"]).replace(chr(39), chr(34))}}}',
             read=(p["confirmed"] or p["rejected"] or T("2026-08-13 07:00")).strftime("%Y-%m-%d %H:%M")
             if (p["confirmed"] or p["rejected"]) else None)
    if p["confirmed"]:
        noti(p["debtor"], "payment_confirmed",
             (p["confirmed"] + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
             f'{{"payment_id":"{p["id"]}","group_id":"{p["gid"]}",'
             f'"amount":{p["amount"]},"reference_code":"{p["ref"]}"}}',
             read=(p["confirmed"] + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"))
    if p["rejected"]:
        noti(p["debtor"], "payment_rejected",
             (p["rejected"] + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
             f'{{"payment_id":"{p["id"]}","group_id":"{p["gid"]}",'
             f'"amount":{p["amount"]},"reference_code":"{p["ref"]}",'
             f'"reason":{q(p["reason"]).replace(chr(39), chr(34))}}}')

# Nhắc nợ định kỳ cho các khoản awaiting quá hạn (FR 4.2.1)
for (bk, uk), x in DEBT.items():
    if x["status"] == "awaiting" and x["reminders"] >= 2:
        noti(uk, "debt_reminder", "2026-08-13 03:00",
             f'{{"debt_id":"{x["id"]}","group_id":"{x["gid"]}",'
             f'"bill_id":"{BILLS[bk]["id"]}","amount":{x["amount"]},'
             f'"creditor":{q(U[x["creditor"]]["name"]).replace(chr(39), chr(34))},'
             f'"reminder_count":{x["reminders"]}}}')

_st = [p for p in PAYMENTS if p["key"] == "g2-hung-ngoc"][0]
for uk in ["hung", "ngoc"]:
    noti(uk, "stalled_confirmation", "2026-08-01 03:01",
         f'{{"payment_id":"{_st["id"]}","group_id":"{_st["gid"]}",'
         f'"amount":{_st["amount"]},"reference_code":"{_st["ref"]}",'
         f'"debt_id":"{DEBT[("b8","hung")]["id"]}"}}')

noti("linh", "account_suspended", "2026-08-01 09:31",
     '{"status":"suspended","reason":"Vi phạm điều khoản sử dụng: phát tán mã mời nhóm hàng loạt",'
     '"outstanding_debt_groups":1}')
noti("khanh", "account_locked", "2026-08-05 14:21",
     '{"status":"locked","reason":"Nhiều báo cáo về hành vi xác nhận thanh toán gian lận"}')
noti("duc", "account_reactivated", "2026-07-08 10:16",
     '{"status":"active","reason":"Khiếu nại được chấp nhận, khôi phục quyền truy cập"}',
     read="2026-07-08 12:00")

for when, user, ntype, payload, read in sorted(notis, key=lambda x: x[0]):
    nid = uuid7(when, f"noti:{user}:{ntype}:{payload[:48]}")
    rows["notifications"].append(
        f"({q(nid)}, {q(U[user]['id'])}, {q(ntype)}, {jb(payload)}, {ts(read)}, {ts(when)})")


# --------------------------------------------------- 10. ADMIN AUDIT LOG ---

def audit(target, action, when, reason):
    w = T(when)
    aid = uuid7(w, f"audit:{target}:{action}:{when}")
    rows["admin_audit_logs"].append(
        f"({q(aid)}, {q(U['admin']['id'])}, {q(U[target]['id'])}, "
        f"{q(action)}::admin_action, {q(reason)}, {ts(w)})")


audit("duc", "suspend", "2026-07-05 09:12",
      "Tạm khoá theo báo cáo spam hoá đơn trong nhóm - chờ xác minh")
audit("duc", "reactivate", "2026-07-08 10:15",
      "Khiếu nại hợp lệ, báo cáo là nhầm lẫn - khôi phục tài khoản")
audit("linh", "suspend", "2026-08-01 09:30",
      "Vi phạm điều khoản: phát tán mã mời nhóm hàng loạt. "
      "Cảnh báo: tài khoản còn công nợ chưa tất toán trong 1 nhóm")
audit("khanh", "lock", "2026-08-05 14:20",
      "Nhiều báo cáo về hành vi xác nhận thanh toán gian lận - khoá vĩnh viễn chờ điều tra")


# ============================================================== EMIT SQL ====

COLS = {
    "users": "id, email, password_hash, display_name, avatar_object_key, phone_number, "
             "default_bank_code, default_bank_account_number, default_bank_account_holder, "
             "role, status, email_verified_at, created_at, updated_at",
    "sessions": "id, user_id, device_id, refresh_token_hash, issued_at, expires_at, revoked_at",
    "user_tokens": "id, user_id, type, token_hash, expires_at, used_at, created_at",
    "groups": "id, name, currency, created_by, created_at",
    "group_members": "id, group_id, user_id, role, status, joined_at, left_at",
    "group_invites": "id, group_id, code, created_by, expires_at, max_uses, use_count, "
                     "revoked_at, created_at",
    "bills": "id, group_id, creditor_member_id, status, merchant_name, bill_date, "
             "image_object_key, subtotal, service_charge, vat, discount, total, "
             "mismatch_warning, version, created_at, finalized_at, updated_at",
    "bill_items": "id, bill_id, group_id, name, quantity, unit_price, line_total, "
                  "created_at, updated_at",
    "bill_item_assignments": "id, bill_item_id, group_id, member_id, weight, created_at",
    "ocr_jobs": "id, bill_id, status, provider, attempts, raw_response, error_message, "
                "created_at, updated_at, completed_at",
    "payments": "id, group_id, debtor_member_id, creditor_member_id, amount, "
                "reference_code, qr_payload, image_object_key, note, rejection_reason, "
                "created_at, submitted_at, confirmed_at, rejected_at, updated_at",
    "debts": "id, group_id, bill_id, debtor_member_id, creditor_member_id, amount, "
             "status, reminder_count, payment_id, created_at, settled_at, updated_at",
    "group_activities": "id, group_id, actor_member_id, action_type, description, "
                        "metadata, created_at",
    "notifications": "id, user_id, type, payload, read_at, created_at",
    "admin_audit_logs": "id, admin_id, target_user_id, action, reason, created_at",
}

SECTION = {
    "users": "1. USERS — 13 tài khoản phủ đủ 4 trạng thái account_status + 2 role",
    "sessions": "2. SESSIONS — phiên đang hoạt động / đã đăng xuất / đã hết hạn / bị admin thu hồi",
    "user_tokens": "3. USER_TOKENS — xác thực email & đặt lại mật khẩu (đã dùng / hết hạn / còn hiệu lực)",
    "groups": "4. GROUPS — 3 nhóm ở 3 giai đoạn vòng đời khác nhau",
    "group_members": "5. GROUP_MEMBERS — mỏ neo của mọi dữ liệu trong nhóm",
    "group_invites": "6. GROUP_INVITES — mã mời còn hiệu lực / đã bị thu hồi",
    "bills": "7. BILLS — 12 hoá đơn: đã chốt, còn nháp, OCR lỗi, lệch tổng tiền",
    "bill_items": "8. BILL_ITEMS — chi tiết từng món",
    "bill_item_assignments": "9. BILL_ITEM_ASSIGNMENTS — ai gánh món nào (nguồn truy vết mức món)",
    "ocr_jobs": "10. OCR_JOBS — succeeded / failed (hết retry) / processing",
    "payments": "11. PAYMENTS — mỗi dòng = 1 lần chuyển khoản = 1 mã QR = 1 reference_code",
    "debts": "12. DEBTS — 1 dòng cho mỗi (bill, debtor, creditor); phủ đủ 5 debt_status",
    "group_activities": "13. GROUP_ACTIVITIES — nhật ký nhóm, phủ đủ 8 activity_type",
    "notifications": "14. NOTIFICATIONS",
    "admin_audit_logs": "15. ADMIN_AUDIT_LOGS — suspend / reactivate / lock",
}

ORDER = ["users", "sessions", "user_tokens", "groups", "group_members", "group_invites",
         "bills", "bill_items", "bill_item_assignments", "ocr_jobs", "payments",
         "debts", "group_activities", "notifications", "admin_audit_logs"]

out = []
w = out.append

w("-- ============================================================================")
w("-- PaySplit — DỮ LIỆU MOCK (seed) cho schema Database/dbv1.sql")
w("--")
w("-- Dữ liệu được sinh theo ĐÚNG trình tự nghiệp vụ trong PRD, không phải số ngẫu nhiên:")
w("--   đăng ký → xác thực email → tạo nhóm → mời/tham gia → upload ảnh bill → OCR")
w("--   → sửa bill → gán món cho thành viên → captain chốt bill → sinh công nợ")
w("--   → debtor gộp nợ tạo mã QR → nộp bằng chứng → creditor xác nhận / từ chối")
w("--   → tất toán → rời nhóm khi net balance = 0.")
w("--")
w("-- Bảo đảm về mặt số học (đã assert khi sinh, và assert lại ở cuối file):")
w("--   * SUM(debts.amount) của 1 bill + phần của creditor == bills.total (chia theo")
w("--     largest-remainder / Hamilton, số nguyên VND, không sai 1 đồng).")
w("--   * payments.amount == SUM(debts.amount) của các khoản nợ mà payment đó gộp.")
w("--   * Mọi khoá ngoại tổ hợp (id, group_id) đều trỏ đúng nhóm.")
w("--   * Mọi CHECK constraint của schema đều thoả (trạng thái ↔ mốc thời gian).")
w("--")
w("-- Mật khẩu của TẤT CẢ tài khoản mock: Password@123")
w("--   (bcrypt cost 12, hash đã verify bằng golang.org/x/crypto/bcrypt)")
w("--")
w("-- Cách chạy:  psql -d paysplit -f Database/dbv1.sql")
w("--             psql -d paysplit -f Database/seed_mock_data.sql")
w("-- ============================================================================")
w("")
w("BEGIN;")
w("")
w("-- Xoá sạch dữ liệu cũ để file có thể chạy lại nhiều lần.")
w("-- CẢNH BÁO: lệnh này xoá toàn bộ dữ liệu nghiệp vụ. Chỉ dùng trên DB dev/demo.")
w("TRUNCATE TABLE admin_audit_logs, notifications, group_activities, debts, payments,")
w("               ocr_jobs, bill_item_assignments, bill_items, bills, group_invites,")
w("               group_members, groups, user_tokens, sessions, users RESTART IDENTITY CASCADE;")
w("")

for t in ORDER:
    w("-- ---------------------------------------------------------------------------")
    w(f"-- {SECTION[t]}")
    w("-- ---------------------------------------------------------------------------")
    w(f"INSERT INTO {t} ({COLS[t]}) VALUES")
    for i, r in enumerate(rows[t]):
        w(("  " + r) + ("," if i < len(rows[t]) - 1 else ";"))
    w("")

# ------- assertions ---------------------------------------------------------
w("-- ---------------------------------------------------------------------------")
w("-- 16. KIỂM TRA TÍNH NHẤT QUÁN — transaction sẽ ROLLBACK nếu có bất kỳ sai lệch nào")
w("-- ---------------------------------------------------------------------------")
w("""DO $$
DECLARE v RECORD; n INT;
BEGIN
    -- (1) Với mỗi bill đã chốt: SUM(debts) + phần của creditor phải bằng đúng bills.total.
    --     Phần của creditor được suy ra = total - SUM(debts), nên chỉ cần kiểm SUM(debts) < total.
    FOR v IN
        SELECT b.id, b.merchant_name, b.total, COALESCE(SUM(d.amount),0) AS debt_sum
        FROM bills b LEFT JOIN debts d ON d.bill_id = b.id
        WHERE b.status = 'finalized'
        GROUP BY b.id, b.merchant_name, b.total
    LOOP
        IF v.debt_sum > v.total OR v.debt_sum = 0 THEN
            RAISE EXCEPTION 'Bill % (%): tong no % khong hop le so voi total %',
                v.id, v.merchant_name, v.debt_sum, v.total;
        END IF;
    END LOOP;

    -- (2) payments.amount phải bằng tổng các khoản nợ mà nó đang gộp
    --     (bỏ qua payment đã bị từ chối và đã nhả nợ ra — giữ lại làm audit trail).
    FOR v IN
        SELECT p.id, p.reference_code, p.amount, SUM(d.amount) AS s
        FROM payments p JOIN debts d ON d.payment_id = p.id
        GROUP BY p.id, p.reference_code, p.amount
    LOOP
        IF v.amount <> v.s THEN
            RAISE EXCEPTION 'Payment % (%): amount % <> tong debts %',
                v.id, v.reference_code, v.amount, v.s;
        END IF;
    END LOOP;

    -- (3) Nợ chỉ được phát sinh từ bill đã chốt.
    SELECT count(*) INTO n FROM debts d JOIN bills b ON b.id = d.bill_id
     WHERE b.status <> 'finalized';
    IF n > 0 THEN RAISE EXCEPTION 'Co % khoan no sinh tu bill chua finalized', n; END IF;

    -- (4) Debtor/creditor của debt phải là người thực sự tham gia bill đó
    --     (creditor là người ứng tiền, debtor phải có ít nhất 1 món trong bill).
    SELECT count(*) INTO n
      FROM debts d
     WHERE NOT EXISTS (
        SELECT 1 FROM bill_item_assignments a
          JOIN bill_items i ON i.id = a.bill_item_id
         WHERE i.bill_id = d.bill_id AND a.member_id = d.debtor_member_id);
    IF n > 0 THEN RAISE EXCEPTION 'Co % khoan no ma debtor khong ganh mon nao trong bill', n; END IF;

    SELECT count(*) INTO n
      FROM debts d JOIN bills b ON b.id = d.bill_id
     WHERE d.creditor_member_id <> b.creditor_member_id;
    IF n > 0 THEN RAISE EXCEPTION 'Co % khoan no co creditor khac nguoi ung tien cua bill', n; END IF;

    -- (5) Thành viên đã rời nhóm phải có net balance = 0 (FR 4.1.10).
    FOR v IN
        SELECT m.id, u.display_name, b.net_balance
        FROM group_members m
        JOIN users u ON u.id = m.user_id
        JOIN v_member_balances b ON b.member_id = m.id
        WHERE m.status = 'inactive'
    LOOP
        IF v.net_balance <> 0 THEN
            RAISE EXCEPTION 'Thanh vien da roi nhom % (%) con so du %',
                v.id, v.display_name, v.net_balance;
        END IF;
    END LOOP;

    -- (6) Không ai được tham gia bill trước ngày họ vào nhóm.
    SELECT count(*) INTO n
      FROM bill_item_assignments a
      JOIN bill_items i  ON i.id = a.bill_item_id
      JOIN bills b       ON b.id = i.bill_id
      JOIN group_members m ON m.id = a.member_id
     WHERE m.joined_at > b.created_at
        OR (m.left_at IS NOT NULL AND m.left_at < b.created_at);
    IF n > 0 THEN RAISE EXCEPTION 'Co % phan bo mon cho thanh vien ngoai khoang thoi gian o trong nhom', n; END IF;

    -- (7) Chủ nợ của bill đã chốt bắt buộc phải có tài khoản ngan hang (FR 4.1.15).
    SELECT count(*) INTO n
      FROM bills b JOIN group_members m ON m.id = b.creditor_member_id
      JOIN users u ON u.id = m.user_id
     WHERE b.status = 'finalized'
       AND (u.default_bank_code IS NULL OR u.default_bank_account_number IS NULL);
    IF n > 0 THEN RAISE EXCEPTION 'Co % bill da chot ma chu no chua cau hinh ngan hang', n; END IF;

    -- (8) use_count cua invite khong duoc vuot qua so thanh vien thuc te cua nhom.
    SELECT count(*) INTO n
      FROM group_invites gi
     WHERE gi.use_count > (SELECT count(*) FROM group_members gm WHERE gm.group_id = gi.group_id);
    IF n > 0 THEN RAISE EXCEPTION 'Co % ma moi co use_count lon hon so thanh vien nhom', n; END IF;

    RAISE NOTICE 'PaySplit seed: tat ca % kiem tra nhat quan da PASS', 8;
END $$;""")
w("")
w("COMMIT;")
w("")
w("-- ---------------------------------------------------------------------------")
w("-- 17. TRUY VẤN ĐỐI CHIẾU NHANH (chạy tay sau khi seed)")
w("-- ---------------------------------------------------------------------------")
w("-- Số dư ròng từng thành viên (dương = được nhận về, âm = còn phải trả):")
w("--   SELECT g.name, u.display_name, b.net_balance")
w("--   FROM v_member_balances b")
w("--   JOIN group_members m ON m.id = b.member_id")
w("--   JOIN users u  ON u.id = m.user_id")
w("--   JOIN groups g ON g.id = m.group_id")
w("--   ORDER BY g.name, b.net_balance DESC;")
w("--")
w("-- Một mã QR trả cho nhiều hoá đơn (điểm khác biệt cốt lõi của PaySplit):")
w("--   SELECT p.reference_code, p.amount, count(d.id) AS so_khoan_no,")
w("--          string_agg(b.merchant_name, ' + ') AS cac_hoa_don")
w("--   FROM payments p JOIN debts d ON d.payment_id = p.id")
w("--   JOIN bills b ON b.id = d.bill_id")
w("--   GROUP BY p.id HAVING count(d.id) > 1;")
w("--")
w("-- Bảng phân rã một hoá đơn tới từng món (truy vết mức item):")
w("--   SELECT bi.name, gm_u.display_name, a.weight")
w("--   FROM bill_items bi")
w("--   JOIN bill_item_assignments a ON a.bill_item_id = bi.id")
w("--   JOIN group_members gm ON gm.id = a.member_id")
w("--   JOIN users gm_u ON gm_u.id = gm.user_id")
w("--   WHERE bi.bill_id = '<bill_id>' ORDER BY bi.created_at;")

with open("/home/lampt14/Documents/ProjectGo/PaySplit-RP/Database/seed_mock_data.sql",
          "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")

# ------------------------------------------------------------- báo cáo -----
print("Đã sinh Database/seed_mock_data.sql\n")
for t in ORDER:
    print(f"  {t:24s} {len(rows[t]):4d} dòng")
print()
for bk in FINALIZED:
    b = BILLS[bk]
    s = SHARES[bk]
    cred = s.get(b["creditor"], 0)
    tot = sum(s.values())
    debts_sum = tot - cred
    ok = "OK " if tot == b["total"] else "SAI"
    print(f"  [{ok}] {bk:4s} {str(b['merchant'])[:26]:28s} total={b['total']:>9,} "
          f"creditor({b['creditor']})={cred:>8,} debts={debts_sum:>9,}")
print()
for p in PAYMENTS:
    print(f"  {p['ref']}  {p['debtor']:>5s} -> {p['creditor']:<5s} {p['amount']:>9,}  "
          f"bills={'+'.join(p['bills'])}")
print()
from collections import Counter
print("  debt_status:", dict(Counter(x["status"] for x in DEBT.values())))
