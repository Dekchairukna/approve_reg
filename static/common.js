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
  /* แถบสลับหน้าสาธารณะของงาน */
  function pageNav(slug, cur) {
    var b = '/c/' + encodeURIComponent(slug), el = document.getElementById('pagenav');
    if (!el) return;
    el.innerHTML = [[b, 'confirm', 'ยืนยันรายชื่อนักกีฬา'], [b + '/roster', 'roster', 'รายชื่อที่ยืนยันลงแข่ง'], [b + '/results', 'results', 'ผลการแข่งขัน']].map(function (x) {
      return '<a href="' + x[0] + '"' + (x[1] === cur ? ' aria-current="page"' : '') + '>' + x[2] + '</a>';
    }).join('');
  }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function norm(s) { return String(s == null ? '' : s).replace(/[\s\u200b\u200c\u200d\ufeff]+/g, ''); }
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
  /* บันทึกเป็นไฟล์ PDF (โหลด html2pdf จาก CDN เมื่อกดครั้งแรก) */
  var H2P = window.__H2P_URL ? [window.__H2P_URL] : ['https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js',
    'https://cdn.jsdelivr.net/npm/html2pdf.js@0.10.1/dist/html2pdf.bundle.min.js'];
  function loadScript(urls) {
    if (window.html2pdf) return Promise.resolve();
    return urls.reduce(function (p, u) {
      return p.catch(function () {
        return new Promise(function (ok, bad) { var s = document.createElement('script'); s.src = u; s.onload = ok; s.onerror = bad; document.head.appendChild(s); });
      });
    }, Promise.reject());
  }
  /* html2canvas ตัดบรรทัดภาษาไทยเพี้ยน (ข้อความซ้อนกัน) — แทรกจุดตัดคำ (ZWSP) ระหว่างคำไทยในสำเนาก่อนสร้าง PDF */
  function zws(root){if(!window.Intl||!Intl.Segmenter)return root;var seg=new Intl.Segmenter('th',{granularity:'word'});var tw=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),n,list=[];while(n=tw.nextNode())if(/[\u0E00-\u0E7F]{6,}/.test(n.nodeValue))list.push(n);list.forEach(function(t){var out=[];for(var it=seg.segment(t.nodeValue)[Symbol.iterator](),r;!(r=it.next()).done;)out.push(r.value.segment);t.nodeValue=out.join('\u200B');});return root}
  function savePdf(el, filename, opt) {
    opt = opt || {};
    toast('กำลังสร้างไฟล์ PDF…');
    var root = document.documentElement;
    root.classList.add('pdfmode');
    var fonts = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    return fonts.then(function () { return loadScript(H2P); }).then(function () {
      return window.html2pdf().set({
        margin: opt.margin || [10, 10, 12, 10], filename: (filename || 'เอกสาร').replace(/[\\/:*?"<>|]+/g, ' ') + '.pdf',
        image: { type: 'jpeg', quality: 0.95 },
        html2canvas: { scale: 2, useCORS: true, backgroundColor: '#ffffff', scrollX: 0, scrollY: 0 },
        jsPDF: { unit: 'mm', format: 'a4', orientation: opt.landscape ? 'landscape' : 'portrait' },
        pagebreak: { mode: ['css', 'legacy'], avoid: opt.avoid || ['tr', '.res-ev', 'h3'] }
      }).from(zws(el.cloneNode(true))).save();
    }).then(function () { toast('บันทึกไฟล์ PDF แล้ว'); }, function (e) {
      toast('สร้าง PDF ไม่สำเร็จ — ใช้ปุ่มพิมพ์ แล้วเลือก "บันทึกเป็น PDF" แทน'); if (window.console) console.error(e);
    }).then(function () { root.classList.remove('pdfmode'); });
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
    toast: toast, savePdf: savePdf, pageNav: pageNav, levelLabel: levelLabel, levelsOf: levelsOf, store: store, logoHtml: logoHtml, days: days };
})();
