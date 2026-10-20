"""บัญชีเจ้าหน้าที่: เข้าสู่ระบบ, สิทธิ์, จัดการผู้ใช้

บทบาท
  admin — จัดการการแข่งขัน ผู้ใช้ และทุกอย่างของ staff
  staff — ดูภาพรวม พิมพ์ใบรายงานตัว ส่งออก Excel แก้รายชื่อได้แม้เลยเวลาปิด
"""
import re
import time
from functools import wraps

from flask import Blueprint, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .logic import stamp

bp = Blueprint('auth', __name__)
ROLES = ('admin', 'staff')
_attempts = {}   # ip -> [จำนวนครั้ง, เวลาเริ่ม]
MAX_ATTEMPTS, WINDOW = 10, 600


def err(msg, code=400):
    return jsonify(error=msg), code


def load_user():
    g.user = None
    uid = session.get('uid')
    if uid:
        r = get_db().execute('SELECT * FROM users WHERE id=? AND active=1', (uid,)).fetchone()
        if r and session.get('pwv') == r['password_hash'][-12:]:
            g.user = dict(id=r['id'], username=r['username'], name=r['name'], role=r['role'])
        else:
            session.clear()


def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not g.get('user'):
                return err('กรุณาเข้าสู่ระบบ', 401)
            if role == 'admin' and g.user['role'] != 'admin':
                return err('ต้องเป็นผู้ดูแลระบบ (admin)', 403)
            return fn(*a, **kw)
        return wrapper
    return deco


def user_count():
    return get_db().execute('SELECT COUNT(*) FROM users').fetchone()[0]


def validate_username(u):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,32}', u or ''):
        return 'ชื่อผู้ใช้ต้องเป็นอังกฤษ/ตัวเลข 3–32 ตัว (ใช้ _ . - ได้)'
    return None


def validate_password(p):
    if len(p or '') < 8:
        return 'รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร'
    return None


def create_user(conn, username, name, password, role):
    conn.execute('INSERT INTO users (username, name, password_hash, role, created_at) VALUES (?,?,?,?,?)',
                 (username, name, generate_password_hash(password), role, stamp()))


def _start_session(row):
    session.clear()
    session.permanent = True
    session['uid'] = row['id']
    session['pwv'] = row['password_hash'][-12:]   # เปลี่ยนรหัสแล้ว session เก่าหมดอายุ


@bp.get('/api/auth/me')
def me():
    return jsonify(user=g.user, needsSetup=user_count() == 0)


@bp.post('/api/auth/setup')
def setup():
    """สร้างผู้ดูแลคนแรก ใช้ได้เฉพาะตอนยังไม่มีผู้ใช้เลย"""
    if user_count() > 0:
        return err('ตั้งค่าเริ่มต้นไปแล้ว', 403)
    d = request.get_json(silent=True) or {}
    username, name, pw = (d.get('username') or '').strip(), (d.get('name') or '').strip(), d.get('password') or ''
    e = validate_username(username) or validate_password(pw)
    if e:
        return err(e)
    conn = get_db()
    with conn:
        create_user(conn, username, name or username, pw, 'admin')
        conn.execute('UPDATE users SET last_login=? WHERE username=?', (stamp(), username))
    row = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    _start_session(row)
    return jsonify(ok=True)


@bp.post('/api/auth/login')
def login():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    n, t0 = _attempts.get(ip, [0, time.time()])
    if time.time() - t0 > WINDOW:
        n, t0 = 0, time.time()
    if n >= MAX_ATTEMPTS:
        return err('ลองเข้าสู่ระบบผิดหลายครั้ง กรุณารอ 10 นาที', 429)
    d = request.get_json(silent=True) or {}
    row = get_db().execute('SELECT * FROM users WHERE username=?', ((d.get('username') or '').strip(),)).fetchone()
    if not row or not row['active'] or not check_password_hash(row['password_hash'], d.get('password') or ''):
        _attempts[ip] = [n + 1, t0]
        return err('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 401)
    _attempts.pop(ip, None)
    conn = get_db()
    with conn:
        conn.execute('UPDATE users SET last_login=? WHERE id=?', (stamp(), row['id']))
    _start_session(row)
    return jsonify(ok=True)


@bp.post('/api/auth/logout')
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.post('/api/auth/password')
@login_required()
def change_own_password():
    d = request.get_json(silent=True) or {}
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE id=?', (g.user['id'],)).fetchone()
    if not check_password_hash(row['password_hash'], d.get('current') or ''):
        return err('รหัสผ่านปัจจุบันไม่ถูกต้อง')
    e = validate_password(d.get('new'))
    if e:
        return err(e)
    with conn:
        conn.execute('UPDATE users SET password_hash=? WHERE id=?', (generate_password_hash(d['new']), row['id']))
    _start_session(conn.execute('SELECT * FROM users WHERE id=?', (row['id'],)).fetchone())
    return jsonify(ok=True)


# ---------- จัดการผู้ใช้ (admin) ----------
@bp.get('/api/admin/users')
@login_required('admin')
def list_users():
    rows = get_db().execute('SELECT id, username, name, role, active, created_at, last_login FROM users ORDER BY id')
    return jsonify(users=[dict(r) for r in rows])


@bp.post('/api/admin/users')
@login_required('admin')
def add_user():
    d = request.get_json(silent=True) or {}
    username, name, pw, role = (d.get('username') or '').strip(), (d.get('name') or '').strip(), d.get('password') or '', d.get('role')
    e = validate_username(username) or validate_password(pw) or (None if role in ROLES else 'บทบาทไม่ถูกต้อง')
    if e:
        return err(e)
    conn = get_db()
    if conn.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
        return err('ชื่อผู้ใช้นี้มีอยู่แล้ว')
    with conn:
        create_user(conn, username, name or username, pw, role)
    return jsonify(ok=True)


@bp.post('/api/admin/users/<int:uid>')
@login_required('admin')
def update_user(uid):
    d = request.get_json(silent=True) or {}
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not row:
        return err('ไม่พบผู้ใช้', 404)
    role = d.get('role', row['role'])
    active = int(bool(d.get('active', row['active'])))
    if role not in ROLES:
        return err('บทบาทไม่ถูกต้อง')
    if uid == g.user['id'] and (role != 'admin' or not active):
        return err('เปลี่ยนบทบาทหรือปิดบัญชีของตัวเองไม่ได้')
    admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id<>?", (uid,)).fetchone()[0]
    if row['role'] == 'admin' and (role != 'admin' or not active) and admins == 0:
        return err('ต้องมีผู้ดูแลระบบที่ใช้งานอยู่อย่างน้อย 1 คน')
    if d.get('password'):
        e = validate_password(d['password'])
        if e:
            return err(e)
    with conn:
        conn.execute('UPDATE users SET name=?, role=?, active=? WHERE id=?',
                     ((d.get('name') or row['name']).strip(), role, active, uid))
        if d.get('password'):
            conn.execute('UPDATE users SET password_hash=? WHERE id=?', (generate_password_hash(d['password']), uid))
    return jsonify(ok=True)


@bp.post('/api/admin/users/<int:uid>/delete')
@login_required('admin')
def delete_user(uid):
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not row:
        return err('ไม่พบผู้ใช้', 404)
    if uid == g.user['id']:
        return err('ลบบัญชีของตัวเองไม่ได้')
    admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id<>?", (uid,)).fetchone()[0]
    if row['role'] == 'admin' and admins == 0:
        return err('ต้องมีผู้ดูแลระบบที่ใช้งานอยู่อย่างน้อย 1 คน')
    with conn:
        conn.execute('DELETE FROM users WHERE id=?', (uid,))
    return jsonify(ok=True)
