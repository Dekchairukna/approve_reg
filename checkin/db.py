"""ฐานข้อมูล SQLite: การเชื่อมต่อและโครงสร้างตาราง"""
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'staff',          -- admin | staff
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT '',
  last_login TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS competitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  sport TEXT NOT NULL DEFAULT '',
  subtitle TEXT NOT NULL DEFAULT '',
  logo TEXT NOT NULL DEFAULT '',
  max_events INTEGER NOT NULL DEFAULT 3,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  comp_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  short TEXT NOT NULL DEFAULT '',
  level TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  start_date TEXT NOT NULL DEFAULT '',
  start_time TEXT NOT NULL DEFAULT '',
  deadline TEXT NOT NULL DEFAULT '',            -- 'YYYY-MM-DD HH:MM' เวลาไทย, ว่าง = ยังไม่ปิด
  sort INTEGER NOT NULL DEFAULT 0,
  UNIQUE (comp_id, name)
);
CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  comp_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
  event TEXT NOT NULL,
  school TEXT NOT NULL,
  level TEXT NOT NULL DEFAULT '',
  team TEXT NOT NULL DEFAULT '',
  prefix TEXT NOT NULL DEFAULT '',
  first TEXT NOT NULL DEFAULT '',
  last TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'รอยืนยัน',
  by TEXT NOT NULL DEFAULT '',
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
  by TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL DEFAULT '',
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (comp_id, school, event)
);
CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  comp_id INTEGER NOT NULL,
  at TEXT, school TEXT, event TEXT, entry_id INTEGER,
  action TEXT, before TEXT, after TEXT, by TEXT, phone TEXT,
  user TEXT NOT NULL DEFAULT ''                 -- ชื่อผู้ใช้เจ้าหน้าที่ ถ้าแก้ผ่านบัญชีเจ้าหน้าที่
);
CREATE INDEX IF NOT EXISTS ix_logs_comp ON logs(comp_id, id);
"""


def connect(path):
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def get_db():
    if 'db' not in g:
        g.db = connect(current_app.config['DATABASE'])
    return g.db


def close_db(_=None):
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()


def init_db(path):
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
