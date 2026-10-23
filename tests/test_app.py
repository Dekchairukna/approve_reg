"""ทดสอบระบบด้วยข้อมูลสมมติ:  python3 -m pytest -q

ทดสอบกับ PostgreSQL ด้วย:  TEST_DATABASE_URL=postgresql://... python3 -m pytest -q
(ฐานข้อมูลนั้นจะถูกล้างทุกครั้ง ห้ามใช้ฐานข้อมูลจริง)
"""
import io
import os

import pytest
from openpyxl import Workbook

from checkin import create_app

H = {'X-Requested-With': 'checkin'}
HEADER = ['รายการแข่งขัน/ประเภทกีฬา', 'โรงเรียนที่เข้าร่วมการแข่งขัน', 'คำนำหน้า', 'ชื่อ', 'นามสกุล', 'ระดับชั้น', 'คู่ที่/ทีมที่/มือวาง']
ROWS = [
    ['เปตอง : เดี่ยว ประถมศึกษา บุคคล ชาย', 'โรงเรียนเอ', 'ด.ช.', 'หนึ่ง', 'ทดสอบ', 'ประถมศึกษา', 999],
    ['เปตอง : ประถมศึกษา Shooting 1 คน ชาย', 'โรงเรียนเอ', 'ด.ช.', 'หนึ่ง', 'ทดสอบ', 'ประถมศึกษา', 999],
    ['เปตอง : ประถมศึกษา คู่ ชาย', 'โรงเรียนเอ', 'ด.ช.', 'หนึ่ง', 'ทดสอบ', 'ประถมศึกษา', 1],
    ['เปตอง : ประถมศึกษา คู่ ชาย', 'โรงเรียนเอ', 'ด.ช.', 'สอง', 'ทดสอบ', 'ประถมศึกษา', 1],
    ['เปตอง : ประถมศึกษา ทีม 3 คน ชาย', 'โรงเรียนเอ', 'ด.ช.', 'หนึ่ง', 'ทดสอบ', 'ประถมศึกษา', 999],
    ['เปตอง : ประถมศึกษา ทีม 3 คน ชาย', 'โรงเรียนเอ', 'ด.ช.', 'สาม', 'ทดสอบ', 'ประถมศึกษา', 999],
    ['เปตอง : ประถมศึกษา ทีม 3 คน ชาย', 'โรงเรียนบี', 'ด.ช.', 'สี่', 'ทดสอบ', 'ประถมศึกษา', 1],
    ['เปตอง : เดี่ยว ประถมศึกษา บุคคล หญิง', 'โรงเรียนเอ', 'ด.ญ.', 'ใจดี', 'ทดสอบ', 'ประถมศึกษา', 999],
    ['เปตอง : เดี่ยว ประถมศึกษา บุคคล ชาย', 'โรงเรียนเอ', 'ด.ช.', 'ขยัน', 'ทดสอบ', 'ประถมศึกษา', 999],
]


def xlsx():
    wb = Workbook()
    ws = wb.active
    ws.append(HEADER)
    for r in ROWS:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    b.seek(0)
    return b


@pytest.fixture
def client(tmp_path, monkeypatch):
    pg = os.environ.get('TEST_DATABASE_URL')
    if pg:
        from checkin.db import DB, TABLES, init_db
        monkeypatch.setenv('DATABASE_URL', pg)
        init_db(pg)
        db = DB(pg)
        db.execute('TRUNCATE ' + ', '.join(TABLES) + ' RESTART IDENTITY CASCADE')
        db.close()
    else:
        monkeypatch.delenv('DATABASE_URL', raising=False)
    app = create_app(str(tmp_path))
    app.config['TESTING'] = True
    return app.test_client()


def setup_comp(c):
    assert c.post('/api/auth/setup', json={'username': 'admin', 'password': 'password123', 'name': 'แอดมิน'}, headers=H).status_code == 200
    r = c.post('/api/admin/competitions', headers=H, content_type='multipart/form-data',
               data={'name': 'งานทดสอบ', 'sport': 'เปตอง', 'slug': 'test', 'max_events': '3', 'file': (xlsx(), 'a.xlsx')})
    assert r.status_code == 200, r.json
    assert r.json['imported'] == {'entries': 9, 'events': 5, 'schools': 2}
    return r.json['id']


def submit(c, event_name, school='โรงเรียนเอ', swap=None):
    """swap = {'ชื่อเดิม': 'ชื่อใหม่'} เปลี่ยนตัวนักกีฬา"""
    swap = swap or {}
    v = c.post('/api/c/test/school', json={'school': school}, headers=H).json
    ev = next(e for e in v['events'] if e['event'] == event_name)
    items = [dict(id=x['id'], prefix=x['prefix'], first=swap.get(x['first'], x['first']), last=x['last']) for x in ev['entries']]
    return c.post('/api/c/test/submit', headers=H, json={'school': school, 'event': event_name, 'by': 'ครู', 'phone': '0812345678', 'items': items}).json


def test_csrf_header_required(client):
    assert client.post('/api/auth/login', json={}).status_code == 400


def test_setup_only_once(client):
    setup_comp(client)
    assert client.post('/api/auth/setup', json={'username': 'x2', 'password': 'password123'}, headers=H).status_code == 403


def test_max_three_events_and_swap(client):
    setup_comp(client)
    client.post('/api/auth/logout', headers=H)          # โรงเรียนไม่ต้องล็อกอิน
    for name in ['เปตอง : เดี่ยว ประถมศึกษา บุคคล ชาย', 'เปตอง : ประถมศึกษา Shooting 1 คน ชาย', 'เปตอง : ประถมศึกษา คู่ ชาย']:
        assert submit(client, name)['ok']
    r = submit(client, 'เปตอง : ประถมศึกษา ทีม 3 คน ชาย')
    assert not r['ok'] and 'ยืนยันได้สูงสุด 3 รายการ' in r['errors'][0]
    assert submit(client, 'เปตอง : ประถมศึกษา ทีม 3 คน ชาย', swap={'หนึ่ง': 'สอง'})['ok']   # เปลี่ยนตัว


def test_roster_dropdown_and_validation(client):
    setup_comp(client)
    v = client.post('/api/c/test/school', json={'school': 'โรงเรียนเอ'}, headers=H).json
    team = next(e for e in v['events'] if e['short'] == 'ทีม 3 คน ชาย')
    assert sorted(p['first'] for p in team['pool']) == ['ขยัน', 'สอง', 'สาม', 'หนึ่ง']  # ชายประถมของโรงเรียนเอ
    assert all(p['first'] != 'ใจดี' for p in team['pool'])                            # หญิงไม่อยู่ในรุ่นชาย
    r = submit(client, 'เปตอง : ประถมศึกษา ทีม 3 คน ชาย', swap={'หนึ่ง': 'คนนอก'})
    assert not r['ok'] and 'ไม่อยู่ในรายชื่อ' in r['errors'][0]
    r = submit(client, 'เปตอง : ประถมศึกษา ทีม 3 คน ชาย', swap={'หนึ่ง': 'สาม'})
    assert not r['ok'] and 'ชื่อซ้ำ' in r['errors'][0]


def test_labels_for_unspecified_team(client):
    setup_comp(client)
    v = client.post('/api/c/test/school', json={'school': 'โรงเรียนเอ'}, headers=H).json
    labels = {e['short']: e['entries'][0]['teamLabel'] for e in v['events']}
    assert labels['เดี่ยวชาย'] == 'บุคคล'
    assert labels['ทีม 3 คน ชาย'] == 'ไม่ระบุทีม'
    assert labels['คู่ชาย'] == 'คู่ที่ 1'


def test_deadline_blocks_public_but_not_staff(client):
    cid = setup_comp(client)
    evs = client.get(f'/api/admin/competitions/{cid}', headers=H).json['events']
    client.post(f'/api/admin/competitions/{cid}/events', headers=H, json={'events': [
        dict(id=e['id'], short=e['short'], startDate='2020-01-02', startTime='08.30', deadline='2020-01-01 18:00') for e in evs]})
    assert submit(client, 'เปตอง : ประถมศึกษา คู่ ชาย')['ok']          # เจ้าหน้าที่ยังแก้ได้
    client.post('/api/auth/logout', headers=H)
    r = submit(client, 'เปตอง : ประถมศึกษา คู่ ชาย')
    assert not r['ok'] and 'ปิดรับยืนยัน' in r['errors'][0]


def test_admin_routes_need_login_and_role(client):
    cid = setup_comp(client)
    client.post('/api/admin/users', headers=H, json={'username': 'staff1', 'password': 'password123', 'role': 'staff'})
    client.post('/api/auth/logout', headers=H)
    assert client.get(f'/api/admin/competitions/{cid}/overview').status_code == 401
    assert client.post('/api/auth/login', headers=H, json={'username': 'staff1', 'password': 'password123'}).status_code == 200
    assert client.get(f'/api/admin/competitions/{cid}/overview').status_code == 200
    assert client.get(f'/api/admin/competitions/{cid}/export').status_code == 200
    assert client.get('/api/admin/users').status_code == 403
    assert client.post(f'/api/admin/competitions/{cid}', headers=H, json={'name': 'x'}).status_code == 403


def test_print_only_confirmed(client):
    cid = setup_comp(client)
    submit(client, 'เปตอง : ประถมศึกษา คู่ ชาย')
    d = client.post(f'/api/admin/competitions/{cid}/print', headers=H, json={}).json
    assert len(d['pages']) == 1 and d['pages'][0]['blocks'][0]['rows'][0]['name'] == 'ด.ช.หนึ่ง ทดสอบ'
    assert len(d['skipped']) == 5


def test_delete_competition_and_user(client):
    cid = setup_comp(client)
    assert client.post(f'/api/admin/competitions/{cid}/delete', headers=H, json={'confirm': 'wrong'}).status_code == 400
    assert client.post(f'/api/admin/competitions/{cid}/delete', headers=H, json={'confirm': 'test'}).json['ok']
    assert client.get('/api/c/test/info').status_code == 404
    client.post('/api/admin/users', headers=H, json={'username': 'staff1', 'password': 'password123', 'role': 'staff'})
    users = client.get('/api/admin/users').json['users']
    me = next(u for u in users if u['username'] == 'admin')
    other = next(u for u in users if u['username'] == 'staff1')
    assert client.post(f"/api/admin/users/{me['id']}/delete", headers=H).status_code == 400
    assert client.post(f"/api/admin/users/{other['id']}/delete", headers=H).json['ok']


def test_backup_and_restore_on_fresh_install(client, tmp_path):
    cid = setup_comp(client)
    submit(client, 'เปตอง : ประถมศึกษา คู่ ชาย')
    data = client.get('/api/admin/backup').data
    assert data.startswith(b'SQLite format 3')
    # ระบบใหม่เปล่า ๆ: กู้คืนจากไฟล์ได้โดยไม่ต้องล็อกอิน
    from checkin import create_app
    fresh = create_app(str(tmp_path / 'fresh')).test_client()
    r = fresh.post('/api/auth/restore', headers=H, content_type='multipart/form-data', data={'file': (io.BytesIO(data), 'checkin.db')})
    assert r.status_code == 200 and r.json['counts']['entries'] == 9 and r.json['counts']['confs'] == 1
    assert fresh.post('/api/auth/login', headers=H, json={'username': 'admin', 'password': 'password123'}).status_code == 200
    assert fresh.get(f'/api/admin/competitions/{cid}/overview').json['totals']['pairsDone'] == 1
    # มีผู้ใช้แล้ว ห้ามกู้คืนแบบไม่ล็อกอิน
    fresh.post('/api/auth/logout', headers=H)
    r = fresh.post('/api/auth/restore', headers=H, content_type='multipart/form-data', data={'file': (io.BytesIO(data), 'checkin.db')})
    assert r.status_code == 403


def test_choose_team_number(client):
    cid = setup_comp(client)
    v = client.post('/api/c/test/school', json={'school': 'โรงเรียนเอ'}, headers=H).json
    ev = next(e for e in v['events'] if e['short'] == 'เดี่ยวชาย')
    items = [dict(id=x['id'], team=str(i + 1), prefix=x['prefix'], first=x['first'], last=x['last']) for i, x in enumerate(ev['entries'])]
    r = client.post('/api/c/test/submit', headers=H, json={'school': 'โรงเรียนเอ', 'event': ev['event'], 'by': 'ครู', 'phone': '0812345678', 'items': items}).json
    assert r['ok']
    labels = [x['teamLabel'] for x in next(e for e in r['view']['events'] if e['short'] == 'เดี่ยวชาย')['entries']]
    assert labels == ['ทีมที่ 1', 'ทีมที่ 2']
    items[0]['team'] = '5'
    r = client.post('/api/c/test/submit', headers=H, json={'school': 'โรงเรียนเอ', 'event': ev['event'], 'by': 'ครู', 'phone': '0812345678', 'items': items}).json
    assert not r['ok']
    d = client.post(f'/api/admin/competitions/{cid}/print', headers=H, json={}).json
    assert [row['teamLabel'] for row in d['pages'][0]['blocks'][0]['rows']] == ['ทีมที่ 1', 'ทีมที่ 2']


def test_not_sending_athlete(client):
    cid = setup_comp(client)
    v = client.post('/api/c/test/school', json={'school': 'โรงเรียนเอ'}, headers=H).json
    ev = next(e for e in v['events'] if e['short'] == 'คู่ชาย')
    items = [dict(id=x['id'], team='1', prefix=x['prefix'], first=x['first'], last=x['last'], withdrawn=(i == 1))
             for i, x in enumerate(ev['entries'])]
    r = client.post('/api/c/test/submit', headers=H, json={'school': 'โรงเรียนเอ', 'event': ev['event'], 'by': 'ครู', 'phone': '0812345678', 'items': items}).json
    assert r['ok'] and r['conf']['count'] == 1
    d = client.post(f'/api/admin/competitions/{cid}/print', headers=H, json={}).json
    assert len(d['pages'][0]['blocks'][0]['rows']) == 1
    assert client.get(f'/api/admin/competitions/{cid}/overview').json['totals']['entriesWithdrawn'] == 1


def test_team_slots_add_new_athlete(client):
    cid = setup_comp(client)
    v = client.post('/api/c/test/school', json={'school': 'โรงเรียนเอ'}, headers=H).json
    ev = next(e for e in v['events'] if e['short'] == 'คู่ชาย')
    assert ev['size'] == 3
    items = [dict(id=x['id'], team='1', prefix=x['prefix'], first=x['first'], last=x['last']) for x in ev['entries']]
    items.append(dict(id=None, team='1', prefix='ด.ช.', first='ขยัน', last='ทดสอบ'))          # สำรองคนที่ 3 จากรายชื่อรุ่นเดียวกัน
    items.append(dict(id=None, team='2', prefix='', first='', last='', withdrawn=True))       # ช่องว่าง: ไม่บันทึก
    body = {'school': 'โรงเรียนเอ', 'event': ev['event'], 'by': 'ครู', 'phone': '0812345678', 'items': items}
    r = client.post('/api/c/test/submit', headers=H, json=body).json
    assert r['ok'] and r['conf']['count'] == 3
    ev2 = next(e for e in r['view']['events'] if e['short'] == 'คู่ชาย')
    assert len(ev2['entries']) == 3
    # เกิน 3 คนในคู่เดียวไม่ได้
    items2 = [dict(id=x['id'], team='1', prefix=x['prefix'], first=x['first'], last=x['last']) for x in ev2['entries']]
    items2.append(dict(id=None, team='1', prefix='ด.ช.', first='สาม', last='ทดสอบ'))
    body['items'] = items2
    r = client.post('/api/c/test/submit', headers=H, json=body).json
    assert not r['ok'] and 'ไม่เกิน 3 คน' in ' '.join(r['errors'])
    d = client.post(f'/api/admin/competitions/{cid}/print', headers=H, json={}).json
    assert len(d['pages'][0]['blocks'][0]['rows']) == 3
