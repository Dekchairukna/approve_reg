"""คำสั่งจัดการระบบจาก Terminal

  python3 manage.py create-user <username> --role admin|staff [--name "ชื่อ"]
  python3 manage.py reset-password <username>
  python3 manage.py list-users
  python3 manage.py copy-to-postgres "postgresql://..."   ย้ายข้อมูลจาก SQLite ในเครื่องขึ้น PostgreSQL
"""
import argparse
import getpass
import os
import sys

from werkzeug.security import generate_password_hash

from checkin import create_app
from checkin.auth import create_user, validate_password, validate_username
from checkin.backup import copy_all
from checkin.db import DB, init_db


def ask_password():
    while True:
        p = getpass.getpass('รหัสผ่าน: ')
        e = validate_password(p)
        if e:
            print(e)
            continue
        if getpass.getpass('ยืนยันรหัสผ่าน: ') != p:
            print('รหัสผ่านไม่ตรงกัน')
            continue
        return p


def main():
    ap = argparse.ArgumentParser(description='จัดการระบบยืนยันรายชื่อนักกีฬา')
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('create-user', help='สร้างบัญชีเจ้าหน้าที่')
    c.add_argument('username')
    c.add_argument('--role', choices=['admin', 'staff'], default='staff')
    c.add_argument('--name', default='')
    r = sub.add_parser('reset-password', help='ตั้งรหัสผ่านใหม่')
    r.add_argument('username')
    sub.add_parser('list-users', help='แสดงบัญชีทั้งหมด')
    cp = sub.add_parser('copy-to-postgres', help='คัดลอกข้อมูลทั้งหมดจาก SQLite ในเครื่องขึ้น PostgreSQL')
    cp.add_argument('url', help='postgresql://... (บน Railway ใช้ค่า DATABASE_PUBLIC_URL)')
    cp.add_argument('--sqlite', default='', help='ไฟล์ SQLite ต้นทาง (ค่าเริ่มต้น instance/checkin.db)')
    cp.add_argument('--replace', action='store_true', help='ลบข้อมูลเดิมใน PostgreSQL ก่อนคัดลอก')
    a = ap.parse_args()

    if a.cmd == 'copy-to-postgres':
        return copy_to_postgres(a)
    app = create_app()
    conn = DB(app.config['DATABASE'])
    if a.cmd == 'create-user':
        e = validate_username(a.username)
        if e:
            sys.exit(e)
        if conn.execute('SELECT 1 FROM users WHERE username=?', (a.username,)).fetchone():
            sys.exit('มีชื่อผู้ใช้นี้แล้ว')
        with conn:
            create_user(conn, a.username, a.name or a.username, ask_password(), a.role)
        print(f'สร้างบัญชี {a.username} ({a.role}) แล้ว')
    elif a.cmd == 'reset-password':
        if not conn.execute('SELECT 1 FROM users WHERE username=?', (a.username,)).fetchone():
            sys.exit('ไม่พบชื่อผู้ใช้นี้')
        with conn:
            conn.execute('UPDATE users SET password_hash=?, active=1 WHERE username=?',
                         (generate_password_hash(ask_password()), a.username))
        print('ตั้งรหัสผ่านใหม่แล้ว')
    elif a.cmd == 'list-users':
        for u in conn.execute('SELECT username, name, role, active, last_login FROM users ORDER BY id'):
            print(f"{u['username']:<20} {u['role']:<6} {'ใช้งาน' if u['active'] else 'ปิด':<6} {u['name']}  เข้าล่าสุด {u['last_login'] or '-'}")



def copy_to_postgres(a):
    base = os.path.dirname(os.path.abspath(__file__))
    src_path = a.sqlite or os.path.join(os.environ.get('CHECKIN_DATA', os.path.join(base, 'instance')), 'checkin.db')
    if not os.path.exists(src_path):
        sys.exit(f'ไม่พบไฟล์ {src_path}')
    if not a.url.startswith(('postgres://', 'postgresql://')):
        sys.exit('URL ต้องขึ้นต้นด้วย postgresql://')
    if '.railway.internal' in a.url:
        sys.exit('URL นี้เป็นที่อยู่ภายในของ Railway (ใช้ได้เฉพาะบนเซิร์ฟเวอร์ Railway)\n'
                 'ให้ใช้ค่า DATABASE_PUBLIC_URL แทน (ที่อยู่จะเป็นแบบ ...proxy.rlwy.net:เลขพอร์ต)')
    init_db(src_path, os.path.join(os.path.dirname(src_path), 'uploads'))   # อัปเกรดโครงสร้าง SQLite รุ่นเก่าก่อน
    init_db(a.url)
    try:
        counts = copy_all(DB(src_path), DB(a.url), replace=a.replace)
    except ValueError as e:
        sys.exit(f'{e}\nถ้าต้องการเขียนทับทั้งหมด ใส่ --replace')
    for t, n in counts.items():
        print(f'  {t:<13} {n:>6} แถว')
    print('คัดลอกเสร็จแล้ว')


if __name__ == '__main__':
    main()
