"""อ่านข้อมูลการแข่งขันจากฐานข้อมูลเป็น dict สำหรับ logic.py"""
from .db import get_db


COMP_COLS = 'id, slug, name, sport, subtitle, logo, logo_mime, max_events, active, created_at'


def comp_by_slug(slug, include_inactive=False):
    r = get_db().execute(f'SELECT {COMP_COLS} FROM competitions WHERE slug=?', (slug,)).fetchone()
    if r and (r['active'] or include_inactive):
        return dict(r)
    return None


def comp_by_id(cid):
    r = get_db().execute(f'SELECT {COMP_COLS} FROM competitions WHERE id=?', (cid,)).fetchone()
    return dict(r) if r else None


def comp_public(c):
    return dict(id=c['id'], slug=c['slug'], name=c['name'], sport=c['sport'], subtitle=c['subtitle'],
                logo=f"/logo/{c['id']}?v={c['logo']}" if c['logo'] else '', max=c['max_events'], active=bool(c['active']))


def load_events(cid):
    return [dict(id=r['id'], event=r['name'], short=r['short'], level=r['level'], category=r['category'],
                 startDate=r['start_date'], startTime=r['start_time'], deadline=r['deadline'], sort=r['sort'])
            for r in get_db().execute(
                "SELECT * FROM events WHERE comp_id=? ORDER BY CASE WHEN start_date='' THEN 1 ELSE 0 END, "
                "start_date, sort", (cid,))]


def load_entries(cid, school=None):
    q, args = 'SELECT * FROM entries WHERE comp_id=?', [cid]
    if school is not None:
        q += ' AND school=?'
        args.append(school)
    return [dict(id=r['id'], event=r['event'], school=r['school'], level=r['level'], team=r['team'],
                 prefix=r['prefix'], first=r['first'], last=r['last'], status=r['status'], by=r['by_name'],
                 phone=r['phone'], at=r['at'], oPrefix=r['o_prefix'], oFirst=r['o_first'], oLast=r['o_last'],
                 checkinAt=r['checkin_at'], checkinBy=r['checkin_by'])
            for r in get_db().execute(q + ' ORDER BY id', args)]


def load_confs(cid):
    return [dict(school=r['school'], event=r['event'], by=r['by_name'], phone=r['phone'], at=r['at'], count=r['count'])
            for r in get_db().execute('SELECT * FROM confs WHERE comp_id=?', (cid,))]


def load_all(cid, auto=True):
    """auto=True: รายการที่เลยเวลาปิดแล้วยังไม่ยืนยัน ถือว่ายืนยันตามที่สมัคร (ดู logic.apply_auto)"""
    from . import logic
    entries, events, confs = load_entries(cid), load_events(cid), load_confs(cid)
    if auto:
        entries, confs = logic.apply_auto(entries, events, confs, logic.now_bkk())
    return entries, events, confs


def schools(cid):
    return [r[0] for r in get_db().execute(
        'SELECT DISTINCT school FROM entries WHERE comp_id=? ORDER BY school', (cid,))]


def load_results(cid):
    return [dict(event=r['event'], school=r['school'], unit=r['unit'], medal=r['medal'], by=r['by_user'], at=r['at'])
            for r in get_db().execute('SELECT * FROM ck_results WHERE comp_id=?', (cid,))]
