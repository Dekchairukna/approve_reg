"""หน้าสาธารณะ: โรงเรียนยืนยันรายชื่อโดยไม่ต้องล็อกอิน"""
import os
import threading

from markupsafe import escape

from flask import Blueprint, Response, abort, current_app, g, jsonify, request, send_from_directory

from . import logic, store
from .db import get_db

bp = Blueprint('public', __name__)
write_lock = threading.Lock()


def static_page(name):
    return send_from_directory(current_app.static_folder, name)


@bp.get('/')
def home():
    return static_page('home.html')


@bp.get('/c/<slug>')
def comp_page(slug):
    c = store.comp_by_slug(slug, include_inactive=bool(g.user))
    if not c:
        abort(404)
    # ใส่ชื่องานและโลโก้ลงในหน้า เพื่อให้ตัวอย่างลิงก์ใน LINE/Facebook แสดงถูกงาน
    with open(os.path.join(current_app.static_folder, 'index.html'), encoding='utf-8') as f:
        page = f.read()
    title = 'ยืนยันรายชื่อนักกีฬา' + (c['sport'] or '')
    desc = c['name'] + ' · โรงเรียนเลือกยืนยันหรือเปลี่ยนตัวนักกีฬาก่อนเวลาปิด'
    og = (f'<meta name="description" content="{escape(desc)}">\n'
          f'<meta property="og:title" content="{escape(title)}">\n'
          f'<meta property="og:description" content="{escape(desc)}">\n<meta property="og:type" content="website">')
    if c['logo']:
        og += f'\n<meta property="og:image" content="{escape(request.url_root.rstrip("/").replace("http://", "https://") if request.headers.get("X-Forwarded-Proto") == "https" else request.url_root.rstrip("/"))}/logo/{c["id"]}?v={escape(c["logo"])}">'
    page = page.replace('<title>ยืนยันรายชื่อนักกีฬา</title>', f'<title>{escape(title)}</title>', 1).replace('<!--og-->', og, 1)
    return Response(page, mimetype='text/html')


@bp.get('/logo/<int:cid>')
def logo(cid):
    r = get_db().execute('SELECT logo_mime, logo_data FROM competitions WHERE id=?', (cid,)).fetchone()
    if not r or not r['logo_data']:
        abort(404)
    resp = Response(bytes(r['logo_data']), mimetype=r['logo_mime'] or 'image/png')
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp


@bp.get('/api/competitions')
def competitions():
    rows = get_db().execute(f'SELECT {store.COMP_COLS} FROM competitions WHERE active=1 ORDER BY id DESC')
    return jsonify(competitions=[store.comp_public(dict(r)) for r in rows])


def _comp(slug):
    c = store.comp_by_slug(slug, include_inactive=bool(g.user))
    if not c:
        abort(404)
    return c


@bp.get('/api/c/<slug>/info')
def info(slug):
    c = _comp(slug)
    return jsonify(comp=store.comp_public(c), schools=store.schools(c['id']), events=store.load_events(c['id']),
                   staff=(g.user or {}).get('name') or (g.user or {}).get('username'))


@bp.post('/api/c/<slug>/school')
def school(slug):
    c = _comp(slug)
    s = (request.get_json(silent=True) or {}).get('school') or ''
    return jsonify(logic.school_view(store.load_entries(c['id'], s), store.load_events(c['id']),
                                     store.load_confs(c['id']), s, logic.now_bkk(), c['max_events']))


@bp.post('/api/c/<slug>/submit')
def submit(slug):
    c = _comp(slug)
    payload = request.get_json(silent=True) or {}
    staff = g.user['username'] if g.user else None
    school = payload.get('school') or ''
    with write_lock:
        conn = get_db()
        entries, events = store.load_entries(c['id'], school), store.load_events(c['id'])
        res = logic.apply_submit(entries, events, payload, logic.now_bkk(), staff, c['max_events'])
        if not res['ok']:
            return jsonify(res)
        with conn:
            for eid, nu in res['changes']:
                conn.execute('UPDATE entries SET prefix=?, first=?, last=?, status=?, by_name=?, phone=?, at=?, team=? '
                             'WHERE id=? AND comp_id=?',
                             (nu['prefix'], nu['first'], nu['last'], nu['status'], nu['by'], nu['phone'], nu['at'],
                              nu['team'], eid, c['id']))
            for nu in res['inserts']:
                conn.execute('INSERT INTO entries (comp_id, event, school, level, team, prefix, first, last, status, '
                             'by_name, phone, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                             (c['id'], payload['event'], school, next((e['level'] for e in events if e['event'] == payload['event']), ''),
                              nu['team'], nu['prefix'], nu['first'], nu['last'], nu['status'], nu['by'], nu['phone'], nu['at']))
            cf = res['conf']
            conn.execute('INSERT INTO confs (comp_id, school, event, by_name, phone, at, count) VALUES (?,?,?,?,?,?,?) '
                         'ON CONFLICT (comp_id, school, event) DO UPDATE SET by_name=excluded.by_name, '
                         'phone=excluded.phone, at=excluded.at, count=excluded.count',
                         (c['id'], cf['school'], cf['event'], cf['by'], cf['phone'], cf['at'], cf['count']))
            conn.executemany('INSERT INTO logs (comp_id, at, school, event, entry_id, action, before, after, by_name, phone, staff_user) '
                             'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                             [(c['id'], l['at'], l['school'], l['event'], l['entry_id'], l['action'], l['before'],
                               l['after'], l['by'], l['phone'], l['user']) for l in res['logs']])
    view = logic.school_view(store.load_entries(c['id'], school), store.load_events(c['id']),
                             store.load_confs(c['id']), school, logic.now_bkk(), c['max_events'])
    return jsonify(ok=True, conf=res['conf'], view=view)
