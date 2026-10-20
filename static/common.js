/* ฟังก์ชันที่ใช้ร่วมกันทุกหน้า */
(function () {
  var MONTHS = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
  var DAYS = ['อาทิตย์', 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์'];
  var LEVEL_LABEL = { 'อนุบาล': 'อนุบาล', 'ประถมศึกษา': 'ประถม', 'มัธยมศึกษาตอนต้น': 'ม.ต้น', 'มัธยมศึกษาตอนปลาย': 'ม.ปลาย' };
  var LEVEL_ORDER = ['อนุบาล', 'ประถมศึกษา', 'มัธยมศึกษาตอนต้น', 'มัธยมศึกษาตอนปลาย'];

  function http(method, url, body) {
    var opt = { method: method, headers: { 'X-Requested-With': 'checkin' }, credentials: 'same-origin' };
    if (body instanceof FormData) opt.body = body;
    else if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch(url, opt).then(function (r) {
      return r.json().catch(function () { return { error: 'เซิร์ฟเวอร์ตอบกลับผิดพลาด (' + r.status + ')' }; }).then(function (d) {
        if (!r.ok || (d && d.error)) { var e = new Error((d && d.error) || ('ผิดพลาด ' + r.status)); e.status = r.status; throw e; }
        return d;
      });
    });
  }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function norm(s) { return String(s == null ? '' : s).replace(/\s+/g, ''); }
  function toMs(s) {
    var m = String(s || '').match(/(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?/);
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3], (+m[4] || 0) - 7, +m[5] || 0) : NaN;
  }
  function thDate(s, withDay) {
    var m = String(s || '').match(/(\d{4})-(\d{2})-(\d{2})/); if (!m) return s ? String(s) : 'ยังไม่กำหนดวัน';
    var d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    return (withDay ? 'วัน' + DAYS[d.getUTCDay()] + 'ที่ ' : '') + (+m[3]) + ' ' + MONTHS[+m[2] - 1] + ' ' + (+m[1] + 543);
  }
  function thDateTime(s) {
    var m = String(s || '').match(/(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})/); if (!m) return s ? thDate(s) : 'ยังไม่กำหนด';
    return thDate(m[1]) + ' ' + ('0' + m[2]).slice(-2) + '.' + m[3] + ' น.';
  }
  function left(ms) {
    var d = ms - Date.now(); if (d <= 0) return 'ปิดแล้ว';
    var h = Math.floor(d / 36e5), dd = Math.floor(h / 24);
    return dd >= 1 ? 'เหลือ ' + dd + ' วัน ' + (h % 24) + ' ชม.' : 'เหลือ ' + h + ' ชม. ' + Math.floor(d % 36e5 / 6e4) + ' นาที';
  }
  function toast(msg) {
    var t = document.getElementById('toast');
    if (!t) { t = document.createElement('div'); t.id = 'toast'; t.className = 'toast'; document.body.appendChild(t); }
    t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(function () { t.hidden = true; }, 3500);
  }
  function levelLabel(name) { return LEVEL_LABEL[name] || name || 'ทั่วไป'; }
  function levelsOf(events) {
    var seen = [];
    events.forEach(function (e) { if (seen.indexOf(e.level) < 0) seen.push(e.level); });
    return seen.sort(function (a, b) {
      var ia = LEVEL_ORDER.indexOf(a), ib = LEVEL_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || String(a).localeCompare(String(b), 'th');
    });
  }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  function logoHtml(comp, cls) {
    return comp.logo ? '<img class="' + (cls || 'logo') + '" src="' + esc(comp.logo) + '" alt="ตราการแข่งขัน">'
      : '<div class="logo-ph" aria-hidden="true">' + esc((comp.sport || comp.name || '?').slice(0, 1)) + '</div>';
  }
  function days(events) {
    var g = {};
    events.forEach(function (ev) {
      var k = ev.startDate || '';
      var d = g[k] || (g[k] = { startDate: ev.startDate, deadline: ev.deadline, cats: [] });
      if (d.cats.indexOf(ev.category) < 0) d.cats.push(ev.category);
    });
    return Object.keys(g).sort(function (a, b) { return (a || '9') < (b || '9') ? -1 : 1; }).map(function (k) { return g[k]; });
  }

  window.C = { http: http, esc: esc, norm: norm, toMs: toMs, thDate: thDate, thDateTime: thDateTime, left: left,
    toast: toast, levelLabel: levelLabel, levelsOf: levelsOf, store: store, logoHtml: logoHtml, days: days };
})();
