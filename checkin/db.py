"""ฐานข้อมูล: ใช้ PostgreSQL เมื่อมี DATABASE_URL ไม่มีก็ใช้ SQLite ในโฟลเดอร์ instance/

โค้ดส่วนอื่นเขียน SQL แบบเดียวกันทั้งสองฐาน (ใช้ ? เป็นตัวแทนค่า) แล้วให้ DB แปลงให้
"""
import os
import sqlite3

from flask import current_app, g

TABLES = ['users', 'competitions', 'events', 'entries', 'confs', 'logs']

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id {pk},
  username TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'staff',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT '',
  last_login TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS competitions (
  id {pk},
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  sport TEXT NOT NULL DEFAULT '',
  subtitle TEXT NOT NULL DEFAULT '',
  logo TEXT NOT NULL DEFAULT '',
  logo_mime TEXT NOT NULL DEFAULT '',
  logo_data {blob},
  max_events INTEGER NOT NULL DEFAULT 3,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS events (
  id {pk},
  comp_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  short TEXT NOT NULL DEFAULT '',
  level TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  start_date TEXT NOT NULL DEFAULT '',
  start_time TEXT NOT NULL DEFAULT '',
  deadline TEXT NOT NULL DEFAULT '',
  sort INTEGER NOT NULL DEFAULT 0,
  UNIQUE (comp_id, name)
);
CREATE TABLE IF NOT EXISTS entries (
  id {pk},
  comp_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
  event TEXT NOT NULL,
  school TEXT NOT NULL,
  level TEXT NOT NULL DEFAULT '',
  team TEXT NOT NULL DEFAULT '',
  prefix TEXT NOT NULL DEFAULT '',
  first TEXT NOT NULL DEFAULT '',
  last TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'รอยืนยัน',
  by_name TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL DEFAULT '',
  o_prefix TEXT NOT NULL DEFAULT '',
  o_first TEXT NOT NULL DEFAULT '',
  o_last TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_entries_comp_school ON entries(comp_id, school);
CREATE TABLE IF NOT EXISTS confs (
  comp_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
  school TEXT NOT NULL,
  event TEXT NOT NULL,
  by_name TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL DEFAULT '',
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (comp_id, school, event)
);
CREATE TABLE IF NOT EXISTS logs (
  id {pk},
  comp_id INTEGER NOT NULL,
  at TEXT, school TEXT, event TEXT, entry_id INTEGER,
  action TEXT, before TEXT, after TEXT, by_name TEXT, phone TEXT,
  staff_user TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_logs_comp ON logs(comp_id, id);
"""
SQLITE_SCHEMA = _SCHEMA.format(pk='INTEGER PRIMARY KEY AUTOINCREMENT', blob='BLOB')
PG_SCHEMA = _SCHEMA.format(pk='SERIAL PRIMARY KEY', blob='BYTEA')


class Row(dict):
    """แถวข้อมูล: ใช้ได้ทั้ง r['ชื่อคอลัมน์'] และ r[0]"""
    def __getitem__(self, k):
        if isinstance(k, int):
            return list(self.values())[k]
        return super().__getitem__(k)


class DB:
    def __init__(self, target):
        self.pg = target.startswith(('postgres://', 'postgresql://'))
        if self.pg:
            import psycopg
            url = target.replace('postgres://', 'postgresql://', 1)
            self.conn = psycopg.connect(url, autocommit=True,
                                        row_factory=lambda cur: (lambda vals: Row(zip([c.name for c in cur.description], vals))))
            self._tx = []
        else:
            self.conn = sqlite3.connect(target, timeout=20)
            self.conn.row_factory = lambda cur, vals: Row(zip([c[0] for c in cur.description], vals))
            self.conn.execute('PRAGMA foreign_keys=ON')
            self.conn.execute('PRAGMA journal_mode=WAL')

    def _sql(self, sql):
        return sql.replace('?', '%s') if self.pg else sql

    def execute(self, sql, args=()):
        if self.pg:
            return self.conn.execute(self._sql(sql), args)
        return self.conn.execute(sql, args)

    def executemany(self, sql, seq):
        seq = list(seq)
        if not seq:
            return
        if self.pg:
            with self.conn.cursor() as cur:
                cur.executemany(self._sql(sql), seq)
        else:
            self.conn.executemany(sql, seq)

    def insert_id(self, sql, args=()):
        """INSERT แล้วคืน id ของแถวใหม่"""
        return self.execute(sql + ' RETURNING id', args).fetchone()[0]

    # with db: ... = ทำทั้งก้อนใน transaction เดียว
    def __enter__(self):
        if self.pg:
            tx = self.conn.transaction()
            tx.__enter__()
            self._tx.append(tx)
        return self

    def __exit__(self, et, ev, tb):
        if self.pg:
            return self._tx.pop().__exit__(et, ev, tb)
        if et is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        return False

    def commit(self):
        if not self.pg:
            self.conn.commit()

    def close(self):
        self.conn.close()

    def columns(self, table):
        if self.pg:
            rows = self.execute('SELECT column_name FROM information_schema.columns WHERE table_name=?', (table,))
            return [r[0] for r in rows]
        return [r['name'] for r in self.execute(f'PRAGMA table_info({table})')]


def database_target(instance_dir):
    return os.environ.get('DATABASE_URL') or os.path.join(instance_dir, 'checkin.db')


def get_db():
    if 'db' not in g:
        g.db = DB(current_app.config['DATABASE'])
    return g.db


def close_db(_=None):
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()


def init_db(target, upload_dir=None):
    db = DB(target)
    if db.pg:
        with db:
            for stmt in PG_SCHEMA.split(';'):
                if stmt.strip():
                    db.execute(stmt)
    else:
        _migrate_sqlite_v1(db)
        db.conn.executescript(SQLITE_SCHEMA)
        db.commit()
        _migrate_sqlite_v2(db, upload_dir)
    db.close()


def _migrate_sqlite_v1(db):
    """ฐานข้อมูลรุ่นแรกใช้คอลัมน์ชื่อ by / user ซึ่งเป็นคำสงวนของ PostgreSQL: เปลี่ยนชื่อ"""
    for table, old, new in (('entries', 'by', 'by_name'), ('confs', 'by', 'by_name'),
                            ('logs', 'by', 'by_name'), ('logs', 'user', 'staff_user')):
        cols = db.columns(table)
        if old in cols and new not in cols:
            db.execute(f'ALTER TABLE {table} RENAME COLUMN "{old}" TO {new}')
    db.commit()


def _migrate_sqlite_v2(db, upload_dir):
    """เพิ่มคอลัมน์เก็บโลโก้ในฐานข้อมูล แล้วย้ายไฟล์โลโก้เดิมเข้าไป"""
    cols = db.columns('competitions')
    if 'logo_mime' not in cols:
        db.execute("ALTER TABLE competitions ADD COLUMN logo_mime TEXT NOT NULL DEFAULT ''")
    if 'logo_data' not in cols:
        db.execute('ALTER TABLE competitions ADD COLUMN logo_data BLOB')
    db.commit()
    if not upload_dir:
        return
    for r in db.execute("SELECT id, logo FROM competitions WHERE logo<>'' AND logo_data IS NULL").fetchall():
        path = os.path.join(upload_dir, r['logo'])
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = f.read()
            ext = os.path.splitext(path)[1].lower().lstrip('.')
            mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else f'image/{ext}'
            db.execute('UPDATE competitions SET logo_data=?, logo_mime=? WHERE id=?', (data, mime, r['id']))
    db.commit()
