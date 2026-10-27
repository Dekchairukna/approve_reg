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
    # ตัดช่องว่างและอักขระล่องหน (zero-width) ที่ติดมากับการคัดลอกชื่อ
    return re.sub(r'[\s\u200b\u200c\u200d\ufeff]+', '', str(s or ''))


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
    return ('คู่ที่ ' if 'คู่' in category else 'ทีมที่ ') + str(team)


def countable(e):
    return e['status'] == OK


def schools_of(entries):
    return sorted({e['school'] for e in entries})


def team_sort(e):
    t = str(e['team'])
    return (int(t) if t.isdigit() else 99999, e['id'])


MALE_PREFIXES = ('ด.ช.', 'นาย')
FEMALE_PREFIXES = ('ด.ญ.', 'น.ส.', 'นาง', 'นางสาว')


def gender_of_prefix(prefix):
    p = norm(prefix)
    if p in MALE_PREFIXES:
        return 'M'
    if p in FEMALE_PREFIXES:
        return 'F'
    return ''


def gender_of_event(name):
    if 'ผสม' in name:
        return ''
    if 'หญิง' in name:
        return 'F'
    if 'ชาย' in name:
        return 'M'
    return ''


def roster(entries, ev):
    """นักกีฬาที่โรงเรียนสมัครไว้ในรุ่นเดียวกับรายการนี้ (ระดับชั้นเดียวกัน และเพศตรงกับรายการ)
    entries ต้องเป็นของโรงเรียนเดียว คืน {key: (คำนำหน้า, ชื่อ, นามสกุล)}"""
    want = gender_of_event(ev['event'])
    out = {}
    for e in entries:
        if e['level'] != ev['level']:
            continue
        for p, f, l in ((e['oPrefix'], e['oFirst'], e['oLast']), (e['prefix'], e['first'], e['last'])):
            g = gender_of_prefix(p)
            if want and g and g != want:
                continue
            out.setdefault(pkey(e['school'], f, l), (p, f, l))
    return out


AUTO_BY = 'ยืนยันอัตโนมัติ (เลยเวลาปิด ใช้รายชื่อตามที่สมัคร)'


def apply_auto(entries, events, confs, now):
    """เลยเวลาปิดแล้วโรงเรียนยังไม่ยืนยันรายการใด ให้ถือว่ายืนยันตามรายชื่อที่ลงไว้ในระบบ
    คำนวณตอนอ่านข้อมูล (ไม่เขียนลงฐานข้อมูล) คืน (entries, confs) ชุดใหม่ ที่มีเครื่องหมาย auto=True"""
    closed = {e['event']: e for e in events if is_closed(e, now)}
    have = {(c['school'], c['event']) for c in confs}
    auto = {}
    out = []
    for e in entries:
        k = (e['school'], e['event'])
        if e['event'] in closed and k not in have:
            if e['status'] == PENDING:
                e = dict(e, status=OK, auto=True)
            if e['status'] == OK:
                auto[k] = auto.get(k, 0) + 1
            else:
                auto.setdefault(k, 0)
        out.append(e)
    extra = [dict(school=s, event=ev, by=AUTO_BY, phone='', at=closed[ev]['deadline'], count=n, auto=True)
             for (s, ev), n in auto.items()]
    return out, list(confs) + extra


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
        pool = roster([e for e in entries if e['school'] == school], ev)
        out.append(dict(
            pool=sorted(({'prefix': p, 'first': f, 'last': l} for p, f, l in pool.values()),
                        key=lambda x: (x['first'], x['last'])),
            event=ev['event'], short=ev['short'], level=ev['level'], category=ev['category'],
            size=team_size(ev['category']),
            startDate=ev['startDate'], startTime=ev['startTime'], deadline=ev['deadline'],
            closed=is_closed(ev, now), confirmation=cm.get((school, ev['event'])),
            entries=[dict(id=e['id'], team=e['team'], teamLabel=team_label(e['team'], ev['category']),
                          prefix=e['prefix'], first=e['first'], last=e['last'], oPrefix=e['oPrefix'],
                          oFirst=e['oFirst'], oLast=e['oLast'], status=e['status'], by=e['by'], at=e['at'])
                     for e in sorted(rows, key=team_sort)]))
    return dict(school=school, max=max_events, events=out)


def team_size(category):
    """จำนวนช่องต่อ 1 ทีม/คู่ (รวมตัวสำรอง)"""
    if category in SINGLE_CATEGORIES:
        return 1
    if 'คู่' in category:
        return 3          # ตัวจริง 2 + สำรอง 1
    return 4              # ทีม 3 คน + สำรอง 1


def apply_submit(entries, events, payload, now, staff, max_events):
    """ตรวจข้อมูลที่ส่งมา คืน changes/inserts/logs/conf ถ้าผ่าน หรือ errors ถ้าไม่ผ่าน

    items: [{id: รหัสเดิม หรือ None = ช่องใหม่, team: '1'|'2', prefix, first, last, withdrawn: ช่องว่าง/ไม่ส่ง}]
    staff = ชื่อผู้ใช้เจ้าหน้าที่ (แก้ได้แม้เลยเวลาปิด) หรือ None
    เจ้าหน้าที่แก้: ไม่ต้องกรอกชื่อ/เบอร์ ไม่นับเป็นการยืนยันของโรงเรียน (conf=None) และคงชื่อผู้ยืนยันเดิมไว้"""
    em = {e['event']: e for e in events}
    ev = em.get(payload.get('event'))
    if not ev:
        return dict(ok=False, errors=['ไม่พบรายการแข่งขันนี้'])
    school = payload.get('school')
    by = clean(payload.get('by'))
    phone = re.sub(r'\D', '', str(payload.get('phone') or ''))
    errors = []
    if staff:
        by, phone = '', ''
    elif not by:
        errors.append('กรุณากรอกชื่อผู้ยืนยัน/แก้ไข')
    if not staff and not re.fullmatch(r'0\d{8,9}', phone):
        errors.append('เบอร์โทรต้องเป็นตัวเลข 9–10 หลัก ขึ้นต้นด้วย 0')
    if not staff and is_closed(ev, now):
        errors.append(f"ปิดรับยืนยันรายการนี้แล้ว ({ev['deadline']} น.) ติดต่อเจ้าหน้าที่")

    school_entries = [e for e in entries if e['school'] == school]
    mine = {e['id']: e for e in school_entries if e['event'] == ev['event']}
    if not mine:
        errors.append('ไม่พบรายชื่อของโรงเรียนในรายการนี้')
    pool = roster(school_entries, ev)
    size = team_size(ev['category'])
    seen, changes, inserts, logs, ts = set(), [], [], [], stamp()
    per_team, given = {}, set()

    for it in payload.get('items') or []:
        try:
            eid = int(it['id']) if it.get('id') not in (None, '', 'new') else None
        except (TypeError, ValueError):
            return dict(ok=False, errors=['ข้อมูลไม่ถูกต้อง กรุณาโหลดหน้าใหม่'])
        e = mine.get(eid) if eid is not None else None
        if eid is not None and e is None:
            return dict(ok=False, errors=['ข้อมูลไม่ตรงกับในระบบ กรุณาโหลดหน้าใหม่'])
        if eid is not None:
            given.add(eid)
        team = str(it.get('team') or (e['team'] if e else '1')).strip()
        if team not in ('1', '2') and not (e and team == str(e['team'])):
            errors.append('เลือกทีมที่ 1 หรือ 2 ให้ถูกต้อง')
            continue
        out = bool(it.get('withdrawn'))       # ช่องว่าง / ไม่ส่ง
        if out and e is None:
            continue                          # ช่องใหม่ที่เว้นว่างไว้: ไม่ต้องบันทึก
        p, f, l = clean(it.get('prefix'))[:20], clean(it.get('first'))[:80], clean(it.get('last'))[:80]
        if not out:
            k = pkey(school, f, l)
            if not f or k not in pool:
                errors.append(f'{p}{f} {l} ไม่อยู่ในรายชื่อที่โรงเรียนสมัครไว้ในรุ่นนี้ เลือกจากรายชื่อในช่องเท่านั้น')
                continue
            p, f, l = pool[k]
            if k in seen:
                errors.append(f'{p}{f} {l} มีชื่อซ้ำในรายการนี้')
            seen.add(k)
            other = [x for x in school_entries if x['event'] != ev['event'] and countable(x)
                     and pkey(x['school'], x['first'], x['last']) == k]
            if max_events and len(other) + 1 > max_events:
                names = ', '.join(em.get(x['event'], {}).get('short', x['event']) for x in other)
                errors.append(f'{p}{f} {l} ยืนยันไปแล้ว {len(other)} รายการ ({names}) '
                              f'ยืนยันได้สูงสุด {max_events} รายการต่อคน')
            per_team[team] = per_team.get(team, 0) + 1
        label = team_label(team, ev['category'])
        if e is None:
            nu = dict(team=team, prefix=p, first=f, last=l, status=OK, by=by[:120], phone=phone, at=ts)
            inserts.append(nu)
            logs.append(dict(at=ts, school=school, event=ev['event'], entry_id=None, action='เพิ่มนักกีฬา',
                             before='', after=f'{p}{f} {l} ({label}) [{OK}]', by=nu['by'], phone=phone, user=staff or ''))
            continue
        nu = dict(prefix=e['prefix'] if out else p, first=e['first'] if out else f,
                  last=e['last'] if out else l, status=OUT if out else OK, by=by[:120], phone=phone, at=ts, team=team)
        if staff:  # ไม่ทับชื่อผู้ยืนยันเดิมของโรงเรียน
            nu.update(by=e['by'] or '', phone=e['phone'] or '', at=e['at'] or '')
        name_changed = (nu['prefix'], nu['first'], nu['last']) != (e['prefix'], e['first'], e['last'])
        team_changed = team != str(e['team'])
        if name_changed or team_changed or nu['status'] != e['status']:
            logs.append(dict(at=ts, school=school, event=e['event'], entry_id=e['id'],
                             action='ไม่ส่ง' if out else ('แก้ไขชื่อ' if name_changed else ('ระบุทีม' if team_changed else 'ยืนยัน')),
                             before=f"{e['prefix']}{e['first']} {e['last']} ({team_label(e['team'], ev['category'])}) [{e['status']}]",
                             after=f"{nu['prefix']}{nu['first']} {nu['last']} ({label}) [{nu['status']}]",
                             by=nu['by'], phone=phone, user=staff or ''))
        changes.append((e['id'], nu))

    if mine and set(mine) - given:
        errors.append('ข้อมูลไม่ครบ กรุณาโหลดหน้าใหม่')
    for t, n in sorted(per_team.items()):
        if t in ('1', '2') and n > size:
            errors.append(f'{team_label(t, ev["category"])} ใส่ได้ไม่เกิน {size} คน (ตอนนี้ {n} คน)')
    errors = list(dict.fromkeys(errors))
    if errors:
        return dict(ok=False, errors=errors)
    count = sum(1 for _, nu in changes if nu['status'] == OK) + len(inserts)
    conf = None if staff else dict(school=school, event=ev['event'], by=by[:120], phone=phone, at=ts, count=count)
    return dict(ok=True, changes=changes, inserts=inserts, logs=logs, conf=conf, count=count)


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
                    pairsTotal=len(pairs), pairsDone=sum(1 for p in pairs if p in cm),
                    pairsAuto=sum(1 for p in pairs if p in cm and cm[p].get('auto'))),
        over=[p for p in pc.values() if max_events and len(p['events']) > max_events])


def print_data(entries, events, confs, f):
    cm = {(c['school'], c['event']): c for c in confs}
    want = set(f.get('events') or [])
    evs = [ev for ev in events if (not want or ev['event'] in want)
           and (not f.get('startDate') or ev['startDate'] == f['startDate'])
           and (not f.get('level') or ev['level'] == f['level'])
           and (not f.get('category') or ev['category'] == f['category'])]
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


# ---------------- ผลการแข่งขัน ----------------
MEDALS = ('gold', 'silver', 'bronze', 'none')
MEDAL_TH = {'gold': 'ทอง', 'silver': 'เงิน', 'bronze': 'ทองแดง', 'none': 'ไม่ได้รางวัล'}
MEDAL_MAX = {'gold': 1, 'silver': 1, 'bronze': 2}     # เปตองมีทองแดงร่วม 2 ทีม


def result_units(entries, events, school=None, event=None):
    """หน่วยที่ได้รางวัล: ประเภทเดี่ยว = รายคน, ประเภทคู่/ทีม = ทีม (รวมตัวสำรอง)
    ใช้เฉพาะรายชื่อที่ยืนยันแล้ว (ส่ง entries ที่ผ่าน apply_auto มา)"""
    em = {e['event']: e for e in events}
    out = {}
    for e in sorted(entries, key=team_sort):
        ev = em.get(e['event'])
        if not ev or e['status'] != OK or (school and e['school'] != school) or (event and e['event'] != event):
            continue
        single = team_size(ev['category']) == 1
        unit = f"e{e['id']}" if single else str(e['team'])
        k = (e['event'], e['school'], unit)
        if k not in out:
            out[k] = dict(event=e['event'], short=ev['short'], level=ev['level'], category=ev['category'],
                          startDate=ev['startDate'], sort=ev.get('sort', 0), school=e['school'], unit=unit,
                          label='บุคคล' if single else team_label(e['team'], ev['category']).replace('คู่ที่', 'ทีมที่'),
                          members=[])
        out[k]['members'].append(f"{e['prefix']}{e['first']} {e['last']}")
    order = {e['event']: i for i, e in enumerate(events)}
    return sorted(out.values(), key=lambda u: (order.get(u['event'], 0), u['school'], u['unit']))


def results_public(entries, events, results):
    """ตารางเหรียญตามสถาบัน (นับต่อทีม) + รายบุคคล + ผลรายรายการ"""
    rm = {(r['event'], r['school'], r['unit']): r['medal'] for r in results}
    units = result_units(entries, events)
    for u in units:
        u['medal'] = rm.get((u['event'], u['school'], u['unit']), '')
    won = [u for u in units if u['medal'] in MEDAL_MAX]
    table = {}
    for u in won:
        for lv in ('', u['level']):
            t = table.setdefault((lv, u['school']), dict(school=u['school'], level=lv, gold=0, silver=0, bronze=0))
            t[u['medal']] += 1
    rows = [dict(t, total=t['gold'] + t['silver'] + t['bronze']) for t in table.values()]
    rows.sort(key=lambda t: (t['level'], -t['gold'], -t['silver'], -t['bronze'], t['school']))
    people = [dict(name=m, school=u['school'], event=u['event'], short=u['short'], level=u['level'],
                   label=u['label'], medal=u['medal']) for u in won for m in u['members']]
    rank = {'gold': 0, 'silver': 1, 'bronze': 2}
    people.sort(key=lambda p: (p['school'], p['name'], rank[p['medal']]))
    by_event = []
    em = {}
    for u in won:
        em.setdefault(u['event'], []).append(u)
    for ev in events:
        if ev['event'] in em:
            by_event.append(dict(event=ev['event'], short=ev['short'], level=ev['level'], startDate=ev['startDate'],
                                 winners=sorted(em[ev['event']], key=lambda u: rank[u['medal']])))
    done = len({u['event'] for u in units if u['medal']})
    return dict(table=rows, people=people, events=by_event,
                progress=dict(events=len({u['event'] for u in units}), withResult=done))


MEDAL_FROM_TH = {'ทอง': 'gold', 'ชนะเลิศ': 'gold', 'เงิน': 'silver', 'รองชนะเลิศอันดับ 1': 'silver',
                 'ทองแดง': 'bronze', 'รองชนะเลิศอันดับ 2': 'bronze', 'gold': 'gold', 'silver': 'silver', 'bronze': 'bronze'}
_PREFIX = re.compile(r'^(ด\.ช\.|ด\.ญ\.|เด็กชาย|เด็กหญิง|นางสาว|น\.ส\.|นาย|นาง)')


def norm_name(s):
    s = re.sub(r'\s+', '', str(s or ''))
    return _PREFIX.sub('', s)


def match_results(rows, units):
    """rows: [{event, medal, name, group}] 1 แถวต่อ 1 คน; แถวที่ event+medal+group เดียวกันคือทีมเดียวกัน
    (group = ชื่อโรงเรียนในไฟล์ ถ้าไม่มีถือว่าแต่ละแถวเป็นคนละทีม)
    จับคู่กับหน่วยตามชื่อ: ตรงกันก่อน ไม่ตรงใช้ชื่อที่คล้ายที่สุด (สะกดต่างเล็กน้อย)
    ทีมที่หาเจออย่างน้อย 1 คนถือว่าใช้ได้ ส่วนคนที่หาไม่เจอแจ้งเป็นคำเตือน
    คืน (found {(event, school, unit): (medal, unit)}, problems, notes)"""
    import difflib
    by_ev = {}
    for u in units:
        by_ev.setdefault(u['event'], []).append(u)

    def find(cand, name):
        n = norm_name(name)
        hit = [u for u in cand if any(norm_name(m) == n for m in u['members'])]
        if hit:
            return hit, False
        best, score = None, 0
        for u in cand:
            for m in u['members']:
                sc = difflib.SequenceMatcher(None, n, norm_name(m)).ratio()
                if sc > score:
                    best, score = u, sc
        return ([best], True) if best and score >= 0.8 else ([], False)

    groups, order = {}, []
    for i, r in enumerate(rows):
        k = (r['event'], r['medal'], r.get('group') or f'#{i}')
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(r)
    found, problems, notes = {}, [], []
    for k in order:
        ev, medal, _ = k
        short = ev.replace('เปตอง : ', '')
        cand = by_ev.get(ev, [])
        if not cand:
            problems.append(f"ไม่พบรายการ “{ev}” หรือไม่มีทีมที่ยืนยันแล้ว")
            continue
        hits, miss = {}, []
        for r in groups[k]:
            h, fz = find(cand, r['name'])
            if len(h) == 1:
                hits[(h[0]['school'], h[0]['unit'])] = h[0]
                if fz:
                    notes.append(f"{short}: “{r['name']}” ใช้ชื่อในระบบ " + next(
                        m for m in h[0]['members'] if difflib.SequenceMatcher(None, norm_name(r['name']), norm_name(m)).ratio() >= 0.8))
            else:
                miss.append(r['name'])
        names = ', '.join(r['name'] for r in groups[k])
        if len(hits) != 1:
            problems.append(f"{short} ({MEDAL_TH[medal]}): " + (f"ไม่พบ {names}" if not hits else f"{names} อยู่คนละทีมในระบบ"))
            continue
        u = next(iter(hits.values()))
        for n in miss:
            notes.append(f"{short}: ไม่พบ “{n}” แต่พบเพื่อนร่วมทีม ({u['school']} {u['label']})")
        fk = (u['event'], u['school'], u['unit'])
        if fk in found and found[fk][0] != medal:
            problems.append(f"{short}: {u['school']} ได้ผลขัดกัน")
            continue
        found[fk] = (medal, u)
    return found, problems, notes
