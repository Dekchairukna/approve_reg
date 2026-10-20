"""ตรรกะการยืนยันรายชื่อ: ไม่ยุ่งกับเว็บ ทดสอบแยกได้"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Bangkok')
PENDING, OK, OUT = 'รอยืนยัน', 'ยืนยัน', 'ถอนตัว'
SINGLE_CATEGORIES = ('เดี่ยว', 'Shooting', 'บุคคล')
UNSPECIFIED_TEAM = '999'   # โรงเรียนไม่ได้ระบุคู่ที่/ทีมที่ (หรือเป็นประเภทบุคคล)


def now_bkk():
    return datetime.now(TZ)


def stamp():
    return now_bkk().strftime('%Y-%m-%d %H:%M:%S')


def norm(s):
    return re.sub(r'\s+', '', str(s or ''))


def clean(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def pkey(school, first, last):
    return norm(school) + '|' + norm(first) + norm(last)


def parse_deadline(s):
    s = (s or '').strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=TZ)
        except ValueError:
            pass
    return None


def is_closed(ev, now):
    d = parse_deadline(ev.get('deadline'))
    return d is not None and now > d


def team_label(team, category):
    if str(team) == UNSPECIFIED_TEAM or not str(team).strip():
        if category in SINGLE_CATEGORIES:
            return 'บุคคล'
        return 'ไม่ระบุทีม' if 'ทีม' in category else 'ไม่ระบุคู่'
    return ('ทีมที่ ' if 'ทีม' in category else 'คู่ที่ ') + str(team)


def countable(e):
    return e['status'] == OK


def schools_of(entries):
    return sorted({e['school'] for e in entries})


def team_sort(e):
    t = str(e['team'])
    return (int(t) if t.isdigit() else 99999, e['id'])


def school_view(entries, events, confs, school, now, max_events):
    cm = {(c['school'], c['event']): c for c in confs}
    by_event = {}
    for e in entries:
        if e['school'] == school:
            by_event.setdefault(e['event'], []).append(e)
    out = []
    for ev in events:
        rows = by_event.get(ev['event'])
        if not rows:
            continue
        out.append(dict(
            event=ev['event'], short=ev['short'], level=ev['level'], category=ev['category'],
            startDate=ev['startDate'], startTime=ev['startTime'], deadline=ev['deadline'],
            closed=is_closed(ev, now), confirmation=cm.get((school, ev['event'])),
            entries=[dict(id=e['id'], team=e['team'], teamLabel=team_label(e['team'], ev['category']),
                          prefix=e['prefix'], first=e['first'], last=e['last'], oPrefix=e['oPrefix'],
                          oFirst=e['oFirst'], oLast=e['oLast'], status=e['status'], by=e['by'], at=e['at'])
                     for e in sorted(rows, key=team_sort)]))
    return dict(school=school, max=max_events, events=out)


def apply_submit(entries, events, payload, now, staff, max_events):
    """ตรวจข้อมูลที่ส่งมา คืน changes/logs/conf ถ้าผ่าน หรือ errors ถ้าไม่ผ่าน
    staff = ชื่อผู้ใช้เจ้าหน้าที่ (แก้ได้แม้เลยเวลาปิด) หรือ None"""
    em = {e['event']: e for e in events}
    ev = em.get(payload.get('event'))
    if not ev:
        return dict(ok=False, errors=['ไม่พบรายการแข่งขันนี้'])
    school = payload.get('school')
    by = clean(payload.get('by'))
    phone = re.sub(r'\D', '', str(payload.get('phone') or ''))
    errors = []
    if not by:
        errors.append('กรุณากรอกชื่อผู้ยืนยัน/แก้ไข')
    if not re.fullmatch(r'0\d{8,9}', phone):
        errors.append('เบอร์โทรต้องเป็นตัวเลข 9–10 หลัก ขึ้นต้นด้วย 0')
    if not staff and is_closed(ev, now):
        errors.append(f"ปิดรับยืนยันรายการนี้แล้ว ({ev['deadline']} น.) ติดต่อเจ้าหน้าที่")

    mine = [e for e in entries if e['school'] == school and e['event'] == ev['event']]
    if not mine:
        errors.append('ไม่พบรายชื่อของโรงเรียนในรายการนี้')
    try:
        items = {int(it['id']): it for it in payload.get('items') or []}
    except (KeyError, TypeError, ValueError):
        return dict(ok=False, errors=['ข้อมูลไม่ถูกต้อง กรุณาโหลดหน้าใหม่'])
    seen, changes, logs, ts = set(), [], [], stamp()

    for e in mine:
        it = items.get(e['id'])
        if it is None:
            errors.append('ข้อมูลไม่ครบ กรุณาโหลดหน้าใหม่')
            continue
        out = bool(it.get('withdrawn'))
        p, f, l = clean(it.get('prefix'))[:20], clean(it.get('first'))[:80], clean(it.get('last'))[:80]
        if not out:
            if not f or not l:
                errors.append(f"กรุณากรอกชื่อ-นามสกุลให้ครบ ({team_label(e['team'], ev['category'])})")
                continue
            k = pkey(school, f, l)
            if k in seen:
                errors.append(f'{p}{f} {l} มีชื่อซ้ำในรายการนี้')
            seen.add(k)
            other = [x for x in entries if x['event'] != e['event'] and countable(x)
                     and pkey(x['school'], x['first'], x['last']) == k]
            if max_events and len(other) + 1 > max_events:
                names = ', '.join(em.get(x['event'], {}).get('short', x['event']) for x in other)
                errors.append(f'{p}{f} {l} ยืนยันไปแล้ว {len(other)} รายการ ({names}) '
                              f'ยืนยันได้สูงสุด {max_events} รายการต่อคน')
        nu = dict(prefix=e['prefix'] if out else p, first=e['first'] if out else f,
                  last=e['last'] if out else l, status=OUT if out else OK, by=by[:120], phone=phone, at=ts)
        name_changed = (nu['prefix'], nu['first'], nu['last']) != (e['prefix'], e['first'], e['last'])
        if name_changed or nu['status'] != e['status']:
            logs.append(dict(at=ts, school=school, event=e['event'], entry_id=e['id'],
                             action='ถอนตัว' if out else ('แก้ไขชื่อ' if name_changed else 'ยืนยัน'),
                             before=f"{e['prefix']}{e['first']} {e['last']} [{e['status']}]",
                             after=f"{nu['prefix']}{nu['first']} {nu['last']} [{nu['status']}]",
                             by=nu['by'], phone=phone, user=staff or ''))
        changes.append((e['id'], nu))

    errors = list(dict.fromkeys(errors))
    if errors:
        return dict(ok=False, errors=errors)
    count = sum(1 for _, nu in changes if nu['status'] == OK)
    conf = dict(school=school, event=ev['event'], by=by[:120], phone=phone, at=ts, count=count)
    return dict(ok=True, changes=changes, logs=logs, conf=conf)


def overview(entries, events, confs, now, max_events):
    cm = {(c['school'], c['event']): c for c in confs}
    em = {e['event']: e for e in events}
    pairs = {(e['school'], e['event']) for e in entries}
    ss = schools_of(entries)
    by_school = []
    for s in ss:
        evs = [ev for ev in events if (s, ev['event']) in pairs]
        done = [ev for ev in evs if (s, ev['event']) in cm]
        people = {pkey(s, e['first'], e['last']) for e in entries if e['school'] == s and e['status'] == OK}
        last = max([cm[(s, ev['event'])]['at'] for ev in done], default='')
        by_school.append(dict(school=s, total=len(evs), done=len(done), athletes=len(people), last=last, events=[
            dict(event=ev['event'], short=ev['short'], level=ev['level'], done=(s, ev['event']) in cm,
                 by=(cm.get((s, ev['event'])) or {}).get('by', ''),
                 phone=(cm.get((s, ev['event'])) or {}).get('phone', ''))
            for ev in evs]))
    cats = {}
    for ev in events:
        k = (ev['startDate'], ev['category'])
        c = cats.setdefault(k, dict(category=ev['category'], startDate=ev['startDate'], deadline=ev['deadline'],
                                    closed=is_closed(ev, now), total=0, done=0))
        for s in ss:
            if (s, ev['event']) in pairs:
                c['total'] += 1
                c['done'] += (s, ev['event']) in cm
    pc = {}
    for e in entries:
        if countable(e):
            k = pkey(e['school'], e['first'], e['last'])
            pc.setdefault(k, dict(name=f"{e['prefix']}{e['first']} {e['last']}", school=e['school'], events=[]))[
                'events'].append(em.get(e['event'], {}).get('short', e['event']))
    return dict(
        schools=by_school,
        categories=sorted(cats.values(), key=lambda c: c['startDate'] or '9999'),   # คงลำดับประเภทตามรายการ
        totals=dict(athletesConfirmed=len(pc),
                    entriesConfirmed=sum(e['status'] == OK for e in entries),
                    entriesWithdrawn=sum(e['status'] == OUT for e in entries),
                    entriesTotal=len(entries),
                    pairsTotal=len(pairs), pairsDone=sum(1 for p in pairs if p in cm)),
        over=[p for p in pc.values() if max_events and len(p['events']) > max_events])


def print_data(entries, events, confs, f):
    cm = {(c['school'], c['event']): c for c in confs}
    evs = [ev for ev in events if (not f.get('startDate') or ev['startDate'] == f['startDate'])
           and (not f.get('level') or ev['level'] == f['level'])]
    pages, skipped = [], []
    for s in schools_of(entries):
        if f.get('school') and s != f['school']:
            continue
        blocks = []
        for ev in evs:
            rows = [e for e in entries if e['school'] == s and e['event'] == ev['event']]
            if not rows:
                continue
            c = cm.get((s, ev['event']))
            if not c:
                skipped.append(dict(school=s, short=ev['short'], level=ev['level']))
                continue
            ok = [dict(teamLabel=team_label(e['team'], ev['category']), name=f"{e['prefix']}{e['first']} {e['last']}")
                  for e in sorted(rows, key=team_sort) if e['status'] == OK]
            blocks.append(dict(event=ev['event'], short=ev['short'], level=ev['level'], category=ev['category'],
                               startDate=ev['startDate'], startTime=ev['startTime'], conf=c, rows=ok))
        if blocks:
            pages.append(dict(school=s, blocks=blocks))
    return dict(pages=pages, skipped=skipped)
