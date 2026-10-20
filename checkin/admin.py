"""หลังบ้านเจ้าหน้าที่: จัดการการแข่งขัน วันแข่ง ภาพรวม พิมพ์ ส่งออก"""
import io
import os
import re
import uuid

from flask import Blueprint, abort, current_app, g, jsonify, request, send_file

from . import logic, store
from .auth import err, login_required
from .db import get_db
from .importer import ImportError_, import_rows, read_excel

bp = Blueprint('admin', __name__)
LOGO_TYPES = {'.png': 'png', '.jpg': 'jpg', '.jpeg': 'jpg', '.webp': 'webp', '.gif': 'gif'}


@bp.get('/admin')
def admin_page():
    from flask import send_from_directory
    return send_from_directory(current_app.static_folder, 'admin.html')


def _comp_or_404(cid):
    c = store.comp_by_id(cid)
    if not c:
        abort(404)
    return c


def _comp_summary(c):
    conn = get_db()
    d = store.comp_public(c)
    d.update(
        entries=conn.execute('SELECT COUNT(*) FROM entries WHERE comp_id=?', (c['id'],)).fetchone()[0],
        schools=conn.execute('SELECT COUNT(DISTINCT school) FROM entries WHERE comp_id=?', (c['id'],)).fetchone()[0],
        events=conn.execute('SELECT COUNT(*) FROM events WHERE comp_id=?', (c['id'],)).fetchone()[0],
        confirmed=conn.execute('SELECT COUNT(*) FROM confs WHERE comp_id=?', (c['id'],)).fetchone()[0],
        undated=conn.execute("SELECT COUNT(*) FROM events WHERE comp_id=? AND deadline=''", (c['id'],)).fetchone()[0],
        created_at=c['created_at'])
    return d


def _save_logo(file, cid):
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in LOGO_TYPES:
        raise ValueError('โลโก้ต้องเป็นไฟล์ png, jpg, webp หรือ gif')
    data = file.read()
    if len(data) > 3 * 1024 * 1024:
        raise ValueError('ไฟล์โลโก้ใหญ่เกิน 3 MB')
    name = f'logo_{cid}_{uuid.uuid4().hex[:8]}{ext}'
    with open(os.path.join(current_app.config['UPLOAD_DIR'], name), 'wb') as f:
        f.write(data)
    return name


def _valid_slug(s):
    return re.fullmatch(r'[a-z0-9][a-z0-9-]{1,40}', s or '') is not None


# ---------- การแข่งขัน ----------
@bp.get('/api/admin/competitions')
@login_required()
def list_comps():
    rows = get_db().execute('SELECT * FROM competitions ORDER BY active DESC, id DESC')
    return jsonify(competitions=[_comp_summary(dict(r)) for r in rows], me=g.user)


@bp.post('/api/admin/competitions')
@login_required('admin')
def create_comp():
    f = request.form
    name, slug = (f.get('name') or '').strip(), (f.get('slug') or '').strip().lower()
    if not name:
        return err('กรุณากรอกชื่อการแข่งขัน')
    if not _valid_slug(slug):
        return err('รหัสลิงก์ต้องเป็นอังกฤษตัวเล็ก/ตัวเลข/ขีด 2–41 ตัว เช่น petong49')
    if 'file' not in request.files or not request.files['file'].filename:
        return err('กรุณาเลือกไฟล์ Excel รายชื่อนักกีฬา')
    try:
        max_events = max(0, int(f.get('max_events') or 3))
    except ValueError:
        return err('จำนวนรายการสูงสุดต่อคนต้องเป็นตัวเลข')
    conn = get_db()
    if conn.execute('SELECT 1 FROM competitions WHERE slug=?', (slug,)).fetchone():
        return err('รหัสลิงก์นี้ถูกใช้แล้ว')
    try:
        rows = read_excel(request.files['file'])
    except ImportError_ as e:
        return err(str(e))
    with conn:
        cur = conn.execute('INSERT INTO competitions (slug, name, sport, subtitle, max_events, created_at) '
                           'VALUES (?,?,?,?,?,?)',
                           (slug, name, (f.get('sport') or '').strip(), (f.get('subtitle') or '').strip(),
                            max_events, logic.stamp()))
        cid = cur.lastrowid
        result = import_rows(conn, cid, rows)
        if request.files.get('logo') and request.files['logo'].filename:
            try:
                conn.execute('UPDATE competitions SET logo=? WHERE id=?', (_save_logo(request.files['logo'], cid), cid))
            except ValueError as e:
                conn.rollback()
                return err(str(e))
    return jsonify(ok=True, id=cid, imported=result)


@bp.get('/api/admin/competitions/<int:cid>')
@login_required()
def get_comp(cid):
    c = _comp_or_404(cid)
    return jsonify(comp=_comp_summary(c), events=store.load_events(cid), schools=store.schools(cid), me=g.user)


@bp.post('/api/admin/competitions/<int:cid>')
@login_required('admin')
def update_comp(cid):
    c = _comp_or_404(cid)
    f = request.form if request.form else (request.get_json(silent=True) or {})
    slug = (f.get('slug') or c['slug']).strip().lower()
    if not _valid_slug(slug):
        return err('รหัสลิงก์ไม่ถูกต้อง')
    conn = get_db()
    if conn.execute('SELECT 1 FROM competitions WHERE slug=? AND id<>?', (slug, cid)).fetchone():
        return err('รหัสลิงก์นี้ถูกใช้แล้ว')
    try:
        max_events = max(0, int(f.get('max_events', c['max_events'])))
    except ValueError:
        return err('จำนวนรายการสูงสุดต่อคนต้องเป็นตัวเลข')
    active = str(f.get('active', c['active'])).lower() in ('1', 'true', 'on')
    logo = c['logo']
    if request.files.get('logo') and request.files['logo'].filename:
        try:
            logo = _save_logo(request.files['logo'], cid)
        except ValueError as e:
            return err(str(e))
    with conn:
        conn.execute('UPDATE competitions SET slug=?, name=?, sport=?, subtitle=?, max_events=?, active=?, logo=? WHERE id=?',
                     (slug, (f.get('name') or c['name']).strip(), (f.get('sport', c['sport']) or '').strip(),
                      (f.get('subtitle', c['subtitle']) or '').strip(), max_events, int(active), logo, cid))
    return jsonify(ok=True)


@bp.post('/api/admin/competitions/<int:cid>/delete')
@login_required('admin')
def delete_comp(cid):
    c = _comp_or_404(cid)
    if ((request.get_json(silent=True) or {}).get('confirm') or '').strip().lower() != c['slug']:
        return err(f"พิมพ์รหัสลิงก์ \"{c['slug']}\" ให้ตรงเพื่อยืนยันการลบ")
    conn = get_db()
    with conn:
        for t in ('logs', 'confs', 'entries', 'events'):
            conn.execute(f'DELETE FROM {t} WHERE comp_id=?', (cid,))
        conn.execute('DELETE FROM competitions WHERE id=?', (cid,))
    if c['logo']:
        try:
            os.remove(os.path.join(current_app.config['UPLOAD_DIR'], c['logo']))
        except OSError:
            pass
    return jsonify(ok=True)


@bp.post('/api/admin/competitions/<int:cid>/import')
@login_required('admin')
def reimport(cid):
    _comp_or_404(cid)
    conn = get_db()
    confirmed = conn.execute('SELECT COUNT(*) FROM confs WHERE comp_id=?', (cid,)).fetchone()[0]
    if confirmed and request.form.get('confirm') != 'yes':
        return err(f'มีการยืนยันไปแล้ว {confirmed} รายการ การนำเข้าใหม่จะลบการยืนยันทั้งหมด', 409)
    if 'file' not in request.files or not request.files['file'].filename:
        return err('กรุณาเลือกไฟล์ Excel')
    try:
        rows = read_excel(request.files['file'])
    except ImportError_ as e:
        return err(str(e))
    with conn:
        result = import_rows(conn, cid, rows)
        conn.execute('INSERT INTO logs (comp_id, at, action, after, user) VALUES (?,?,?,?,?)',
                     (cid, logic.stamp(), 'นำเข้ารายชื่อใหม่', f"{result['entries']} รายชื่อ", g.user['username']))
    return jsonify(ok=True, imported=result)


@bp.post('/api/admin/competitions/<int:cid>/events')
@login_required('admin')
def update_events(cid):
    _comp_or_404(cid)
    items = (request.get_json(silent=True) or {}).get('events') or []
    errors = []
    for it in items:
        if it.get('deadline') and not logic.parse_deadline(it['deadline']):
            errors.append(f"เวลาปิดยืนยันไม่ถูกต้อง: {it.get('short') or it.get('id')}")
        if it.get('startDate') and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', it['startDate']):
            errors.append(f"วันแข่งไม่ถูกต้อง: {it.get('short') or it.get('id')}")
    if errors:
        return err(' · '.join(errors))
    conn = get_db()
    with conn:
        for it in items:
            conn.execute('UPDATE events SET short=?, start_date=?, start_time=?, deadline=? WHERE id=? AND comp_id=?',
                         ((it.get('short') or '').strip(), it.get('startDate') or '', (it.get('startTime') or '').strip(),
                          (it.get('deadline') or '').replace('T', ' ')[:16], int(it['id']), cid))
    return jsonify(ok=True, events=store.load_events(cid))


@bp.get('/api/admin/competitions/<int:cid>/overview')
@login_required()
def overview(cid):
    c = _comp_or_404(cid)
    entries, events, confs = store.load_all(cid)
    return jsonify(logic.overview(entries, events, confs, logic.now_bkk(), c['max_events']))


@bp.post('/api/admin/competitions/<int:cid>/print')
@login_required()
def print_data(cid):
    _comp_or_404(cid)
    entries, events, confs = store.load_all(cid)
    return jsonify(logic.print_data(entries, events, confs, request.get_json(silent=True) or {}))


@bp.get('/api/admin/competitions/<int:cid>/logs')
@login_required()
def logs(cid):
    _comp_or_404(cid)
    rows = get_db().execute('SELECT * FROM logs WHERE comp_id=? ORDER BY id DESC LIMIT 300', (cid,))
    return jsonify(logs=[dict(r) for r in rows])


@bp.get('/api/admin/competitions/<int:cid>/export')
@login_required()
def export_excel(cid):
    from openpyxl import Workbook
    c = _comp_or_404(cid)
    entries, events, confs = store.load_all(cid)
    em = {e['event']: e for e in events}
    wb = Workbook()
    ws = wb.active
    ws.title = 'รายชื่อนักกีฬา'
    ws.append(['รายการแข่งขัน', 'โรงเรียน', 'คำนำหน้า', 'ชื่อ', 'นามสกุล', 'ระดับชั้น', 'คู่ที่/ทีมที่/มือวาง', 'สถานะ',
               'ผู้ยืนยัน/แก้ไข', 'เบอร์โทร', 'เวลาที่บันทึก', 'ชื่อเดิม', 'วันแข่ง'])
    for e in entries:
        ws.append([e['event'], e['school'], e['prefix'], e['first'], e['last'], e['level'],
                   int(e['team']) if str(e['team']).isdigit() else e['team'], e['status'], e['by'], e['phone'], e['at'],
                   f"{e['oPrefix']}{e['oFirst']} {e['oLast']}", em.get(e['event'], {}).get('startDate', '')])
    ws2 = wb.create_sheet('การยืนยัน')
    ws2.append(['โรงเรียน', 'รายการแข่งขัน', 'ผู้ยืนยัน', 'เบอร์โทร', 'เวลายืนยัน', 'จำนวนนักกีฬา'])
    for x in confs:
        ws2.append([x['school'], x['event'], x['by'], x['phone'], x['at'], x['count']])
    ws3 = wb.create_sheet('ประวัติการแก้ไข')
    ws3.append(['เวลา', 'โรงเรียน', 'รายการแข่งขัน', 'การกระทำ', 'ก่อน', 'หลัง', 'ผู้แก้ไข', 'เบอร์โทร', 'บัญชีเจ้าหน้าที่'])
    for r in get_db().execute('SELECT at, school, event, action, before, after, by, phone, user FROM logs '
                              'WHERE comp_id=? ORDER BY id', (cid,)):
        ws3.append(list(r))
    for sh in wb.worksheets:
        sh.freeze_panes = 'A2'
        for col in sh.columns:
            sh.column_dimensions[col[0].column_letter].width = min(max(len(str(x.value or '')) for x in col) + 2, 60)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"{c['slug']}_{logic.now_bkk():%Y%m%d_%H%M}.xlsx",
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
