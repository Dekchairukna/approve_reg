"""สำรอง/กู้คืน/ย้ายข้อมูลทั้งระบบ ระหว่าง SQLite และ PostgreSQL"""
import os
import tempfile

from .db import DB, TABLES, init_db

SQLITE_MAGIC = b'SQLite format 3\x00'


def copy_all(src, dst, replace=False):
    """คัดลอกทุกตารางจาก src ไป dst (DB ทั้งคู่ โครงสร้างล่าสุดแล้ว) คืนจำนวนแถวต่อตาราง"""
    existing = {t: dst.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in TABLES}
    if any(existing.values()) and not replace:
        raise ValueError('ปลายทางมีข้อมูลอยู่แล้ว: ' + ', '.join(f'{t} {n}' for t, n in existing.items() if n))
    counts = {}
    with dst:
        if dst.pg:
            dst.execute('TRUNCATE ' + ', '.join(TABLES) + ' RESTART IDENTITY CASCADE')
        else:
            for t in reversed(TABLES):
                dst.execute(f'DELETE FROM {t}')
        for t in TABLES:
            dcols = dst.columns(t)
            cols = [c for c in src.columns(t) if c in dcols]
            rows = [tuple(r[c] for c in cols) for r in src.execute(f'SELECT {", ".join(cols)} FROM {t}')]
            dst.executemany(f'INSERT INTO {t} ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})', rows)
            if dst.pg and 'id' in cols:
                dst.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                            f"COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)")
            counts[t] = len(rows)
    return counts


def restore_from_sqlite_bytes(data, target):
    """กู้คืนจากไฟล์ SQLite (เช่น instance/checkin.db จากเครื่องอื่น) ทับข้อมูลทั้งหมดใน target"""
    if not data.startswith(SQLITE_MAGIC):
        raise ValueError('ไฟล์นี้ไม่ใช่ไฟล์ฐานข้อมูลของระบบ (ต้องเป็นไฟล์ checkin.db)')
    fd, path = tempfile.mkstemp(suffix='.db')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        try:
            init_db(path)                     # อัปเกรดโครงสร้างรุ่นเก่า
            src = DB(path)
            tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except Exception as e:  # noqa: BLE001
            raise ValueError(f'เปิดไฟล์ฐานข้อมูลไม่ได้: {e}')
        if not {'users', 'competitions', 'entries'} <= tables:
            src.close()
            raise ValueError('ไฟล์นี้ไม่ใช่ฐานข้อมูลของระบบนี้')
        dst = DB(target)
        try:
            return copy_all(src, dst, replace=True)
        finally:
            src.close()
            dst.close()
    finally:
        for p in (path, path + '-wal', path + '-shm'):
            try:
                os.remove(p)
            except OSError:
                pass


def backup_to_sqlite_bytes(source):
    """สำรองข้อมูลทั้งหมดเป็นไฟล์ SQLite ไฟล์เดียว (เปิดด้วยระบบนี้ หรือกู้คืนที่อื่นได้)"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.remove(path)
    try:
        init_db(path)
        src, dst = DB(source), DB(path)
        try:
            copy_all(src, dst, replace=True)
            dst.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            dst.execute('PRAGMA journal_mode=DELETE')
        finally:
            src.close()
            dst.close()
        with open(path, 'rb') as f:
            return f.read()
    finally:
        for p in (path, path + '-wal', path + '-shm'):
            try:
                os.remove(p)
            except OSError:
                pass
