/* Redaktions-Dashboard: Quellen, Durchläufe, KI-Labor, Prüfung, kuratierte Inhalte (CMS), Meldungen, Partner */
(function () {
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let token = sessionStorage.getItem('oo-token') || '';
  let page = 'overview', selQ = null, lab = { text: '', res: null };
  const toast = m => { const t = $('#toast'); t.textContent = m; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => t.hidden = true, 3200); };
  async function api(path, body) {
    const r = await fetch(path, { method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json', 'X-Token': token }, body: body ? JSON.stringify(body) : undefined });
    if (r.status === 401) { logout(); throw new Error('Bitte erneut anmelden.'); }
    if (!r.ok) { let d = 'Fehler'; try { d = (await r.json()).detail; } catch (e) {} throw new Error(d); }
    return r.json();
  }
  const fmt = d => d ? new Date(d.slice(0, 10) + 'T00:00').toLocaleDateString('de-DE', { day: 'numeric', month: 'short' }) : '–';
  const ago = s => { if (!s) return 'noch nie'; const m = Math.round((Date.now() - new Date(s.replace(' ', 'T'))) / 60000); return m < 1 ? 'gerade eben' : m < 60 ? `vor ${m} Min.` : `vor ${Math.round(m / 60)} Std.`; };
  const ST = { ok: ['ok', 'Läuft'], err: ['err', 'Fehler'], null: ['warn', 'Noch nicht abgerufen'] };
  const status = s => { const [c, t] = ST[s] || ST.null; return `<span class="status ${c}">${t}</span>`; };

  $('#login-form').addEventListener('submit', async e => {
    e.preventDefault();
    try { const r = await api('/api/admin/login', { user: $('#l-user').value, password: $('#l-pass').value }); token = r.token; sessionStorage.setItem('oo-token', token); show(); }
    catch (err) { $('#l-msg').textContent = err.message; }
  });
  function logout() { token = ''; sessionStorage.removeItem('oo-token'); $('#v-app').hidden = true; $('#v-login').hidden = false; }
  function show() { $('#v-login').hidden = true; $('#v-app').hidden = false; render(); }

  const NAV = [['overview', 'Übersicht'], ['sources', 'Quellen & Durchläufe'], ['lab', 'KI-Labor'], ['review', 'Prüfung'], ['cms', 'Kuratierte Inhalte'], ['reports', 'Meldungen'], ['partner', 'Partner-Ansicht']];
  function nav() {
    $('#snav').innerHTML = NAV.map(([k, l]) => `<button type="button" data-p="${k}" ${k === page ? 'aria-current="page"' : ''}><span class="lbltxt">${l}</span></button>`).join('') + `<button type="button" id="out"><span class="lbltxt">Abmelden</span></button>`;
    document.querySelectorAll('[data-p]').forEach(b => b.onclick = () => { page = b.dataset.p; render(); });
    $('#out').onclick = logout;
  }
  async function render() {
    nav();
    try { await ({ overview, sources, lab: labPage, review, cms, reports, partner }[page])(); }
    catch (e) { $('#content').innerHTML = `<p class="empty">${esc(e.message)}</p>`; }
  }
  const head = (eb, h, extra = '') => `<div class="hello"><div><p class="eyebrow">${eb}</p><h1>${h}</h1></div>${extra}</div>`;

  /* ---------- Übersicht ---------- */
  const STATNAME = k => ({ 'view:start': 'Startseite', 'view:mein': 'Mein Oberfranken', 'view:datenschutz': 'Datenschutz-Seite', ask: 'Fragen an den KI-Begleiter', followup: 'Folgefragen geklickt', plan: 'Tagespläne gespeichert', save: 'Einträge gemerkt', feedback: 'Feedback gegeben' }[k] || (k.startsWith('view:region:') ? 'Region ' + k.slice(12) : k));
  async function overview() {
    const o = await api('/api/admin/overview');
    const r = o.last_run || {};
    const max = Math.max(1, ...o.categories.map(c => c.n));
    $('#content').innerHTML = head('Redaktions-Dashboard', 'Quellen, KI und Prüfung', `<p class="note">KI: ${esc(o.engine)} · Durchlauf alle ${o.interval} Min.</p>`) +
      `<div class="kpis">${[[`${o.sources_active} / ${o.sources_total}`, 'Quellen aktiv'], [o.new_24h, 'Neue Inhalte (24 h)'], [o.queue, 'Warten auf Prüfung'], [Math.round(o.avg_conf * 100) + ' %', 'Ø KI-Sicherheit']].map(x => `<div class="stat"><span class="n">${x[0]}</span><span class="l">${x[1]}</span></div>`).join('')}</div>
      <div class="panel"><div class="sec-head"><h2>Letzter Durchlauf</h2><span class="note">${r.finished ? ago(r.finished) : 'läuft gerade'}</span></div>
        <div class="flow">${[[r.fetched, 'Abgerufen'], [r.new, 'Neu'], [r.duplicates, 'Duplikate'], [r.processed, 'KI verarbeitet'], [r.live, 'Automatisch live'], [r.review, 'Zur Prüfung']].map((x, i) => (i ? '<span class="arr">→</span>' : '') + `<div class="st"><b>${x[0] ?? 0}</b><span>${x[1]}</span></div>`).join('')}</div></div>
      <div class="two"><div class="panel"><div class="sec-head"><h2>Inhalte pro Thema</h2><span class="note">freigegeben</span></div><div class="bars">
        ${o.categories.map(c => `<div class="barrow" tabindex="0" title="${esc(c.category)}: ${c.n}"><span>${esc(c.category)}</span><div class="track"><div class="fill" style="width:${c.n / max * 100}%"></div></div><span class="v">${c.n}</span></div>`).join('')}</div></div>
        <div class="panel"><div class="sec-head"><h2>KI-Kosten diesen Monat</h2></div>
          <div class="flow"><div class="st"><b>${o.cost.processed}</b><span>Inhalte verarbeitet</span></div><div class="st"><b>${(o.cost.tokens_in + o.cost.tokens_out).toLocaleString('de-DE')}</b><span>Tokens (echt gemessen)</span></div><div class="st"><b>${o.cost.usd.toLocaleString('de-DE', { style: 'currency', currency: 'USD', maximumFractionDigits: 4 })}</b><span>tatsächliche Kosten</span></div></div>
          <p class="note">Schätzung bei LLM-Betrieb: ${o.cost.est_usd.toLocaleString('de-DE', { style: 'currency', currency: 'USD' })} (1.500 Tokens rein, 300 raus je Inhalt, ${o.cost.price_in} / ${o.cost.price_out} $ pro 1 Mio.). Ohne API-Schlüssel kostet die regelbasierte Verarbeitung nichts.</p>
          <p class="note"><b>KI-Begleiter (Chat) seit Serverstart:</b> ${o.chat.calls} LLM-Antworten · ${(o.chat.tokens_in + o.chat.tokens_out).toLocaleString('de-DE')} Tokens · ${o.chat.usd.toLocaleString('de-DE', { style: 'currency', currency: 'USD', maximumFractionDigits: 4 })} · Feedback 👍 ${o.chat.up} / 👎 ${o.chat.down}</p></div></div>
      <div class="panel"><div class="sec-head"><h2>Anonyme Statistik (7 Tage)</h2><span class="note">nur mit Einwilligung · nur Summen pro Tag · keine IP, keine ID</span></div>
        ${o.stats.length ? `<div class="bars">${o.stats.map(x => `<div class="barrow"><span>${esc(STATNAME(x.key))}</span><div class="track"><div class="fill" style="width:${x.n / Math.max(...o.stats.map(y => y.n)) * 100}%"></div></div><span class="v">${x.n}</span></div>`).join('')}</div>` : '<p class="note">Noch keine Zahlen. Es wird nur gezählt, wenn Besucher „Anonyme Statistik“ erlauben.</p>'}
        <p class="note" style="margin-top:10px">IP-Adressen: nicht gespeichert, kein Zugriffsprotokoll · Missbrauchsschutz nur im Arbeitsspeicher (Hash, täglich neuer Schlüssel) · Regionsvorschlag per GeoIP: ${o.geoip ? 'aktiv (lokale Datei)' : 'aus (keine GeoIP-Datei)'}</p></div>
      <div class="panel"><div class="sec-head"><h2>Themen dieser Woche</h2><span class="note">automatisch erkannte Begriffe</span></div><div class="chips">${o.trends.length ? o.trends.map(([w, n]) => `<span class="chip" style="cursor:default">${esc(w)} <span class="note">${n}×</span></span>`).join('') : '<span class="note">Noch zu wenige Inhalte.</span>'}</div></div>`;
  }

  /* ---------- Quellen ---------- */
  let poll = null;
  async function sources() {
    const [srcs, runs] = await Promise.all([api('/api/admin/sources'), api('/api/admin/runs')]);
    const M = { rss: 'RSS', jsonld: 'schema.org', api: 'API', crawler: 'Crawler' };
    $('#content').innerHTML = head('Datenerfassung', 'Quellen & Durchläufe', `<button class="btn primary" type="button" id="run" ${runs.running ? 'disabled' : ''}>${runs.running ? 'Läuft …' : 'Alle jetzt abrufen'}</button>`) +
      `<div class="panel"><div class="tbl-wrap"><table><thead><tr><th>Quelle</th><th>Methode</th><th>Status</th><th class="num">Neu</th><th class="num">Gesamt</th><th>Letzter Abruf</th><th></th></tr></thead><tbody>
      ${srcs.map(s => `<tr><td><b>${esc(s.name)}</b><div class="note mono">${esc(s.url)}</div>${s.last_error ? `<div class="note" style="color:var(--crit)">${esc(s.last_error)}</div>` : ''}</td><td><span class="method">${M[s.method] || s.method}</span></td><td>${status(s.last_status)}</td><td class="num">${s.last_new}</td><td class="num">${s.total}</td><td class="mono">${ago(s.last_run)}</td><td><button class="btn sm" type="button" data-run="${esc(s.id)}">Abrufen</button></td></tr>`).join('')}
      </tbody></table></div><p class="note">Neue Quellen trägt man in <span class="mono">app/sources.json</span> ein. Webquellen prüfen vorher robots.txt (§ 44b UrhG).</p></div>
      <div class="panel"><h2>Durchläufe</h2>${runs.runs.map(r => `<details ${r === runs.runs[0] ? 'open' : ''}><summary><b>${esc(r.started)}</b> · ${r.fetched} abgerufen, ${r.new} neu, ${r.duplicates} Duplikate, ${r.live} live, ${r.review} Prüfung</summary><pre class="logline">${esc(r.log || 'läuft …')}</pre></details>`).join('') || '<p class="empty">Noch kein Durchlauf.</p>'}</div>`;
    const start = async src => { try { await api('/api/admin/run', src ? { source: src } : {}); toast('Abruf gestartet.'); clearInterval(poll); poll = setInterval(async () => { const r = await api('/api/admin/runs'); if (!r.running) { clearInterval(poll); toast('Abruf fertig.'); if (page === 'sources') sources(); } }, 1500); sources(); } catch (e) { toast(e.message); } };
    $('#run').onclick = () => start();
    document.querySelectorAll('[data-run]').forEach(b => b.onclick = () => start(b.dataset.run));
  }

  /* ---------- KI-Labor ---------- */
  const EX = ['Mountainbike-Tour am Ochsenkopf\nAm Samstag führt eine geführte Tour über 28 km rund um den Ochsenkopf bei Bischofsgrün. Leihräder gibt es an der Talstation, Start 9:30 Uhr.',
    'Karrieretag Pflege und Gesundheit\nAm 24. Oktober stellen sich in Hof über 20 Kliniken und Pflegedienste vor. Für Fachkräfte aus dem Ausland gibt es Beratung zur Anerkennung von Abschlüssen.',
    'Weinfest am Mainufer\nVom 10. bis 11. Oktober schenken Winzer in Würzburg ihre neuen Weine aus. Livemusik ab 18 Uhr.'];
  async function labPage() {
    if (!lab.text) lab.text = EX[0];
    $('#content').innerHTML = head('KI-Verarbeitung', 'KI-Labor: Text rein, strukturierter Inhalt raus') +
      `<div class="two"><div class="panel"><h2>Eingabe</h2><div class="chips">${EX.map((_, i) => `<button class="chip" type="button" data-ex="${i}">Beispiel ${i + 1}</button>`).join('')}</div>
        <textarea class="field" id="lab-in" rows="9">${esc(lab.text)}</textarea>
        <div class="actions"><button class="btn primary" type="button" id="lab-go">Verarbeiten</button></div>
        <p class="note">Mit LLM_API_KEY in der .env-Datei ruft das echte Sprachmodell auf, sonst die regelbasierte Extraktion.</p></div>
      <div class="panel detail" id="lab-out"><h2>Ergebnis</h2><p class="empty">Klicke auf „Verarbeiten“.</p></div></div>`;
    document.querySelectorAll('[data-ex]').forEach(b => b.onclick = () => { lab.text = EX[+b.dataset.ex]; lab.res = null; labPage(); });
    $('#lab-in').oninput = e => lab.text = e.target.value;
    $('#lab-go').onclick = async () => {
      $('#lab-out').innerHTML = '<h2>Ergebnis</h2><p class="muted">Verarbeite …</p>';
      try { lab.res = await api('/api/admin/process', { text: lab.text }); showLab(); } catch (e) { $('#lab-out').innerHTML = `<h2>Ergebnis</h2><p class="empty">${esc(e.message)}</p>`; }
    };
    if (lab.res) showLab();
  }
  function showLab() {
    const r = lab.res;
    $('#lab-out').innerHTML = `<div class="sec-head"><h2>Ergebnis</h2><span class="method">${esc(r.engine)}</span></div>
      <dl><dt>Titel</dt><dd><b>${esc(r.title)}</b></dd><dt>Zusammenfassung</dt><dd>${esc(r.summary)}</dd><dt>Englisch</dt><dd>${r.summary_en ? esc(r.summary_en) : '<span class="note">nur mit LLM</span>'}</dd>
      <dt>Thema</dt><dd>${esc(r.category)}</dd><dt>Schlagwörter</dt><dd>${(r.keywords || []).map(k => `<span class="method">${esc(k)}</span>`).join(' ')}</dd>
      <dt>Priorität</dt><dd>${'●'.repeat(r.priority || 1)} <span class="note">${r.priority} von 5</span></dd><dt>Ort</dt><dd>${esc(r.location || 'nicht erkannt')}${r.coords ? ` <span class="note">${r.coords.join(', ')}</span>` : ''}</dd>
      <dt>Datum</dt><dd>${r.event_date ? fmt(r.event_date) : 'nicht erkannt'}</dd><dt>KI-Sicherheit</dt><dd class="mono">${Number(r.confidence).toFixed(2)}</dd></dl>
      <div><h3>Automatische Prüfung</h3>${r.checks.length ? r.checks.map(c => `<div><span class="status warn">${esc(c)}</span></div>`).join('') : '<span class="status ok">Alle Prüfungen bestanden</span>'}</div>
      <div class="actions"><button class="btn primary" type="button" id="lab-pub">${r.checks.length ? 'In die Prüfung geben' : 'Veröffentlichen'}</button></div>
      <details><summary class="note">Prompt anzeigen</summary><pre class="logline">${esc(r.prompt)}</pre></details>`;
    $('#lab-pub').onclick = async () => { const res = await api('/api/admin/publish', { result: r, text: lab.text }); toast(res.status === 'live' ? 'Veröffentlicht, jetzt auf der Nutzerseite.' : 'In die Prüfwarteschlange gelegt.'); lab.res = null; page = res.status === 'live' ? 'lab' : 'review'; render(); };
  }

  /* ---------- Prüfung ---------- */
  async function review() {
    const q = await api('/api/admin/queue');
    if (!q.find(i => i.id === selQ)) selQ = q[0] && q[0].id;
    const i = q.find(x => x.id === selQ);
    $('#content').innerHTML = head('Qualitätssicherung', 'Prüfung durch die Redaktion', `<p class="note">${q.length} offen · nur Unsicheres landet hier</p>`) +
      `<div class="two"><div class="panel"><div class="queue">${q.map(x => `<button type="button" class="qitem" aria-selected="${x.id === selQ}" data-q="${x.id}"><span class="why">${esc(x.flags.join(' · '))}</span><b>${esc(x.title)}</b><span class="conf">KI-Sicherheit ${Math.round(x.confidence * 100)} % · ${esc(x.source)}</span></button>`).join('') || '<p class="empty">Alles geprüft.</p>'}</div></div>
      <div class="panel detail">${i ? `<h2>${esc(i.title)}</h2><div class="cmp"><div><p class="eyebrow" style="color:var(--ink-3)">Original</p><p>${esc(i.text)}</p></div><div><p class="eyebrow">KI-Zusammenfassung</p><p>${esc(i.summary)}</p></div></div>
        <dl><dt>Quelle</dt><dd>${esc(i.source)} ${i.url ? `<a href="${esc(i.url)}" target="_blank" rel="noopener">Link</a>` : ''}</dd><dt>Thema</dt><dd>${esc(i.category)}</dd><dt>Ort</dt><dd>${esc(i.location || '–')}</dd><dt>Datum</dt><dd>${fmt(i.event_date)}</dd></dl>
        <div class="actions"><button class="btn ok" type="button" id="ok">Freigeben</button><button class="btn no" type="button" id="no">Ablehnen</button></div>` : '<h2>Details</h2><p class="muted">Keine offenen Inhalte.</p>'}</div></div>`;
    document.querySelectorAll('[data-q]').forEach(b => b.onclick = () => { selQ = +b.dataset.q; review(); });
    if (i) { $('#ok').onclick = async () => { await api(`/api/admin/items/${i.id}/approve`, {}); toast('Freigegeben.'); review(); }; $('#no').onclick = async () => { await api(`/api/admin/items/${i.id}/reject`, {}); toast('Abgelehnt.'); review(); }; }
  }

  /* ---------- Kuratierte Inhalte (blau) ---------- */
  async function cms() {
    const items = await fetch('/api/curated').then(r => r.json());
    $('#content').innerHTML = head('Team Oberfranken · 30 %', 'Kuratierte Inhalte', '<p class="note">100 % Kontrolle: diese Texte schreibt die Redaktion selbst</p>') +
      items.map(c => `<form class="panel" data-c="${esc(c.id)}"><p class="eyebrow">${c.slot === 'start' ? 'Startseite' : 'Regionsseite ' + esc(c.region)}</p>
        <div><label class="lbl" for="t-${esc(c.id)}">Überschrift</label><input class="field" id="t-${esc(c.id)}" value="${esc(c.title)}"></div>
        <div><label class="lbl" for="x-${esc(c.id)}">Text</label><textarea class="field" id="x-${esc(c.id)}" rows="3">${esc(c.text)}</textarea></div>
        <div><button class="btn primary sm" type="submit">Speichern</button></div></form>`).join('');
    document.querySelectorAll('[data-c]').forEach(f => f.addEventListener('submit', async e => { e.preventDefault(); const id = f.dataset.c; await api('/api/admin/curated', { id, title: $('#t-' + CSS.escape(id)).value, text: $('#x-' + CSS.escape(id)).value }); toast('Gespeichert, sofort auf der Website.'); }));
  }

  /* ---------- Meldungen ---------- */
  async function reports() {
    const r = await api('/api/admin/reports');
    $('#content').innerHTML = head('Nutzerhinweise', 'Meldungen') + `<div class="panel"><div class="tbl-wrap"><table><thead><tr><th>Eintrag</th><th>Grund</th><th>Datum</th><th>Status</th><th></th></tr></thead><tbody>
      ${r.map(x => `<tr><td>${x.item_id ? esc(x.title) : '<b>KI-Begleiter</b>'}</td><td>${esc(x.reason)}</td><td class="mono">${esc(x.created)}</td><td>${x.status === 'offen' ? '<span class="status warn">offen</span>' : '<span class="status ok">erledigt</span>'}</td><td>${x.status === 'offen' ? `<button class="btn sm" type="button" data-d="${x.id}">Erledigt</button>` : ''}</td></tr>`).join('') || '<tr><td colspan="5" class="note">Noch keine Meldungen. Auf der Nutzerseite gibt es unter jedem Eintrag „Fehler melden“.</td></tr>'}
      </tbody></table></div></div>`;
    document.querySelectorAll('[data-d]').forEach(b => b.onclick = async () => { await api(`/api/admin/reports/${b.dataset.d}/done`, {}); reports(); });
  }

  /* ---------- Partner ---------- */
  async function partner() {
    const s = (await api('/api/admin/sources')).filter(x => x.total > 0 || x.live > 0);
    $('#content').innerHTML = head('Was Partner davon haben', 'Partner-Ansicht', '<p class="note">Reichweite ohne Mehraufwand: Zahlen pro Quelle</p>') +
      `<div class="panel"><div class="tbl-wrap"><table><thead><tr><th>Partner / Quelle</th><th class="num">Inhalte live</th><th class="num">Angezeigt</th><th class="num">Klicks zur Quelle</th><th class="num">Gemerkt</th></tr></thead><tbody>
      ${s.map(x => `<tr><td><b>${esc(x.name)}</b></td><td class="num">${x.live}</td><td class="num">${x.views}</td><td class="num">${x.clicks}</td><td class="num">${x.saves}</td></tr>`).join('')}
      </tbody></table></div><p class="note">Die Zahlen entstehen echt: Anzeigen auf der Startseite, Klicks auf „Zur Quelle“ und Herzen der Nutzer.</p></div>`;
  }

  if (token) show();
})();
