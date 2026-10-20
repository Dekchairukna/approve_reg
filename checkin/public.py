"""หน้าสาธารณะ: โรงเรียนยืนยันรายชื่อโดยไม่ต้องล็อกอิน"""
import threading

from flask import Blueprint, abort, current_app, g, jsonify, request, send_from_directory

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
    if not store.comp_by_slug(slug, include_inactive=bool(g.user)):
        abort(404)
    return static_page('index.html')


@bp.get('/logo/<int:cid>')
def logo(cid):
    c = store.comp_by_id(cid)
    if not c or not c['logo']:
        abort(404)
    return send_from_directory(current_app.config['UPLOAD_DIR'], c['logo'], max_age=86400)


@bp.get('/api/competitions')
def competitions():
    rows = get_db().execute('SELECT * FROM competitions WHERE active=1 ORDER BY id DESC')
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
                conn.execute('UPDATE entries SET prefix=?, first=?, last=?, status=?, by=?, phone=?, at=? '
                             'WHERE id=? AND comp_id=?',
                             (nu['prefix'], nu['first'], nu['last'], nu['status'], nu['by'], nu['phone'], nu['at'],
                              eid, c['id']))
            cf = res['conf']
            conn.execute('INSERT OR REPLACE INTO confs (comp_id, school, event, by, phone, at, count) '
                         'VALUES (?,?,?,?,?,?,?)',
                         (c['id'], cf['school'], cf['event'], cf['by'], cf['phone'], cf['at'], cf['count']))
            conn.executemany('INSERT INTO logs (comp_id, at, school, event, entry_id, action, before, after, by, phone, user) '
                             'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                             [(c['id'], l['at'], l['school'], l['event'], l['entry_id'], l['action'], l['before'],
                               l['after'], l['by'], l['phone'], l['user']) for l in res['logs']])
    view = logic.school_view(store.load_entries(c['id'], school), store.load_events(c['id']),
                             store.load_confs(c['id']), school, logic.now_bkk(), c['max_events'])
    return jsonify(ok=True, conf=res['conf'], view=view)
