/* oberfranken – Nutzerseite (Prototyp)
   Profil, Merkliste und Cookie-Wahl liegen NUR im Browser (localStorage).
   An den Server gehen nur Filter (Themen, Region, Interessen); gespeichert wird davon nichts. */
(function () {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const KEY = 'oberfranken-profil', CK = 'oberfranken-cookie';
  const RLABEL = r => (REGION_NAMES[r] && REGION_NAMES[r] !== r) ? `${r} · ${REGION_NAMES[r]}` : r;
  const REGION_NAMES = { Wunsiedel: 'Fichtelgebirge', Kronach: 'Frankenwald', Lichtenfels: 'Obermain-Jura', Bamberg: 'Bamberg', Bayreuth: 'Bayreuth', Coburg: 'Coburg', Forchheim: 'Fränkische Schweiz', Hof: 'Hof', Kulmbach: 'Kulmbach' };
  const ICON = {
    Events: '<path d="M4 7h16v13H4zM4 11h16M9 3v6M15 3v6"/>',
    Tourismus: '<circle cx="6" cy="17" r="3.5"/><circle cx="18" cy="17" r="3.5"/><path d="M6 17l4-8h5l3 8M10 9l-2-3H6M14 9l1-3h2"/>',
    Wirtschaft: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V4h8v3"/>',
    Wissenschaft: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3"/>',
    Kultur: '<path d="M4 20h16M6 20V10M10 20V10M14 20V10M18 20V10M3 10l9-6 9 6z"/>',
    Region: '<path d="M3 21h18M5 21V9l7-5 7 5v12M9 21v-6h6v6M9 11h.01M15 11h.01"/>'
  };
  const BAND = { Events: '#F3DCE0', Tourismus: '#DDEBE2', Wirtschaft: '#DFE6F1', Wissenschaft: '#E8E1F1', Kultur: '#F2E6D6', Region: '#E3ECF0' };
  const ARROW = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
  const SPARK = '<svg class="k" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/></svg>';
  let meta = { topics: [], regions: [], roles: {} };
  const load = k => { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } };
  const store = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
  let profile = load(KEY);
  /* ---------- Sprache DE/EN: Oberfläche per Wörterbuch (i18n.js), KI-Antworten auf Englisch über Gemini ---------- */
  let LANG = (load('oberfranken-lang') === 'en') ? 'en' : 'de';
  const LOC = () => LANG === 'en' ? 'en-GB' : 'de-DE';
  function applyLang(root) {
    if (LANG !== 'en' || !window.I18N) return;
    const D = window.I18N, walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT);
    const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const n of nodes) {
      const t = n.nodeValue.trim(); if (!t || t.length > 1500) continue;
      if (D.exact[t]) { n.nodeValue = n.nodeValue.replace(t, D.exact[t]); continue; }
      let v = n.nodeValue; for (const [re, to] of D.patterns) v = v.replace(re, to); if (v !== n.nodeValue) n.nodeValue = v;
    }
    (root || document).querySelectorAll && (root || document).querySelectorAll('[placeholder],[aria-label],[title]').forEach(el => {
      for (const a of ['placeholder', 'aria-label', 'title']) {
        const v = el.getAttribute(a); if (!v) continue;
        let nv = D.exact[v.trim()] || v; if (nv === v) for (const [re, to] of D.patterns) nv = nv.replace(re, to);
        if (nv !== v) el.setAttribute(a, nv);
      }
    });
  }
  const langObs = new MutationObserver(ms => { if (LANG !== 'en') return; langObs.disconnect(); ms.forEach(m => m.addedNodes.forEach(n => { if (n.nodeType === 1) applyLang(n); else if (n.nodeType === 3 && n.parentNode) applyLang(n.parentNode); })); langObs.observe(document.body, { childList: true, subtree: true }); });
  langObs.observe(document.body, { childList: true, subtree: true });
  const toast = m => { const t = $('#toast'); t.textContent = m; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => t.hidden = true, 3000); };
  async function api(path, opts) {
    if (LANG === 'en' && !(opts && opts.body) && path.startsWith('/api/')) path += (path.includes('?') ? '&' : '?') + 'lang=en'; // Server übersetzt seine eigenen Texte
    const r = await fetch(path, opts && opts.body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(opts.body) } : opts);
    if (!r.ok) { let d = 'Fehler'; try { d = (await r.json()).detail; } catch (e) {} throw new Error(d); }
    return r.json();
  }
  const fmt = d => d ? new Date(d.slice(0, 10) + 'T00:00').toLocaleDateString(LANG === 'en' ? 'en-GB' : 'de-DE', { weekday: 'short', day: 'numeric', month: 'short' }) : '';
  const icon = (k, s = 30) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="#3A3A3A" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${ICON[k] || ICON.Events}</svg>`;
  const saved = () => (profile && profile.saved) || [];
  const img = (file, alt) => file ? `<img src="/static/img/${esc(file)}" alt="${esc(alt)}" onerror="this.remove()">` : '';

  /* ---------- Einwilligung (Cookies / Speicher im Browser) ----------
     Notwendig: deine Auswahl hier, Mein Oberfranken (nur wenn du es einrichtest), deine Region.
     Optional: anonyme Statistik. Gezählt wird nur „Tag + Ereignis“, ohne IP, ohne ID. Standard: AUS. */
  const consent = () => { const c = load(CK); if (!c) return null; if (typeof c === 'string') return { stats: c === 'ja', date: '' }; return c; };
  function setConsent(stats) { store(CK, { v: 1, stats: !!stats, date: new Date().toISOString().slice(0, 10) }); }
  function track(key) {
    const c = consent(); if (!c || !c.stats) return; // ohne Einwilligung wird nichts gesendet
    try { fetch('/api/stats', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }), keepalive: true }).catch(() => {}); } catch (e) {}
  }
  function cookieCard(force) {
    const slot = $('#cookie-slot');
    if (!force && consent()) { slot.innerHTML = ''; return; }
    const cur = consent() || { stats: false };
    slot.innerHTML = `<section class="box cookie" aria-label="Cookie-Auswahl"><p class="eyebrow">Datenschutz-Einstellungen</p><h2>Du entscheidest, was gespeichert wird.</h2>
      <p class="small muted">Wir nutzen keine Werbe- oder Tracking-Cookies und speichern keine IP-Adressen. Optional darfst du uns helfen, die Seite zu verbessern.</p>
      <div class="cons">
        <label class="consrow"><input type="checkbox" checked disabled><span><span><b>Notwendig</b> · immer an</span><small>Deine Auswahl hier, „Mein Oberfranken“ (nur wenn du es einrichtest) und deine Region. Alles bleibt in deinem Browser.</small></span></label>
        <label class="consrow"><input type="checkbox" id="ck-stats" ${cur.stats ? 'checked' : ''}><span><span><b>Anonyme Statistik</b> · freiwillig</span><small>Wir zählen nur, wie oft z. B. eine Regionsseite oder der KI-Begleiter genutzt wird, als Summe pro Tag. Keine IP, keine ID, kein Profil.</small></span></label>
      </div>
      <div class="row"><button class="btn" data-ck="nein" type="button">Nur notwendige</button><button class="btn" data-ck="auswahl" type="button">Auswahl speichern</button><button class="btn" data-ck="ja" type="button">Alle akzeptieren</button>
        <a class="small" href="#/datenschutz">Mehr erfahren</a><a class="small" href="#/datenschutz" data-pvjump>Gespeichertes ansehen</a></div></section>`;
    const j = slot.querySelector('[data-pvjump]'); if (j) j.onclick = () => { window.__pvjump = true; if (location.hash === '#/datenschutz') route(); };
    slot.querySelectorAll('[data-ck]').forEach(b => b.onclick = () => {
      const v = b.dataset.ck === 'ja' ? true : b.dataset.ck === 'nein' ? false : $('#ck-stats').checked;
      setConsent(v); slot.innerHTML = '';
      toast(v ? 'Danke! Anonyme Statistik ist an. Du kannst das im Footer jederzeit ändern.' : 'Gespeichert: nur notwendige. Es wird nichts gezählt.');
      if (location.hash === '#/mein') route();
    });
  }

  /* ---------- Region: Profil > eigene Wahl > Vorschlag aus der Verbindung > Bamberg ---------- */
  const RK = 'oberfranken-region';
  const home = () => (profile && profile.region) || (load(RK) || {}).region || 'Bamberg';
  // genauer Ort (eine der 214 Städte, Märkte und Gemeinden; amtliche Liste von Destatis). Leer = nur Region.
  const town = () => (profile && profile.town) || (load(RK) || {}).town || '';
  const homeKey = () => town() || home(); // für Entfernung und Wetter
  const placeBy = n => (meta.places || []).find(p => p[0].toLowerCase() === String(n || '').trim().toLowerCase());
  const placeOptions = () => `<datalist id="place-list">${(meta.places || []).map(p => `<option value="${esc(p[0])}">${esc(p[4])} · ${esc(RLABEL(p[1]))}</option>`).join('')}</datalist>`;
  function setRegion(r, how, t) {
    if (profile) { profile.region = r; profile.town = t || ''; store(KEY, profile); }
    store(RK, { region: r, how, town: t || '' });
  }
  async function guessRegion() {
    if (profile || load(RK)) return;
    try { const g = await api('/api/region-guess'); if (g.region) { store(RK, { region: g.region, how: 'guess' }); route(); toast(`Wir vermuten: ${REGION_NAMES[g.region] || g.region}. Du kannst das oben ändern.`); } } catch (e) {}
  }
  function nearestPlace(lat, lon) {  // nächste Gemeinde (Mittelpunkt), nur im Browser berechnet
    let best = null, bd = 1e9;
    for (const p of meta.places || []) { const d = Math.hypot((lat - p[2]) * 111, (lon - p[3]) * 72); if (d < bd) { bd = d; best = p; } }
    return bd <= 12 ? best : null;
  }
  function nearest(lat, lon) {
    let best = null, bd = 1e9;
    for (const [r, [a, b]] of Object.entries(meta.coords || {})) { const d = Math.hypot((lat - a) * 111, (lon - b) * 72); if (d < bd) { bd = d; best = r; } }
    return bd <= 45 ? best : null;
  }
  function openRegionPicker() {
    const m = $('#modal'); m.hidden = false;
    m.innerHTML = `<div class="dlg" role="dialog" aria-modal="true" aria-label="Region wählen"><h2>Wo bist du unterwegs?</h2>
      <button class="btn primary" type="button" id="rp-geo">📍 Meinen Standort verwenden</button>
      <p class="small muted" style="margin:-6px 0 0">Dein Browser fragt dich. Der nächste Ort wird <b>nur auf deinem Gerät</b> berechnet, dein Standort wird nicht gesendet.</p>
      <label class="lbl" for="rp-town">oder deinen Ort eingeben</label><input class="field" id="rp-town" list="place-list" autocomplete="off" placeholder="z. B. Steinbach am Wald, Pegnitz, Selb" value="${esc(town())}">${placeOptions()}
      <p class="small muted" id="rp-hint" style="margin:-4px 0 0">Alle ${(meta.places || []).length} Städte, Märkte und Gemeinden in Oberfranken (amtliche Liste).</p>
      <label class="lbl" for="rp-sel">oder nur die Region</label><select class="field" id="rp-sel">${meta.regions.map(r => `<option value="${r}"${r === home() ? ' selected' : ''}>${esc(RLABEL(r))}</option>`).join('')}</select>
      <div style="display:flex;justify-content:flex-end;gap:8px"><button class="btn ghost" type="button" id="rp-x">Abbrechen</button><button class="btn" type="button" id="rp-ok">Übernehmen</button></div></div>`;
    $('#rp-x').onclick = () => m.hidden = true;
    $('#rp-town').oninput = () => { const p = placeBy($('#rp-town').value); $('#rp-hint').textContent = p ? `${p[0]}: ${p[4]} im Gebiet ${RLABEL(p[1])}` : `Alle ${(meta.places || []).length} Städte, Märkte und Gemeinden in Oberfranken (amtliche Liste).`; if (p) $('#rp-sel').value = p[1]; };
    $('#rp-ok').onclick = () => {
      const t = $('#rp-town').value.trim(), p = placeBy(t);
      if (t && !p) { toast('Diesen Ort kenne ich in Oberfranken nicht. Bitte aus der Liste wählen.'); return; }
      if (p) setRegion(p[1], 'manual', p[0]); else setRegion($('#rp-sel').value, 'manual', '');
      m.hidden = true; toast(p ? `Dein Ort: ${p[0]}` : `Region: ${RLABEL($('#rp-sel').value)}`); route();
    };
    $('#rp-geo').onclick = () => {
      if (!navigator.geolocation) { toast('Dein Browser unterstützt keine Standortabfrage.'); return; }
      navigator.geolocation.getCurrentPosition(p => {
        const pl = nearestPlace(p.coords.latitude, p.coords.longitude);
        const r = pl ? pl[1] : nearest(p.coords.latitude, p.coords.longitude);
        if (!r) { toast('Du scheinst außerhalb Oberfrankens zu sein. Wähle einfach deinen Ort aus.'); return; }
        setRegion(r, 'geo', pl ? pl[0] : ''); m.hidden = true; toast(pl ? `Dein Ort: ${pl[0]}` : `Region: ${RLABEL(r)}`); route();
      }, () => toast('Standort nicht freigegeben. Wähle einfach eine Region aus.'), { maximumAge: 600000, timeout: 10000 });
    };
  }

  /* ---------- KI-Karten (rot) ---------- */
  const standDate = i => { const d = (i.published || i.created || '').slice(0, 10); return d ? new Date(d + 'T00:00').toLocaleDateString(LOC(), { day: '2-digit', month: '2-digit', year: 'numeric' }) : 'unbekannt'; };
  // Google Maps nur als Link (öffnet Google erst nach Klick, ohne API-Schlüssel)
  const mapsUrl = i => i.lat && i.lon ? `https://www.google.com/maps/dir/?api=1&destination=${i.lat},${i.lon}` : (i.location ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(i.location + ', Oberfranken')}` : '');
  const mapsLink = i => mapsUrl(i) ? `<a href="${esc(mapsUrl(i))}" target="_blank" rel="noopener" title="Route in Google Maps (öffnet Google)">🗺️ Route</a>` : '';
  // Quelle: echte Einträge verlinken direkt auf den Originalartikel. Beispiel-Einträge sind erfunden,
  // ihr Link führt ehrlich gekennzeichnet zur echten Seite des Ortes/Anbieters.
  const isDemo = i => /^bsp-/.test(i.source_id || '') || /\(Beispiel\)/.test(i.source || '');
  const hostOf = u => { try { const x = new URL(u), h = x.hostname.replace(/^www\./, ''); return h === 'ihk.de' ? h + '/' + (x.pathname.split('/')[1] || '') : h; } catch (e) { return ''; } };
  // „Quelle“ führt direkt auf den einzelnen Termin bzw. die Meldung beim Anbieter; nur ohne eigenen Link auf die Website
  const siteOf = i => i.site || (() => { try { const u = new URL(i.url); return u.origin + '/'; } catch (e) { return ''; } })();
  const srcA = (i, txt) => { const s = siteOf(i); return s ? `<a href="${esc(s)}" target="_blank" rel="noopener" title="Website: ${esc(hostOf(s))}">${txt}</a>` : txt; };
  const srcLine = i => {
    const a = i.url ? `<a href="${esc(i.url)}" target="_blank" rel="noopener" data-click="${i.id}" title="${esc(i.url)}">` : '';
    if (isDemo(i)) return `<span title="Erfundener Beispiel-Eintrag des Prototyps">Beispiel-Eintrag · Infos:</span> ${a ? a + esc(hostOf(i.url)) + '</a>' : '–'}`;
    const rk = i.rank ? ` · <span class="rk rk${i.rank}" title="Quellen-Ranking: ${i.rank} von 5 (1 = amtlich). So funktioniert's: siehe Seite „So funktioniert's“">${i.rank <= 2 ? '✓ ' : ''}${esc(i.rank_label || '')}</span>` : '';
    return `Quelle: ${a ? a + esc(i.source || hostOf(i.url)) + '</a>' : srcA(i, esc(i.source || '–'))}${rk}`;
  };
  function card(i) {
    const on = saved().includes(i.id);
    const why = i.why ? `<details class="why"><summary>Warum sehe ich das?</summary><ul>${i.why.map(w => `<li>${esc(w)}</li>`).join('')}</ul></details>` : '';
    const heart = `<button class="heart" type="button" data-save="${i.id}" aria-pressed="${on}" aria-label="${on ? 'Aus Mein Oberfranken entfernen' : 'Merken'}"><svg width="18" height="18" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" fill="none"><path d="M12 21s-7-4.5-9.5-9A5.5 5.5 0 0 1 12 6a5.5 5.5 0 0 1 9.5 6C19 16.5 12 21 12 21z"/></svg></button>`;
    const top = i.img
      ? `<div class="ph"><img src="${esc(i.img.src)}" alt="Symbolbild: ${esc(i.img.caption)}" loading="lazy"><span class="ctag">${esc(i.category)}</span>${i.event_date ? `<span class="cdate">${fmt(i.event_date)}</span>` : ''}${heart}<a class="credit" href="#/bildnachweis" title="Symbolbild · ${esc(i.img.credit)}">${esc(i.img.credit)}</a></div>`
      : `<div class="ph noimg" style="--bg:${BAND[i.category] || '#EEE'}">${icon(i.category, 54)}<span class="ctag">${esc(i.category)}</span>${i.event_date ? `<span class="cdate">${fmt(i.event_date)}</span>` : ''}${heart}<span class="credit dark">${esc(REGION_NAMES[i.region] || i.location || '')}</span></div>`;
    return `<article class="box card" data-src="red">${top}
      <div class="body"><div class="meta"><span>${esc(i.location || '')}</span>${i.km != null ? `<span>· 📍 ${i.km < 3 ? 'bei dir' : 'ca. ' + i.km + ' km'}</span>` : ''}${i.wx ? `<span title="Vorhersage am Termin">· ${i.wx.icon} ${i.wx.tmax}°</span>` : ''}</div>
        <h3>${esc(i.title)}</h3><p class="sum">${esc((LANG === 'en' && i.summary_en) || i.summary || '')}</p>${why}
        <p class="stand" title="Wann die Quelle den Inhalt veröffentlicht hat bzw. wann wir ihn eingesammelt haben">${srcLine(i)} · Stand ${esc(standDate(i))}</p>
        <div class="foot"><span class="ki">✦ KI-Zusammenfassung</span><span class="fl">${mapsLink(i)}${i.url ? `<a href="${esc(i.url)}" target="_blank" rel="noopener" data-click="${i.id}" title="${esc(i.url)}">${isDemo(i) ? 'Infos beim Anbieter' : i.event_date ? 'Zum Termin' : 'Zur Meldung'} ↗</a>` : ''}</span></div>
        <button class="linkbtn" type="button" data-report="${i.id}">Fehler melden</button></div></article>`;
  }
  const newsCard = n => `<article class="box card news" data-src="blue">${(x => x ? `<div class="ph"><img src="${esc(x.src)}" alt="" loading="lazy"><span class="ctag oo">Oberfranken Offensiv</span></div>` : `<div class="band" style="background:var(--blue-soft)">${icon('Wissenschaft')}</div>`)(imgByFile('hochschule-coburg.jpg'))}<div class="body"><h3>${esc(n.title)}</h3><p class="sum">${esc(n.text)}</p><div class="foot"><span>Von innen nach außen · Team Oberfranken</span></div></div></article>`;
  const cards = (list, empty, extra = '') => (list.length || extra) ? `<div class="cards">${extra}${list.map(card).join('')}</div>` : `<p class="empty">${empty}</p>`;
  function bindCards(root = document) {
    root.querySelectorAll('[data-save]').forEach(b => b.onclick = () => toggleSave(+b.dataset.save));
    root.querySelectorAll('[data-click]').forEach(a => a.addEventListener('click', () => api(`/api/items/${a.dataset.click}/click`, { method: 'POST' }).catch(() => {})));
    root.querySelectorAll('[data-report]').forEach(b => b.onclick = () => openReport(+b.dataset.report));
  }
  function toggleSave(id) {
    if (!profile) { openOnboarding(() => toggleSave(id)); return; }
    profile.saved = profile.saved || [];
    const k = profile.saved.indexOf(id);
    if (k >= 0) profile.saved.splice(k, 1); else profile.saved.push(id);
    store(KEY, profile);
    api(`/api/items/${id}/save`, { body: { on: k < 0 } }).catch(() => {});
    toast(k >= 0 ? 'Aus Mein Oberfranken entfernt.' : 'In Mein Oberfranken gemerkt.'); if (k < 0) track('save');
    document.querySelectorAll(`[data-save="${id}"]`).forEach(b => b.setAttribute('aria-pressed', k < 0));
  }

  /* ---------- KI-Begleiter (Chat im Hero) ----------
     Frage -> kurze KI-Antwort + Karten aus unseren Inhalten, Wetter am Tag, Alternativen bei Regen,
     Folgefragen als Chips, „Als Tagesplan speichern“, 👍/👎. Verlauf nur im Speicher (max. 2 Runden). */
  let chatHist = [];
  async function ask(q, target, pageRegion) {
    target.hidden = false;
    target.innerHTML = `<div class="qline"><span class="qb">${esc(q)}</span></div><p class="muted thinking">${SPARK} Ich schaue in die Inhalte aus Oberfranken und ins Wetter …</p>`;
    target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    try {
      const r = await api('/api/ask', { body: { q, home: home(), town: town(), region: pageRegion || '', history: chatHist, lang: LANG } });
      chatHist = [...chatHist, { q, a: r.answer }].slice(-2); track('ask');
      const wx = r.weather ? `<span class="wxb${r.weather.rain ? ' rain' : ''}">${r.weather.icon} ${esc(new Date(r.weather.date + 'T00:00').toLocaleDateString(LOC(), { weekday: 'long', day: 'numeric', month: 'numeric' }))} · ${esc(REGION_NAMES[r.weather.region] || r.weather.region)}: ${esc(r.weather.text)}, bis ${r.weather.tmax} °C</span>` : '';
      const fcDay = d => { const x = new Date(d + 'T00:00'), t = new Date(); t.setHours(0, 0, 0, 0); const n = Math.round((x - t) / 864e5); return n === 0 ? (LANG === 'en' ? 'Today' : 'Heute') : n === 1 ? (LANG === 'en' ? 'Tomorrow' : 'Morgen') : x.toLocaleDateString(LOC(), { weekday: 'long' }); };
      const fc = (r.forecast || []).length > 1 ? `<div class="fcrow">${r.forecast.map(f => `<div class="fc${f.rain ? ' rain' : ''}"><b>${esc(fcDay(f.date))}</b><span class="fi">${f.icon}</span><span>${f.tmax}°</span><small>${esc(f.text)} · ${f.prob} %</small></div>`).join('')}</div>` : '';
      const links = (r.links || []).length ? `<div class="offlinks"><b>Bei den offiziellen Seiten nachsehen:</b>${r.links.map(l => `<a href="${esc(l.link)}" target="_blank" rel="noopener">${esc(l.link.replace(/^https?:\/\/(www\.)?/, ''))} ↗</a>`).join('')}</div>` : '';
      target.innerHTML = `<div class="qline"><span class="qb">${esc(q)}</span><button class="btn sm ghost" type="button" data-close>Schließen</button></div>
        <div class="abox"><span class="kilabel">✦ KI-Antwort</span>${VOICE.canSpeak ? `<button class="speak" type="button" data-speak title="Antwort vorlesen" aria-label="Antwort vorlesen">🔊 Vorlesen</button>` : ''}${fc || wx}<p class="txt">${esc(r.answer)}</p></div>
        ${r.items.length ? cards(r.items, '') : ''}
        ${r.alternatives.length ? `<h3 class="alt-h">🌧️ Falls es regnet: Ideen für drinnen</h3>${cards(r.alternatives, '')}` : ''}
        ${(r.web_sources || []).length ? `<div class="websrc"><b>Quellen</b>${r.web_sources.map(w => `<a href="${esc(w.url)}" target="_blank" rel="noopener" title="${esc(w.url)} · ${esc(w.stufe)}">${w.title && w.title !== w.domain ? `<span class="wt">${esc(w.title)}</span> ` : ''}<span class="wd">${esc(w.domain)}</span> ↗</a>`).join('')}<span class="note">${/eigene Suche/.test(r.engine || '') ? 'Eigene Suche' : 'Websuche über Google'}, nur auf geprüften Seiten · ${esc(r.web_sources[0].stufe)} · abgerufen ${esc((r.fetched_at || '').split(' ').map((x, k) => k ? x : x.split('-').reverse().join('.')).join(' '))}</span></div>` : ''}
        ${links}
        ${r.followups.length ? `<div class="follow"><span class="note">Weiterfragen</span><div class="chips" style="margin:0">${r.followups.map(f => `<button class="chip" type="button" data-fu="${esc(f)}">${esc(f)}</button>`).join('')}</div></div>` : ''}
        <div class="aact">${(r.items.length || r.alternatives.length) && r.in_scope ? `<button class="btn primary" type="button" data-plan>Als Tagesplan speichern</button>` : '<span></span>'}
          <span class="fb"><span class="note">War das hilfreich?</span><button class="iconbtn" type="button" data-fb="up" aria-label="Hilfreich">👍</button><button class="iconbtn" type="button" data-fb="down" aria-label="Nicht hilfreich">👎</button></span></div>
        ${(r.trace || []).length ? `<details class="trace"><summary>Was passiert im Hintergrund?</summary><ol>${r.trace.map(t => `<li>${esc(t)}</li>`).join('')}</ol><a href="#/so-funktionierts">So funktioniert die Plattform →</a></details>` : ''}
        <p class="note">KI-Antwort nur aus Inhalten der Partner und der Redaktion, jede Karte mit Quelle · Wetter: Open-Meteo · ${esc(r.engine || '')} · Deine Frage wird nicht gespeichert.</p>`;
      bindCards(target); typeIn($('.abox .txt', target));
      const sp = $('[data-speak]', target);
      if (sp) { sp.onclick = () => speak(r.answer, sp); if (VOICE.spoken) setTimeout(() => speak(r.answer, sp), 300); }
      VOICE.spoken = false;
      $('[data-close]', target).onclick = () => { target.hidden = true; chatHist = []; };
      target.querySelectorAll('[data-fu]').forEach(b => b.onclick = () => { const inp = target.parentNode.querySelector('[data-ask] input'); if (inp) inp.value = b.dataset.fu; ask(b.dataset.fu, target, pageRegion); track('followup'); });
      if ($('[data-plan]', target)) $('[data-plan]', target).onclick = () => savePlan(q, r);
      target.querySelectorAll('[data-fb]').forEach(b => b.onclick = async () => {
        const fb = b.closest('.fb');
        track('feedback'); if (b.dataset.fb === 'up') { api('/api/ask/feedback', { body: { vote: 'up' } }).catch(() => {}); fb.innerHTML = '<span class="note">Danke für dein Feedback!</span>'; return; }
        fb.innerHTML = `<input class="field" style="padding:6px 10px;width:220px" maxlength="200" placeholder="Was hat gefehlt? (optional)"><button class="btn sm" type="button">Senden</button>`;
        $('button', fb).onclick = async () => { await api('/api/ask/feedback', { body: { vote: 'down', q, note: $('input', fb).value } }).catch(() => {}); fb.innerHTML = '<span class="note">Danke! Die Redaktion schaut sich das anonym an.</span>'; };
      });
    } catch (e) { target.innerHTML = `<p>${esc(e.message)}</p>`; }
  }
  function savePlan(q, r) {
    if (!profile) { openOnboarding(() => savePlan(q, r)); return; }
    const pick = [...r.items, ...r.alternatives].slice(0, 3).map(i => ({ id: i.id, title: i.title, location: i.location, event_date: i.event_date, url: i.url, site: i.site, source: i.source }));
    profile.plans = [{ id: Date.now().toString(36), title: q, when: r.label || '', weather: r.weather ? `${r.weather.icon} ${r.weather.text}, bis ${r.weather.tmax} °C` : '', steps: pick }, ...(profile.plans || [])].slice(0, 10);
    store(KEY, profile);
    toast('Tagesplan in Mein Oberfranken gespeichert.'); track('plan');
  }
  /* ---------- Sprachassistent: sprechen statt tippen, Antwort vorlesen ---------- */
  // Spracheingabe: Web Speech API des Browsers (Chrome/Edge/Safari). Vorlesen: speechSynthesis, läuft im Browser.
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const VOICE = { canListen: !!SR, canSpeak: 'speechSynthesis' in window, rec: null, spoken: false };
  function voiceOk(go) {
    let ok = false; try { ok = localStorage.getItem('oberfranken-voice-ok') === '1'; } catch (e) {}
    if (ok) return go();
    const m = $('#modal'); m.hidden = false;
    m.innerHTML = `<div class="dlg" role="dialog" aria-modal="true" aria-label="Spracheingabe"><h2>Frage sprechen</h2>
      <p>Dein Browser wandelt deine Sprache in Text um. In Chrome und Edge passiert das über einen Dienst von Google bzw. Microsoft, in Safari über Apple. <b>Wir bekommen nur den fertigen Text</b>, keine Aufnahme, und speichern auch den nicht.</p>
      <p class="small muted">Der Browser fragt dich gleich, ob er das Mikrofon nutzen darf. Du kannst jederzeit wieder tippen.</p>
      <div style="display:flex;justify-content:flex-end;gap:8px"><button class="btn ghost" type="button" id="v-no">Lieber tippen</button><button class="btn primary" type="button" id="v-ok">Mikrofon verwenden</button></div></div>`;
    $('#v-no').onclick = () => m.hidden = true;
    $('#v-ok').onclick = () => { try { localStorage.setItem('oberfranken-voice-ok', '1'); } catch (e) {} m.hidden = true; go(); };
  }
  // Klare Meldung statt stillem Fehler: was ist los und was kann man tun
  function micProblem(code) {
    const EN = LANG === 'en';
    const file = location.protocol === 'file:';
    const M = {
      unsupported: EN ? 'Voice input works in Chrome, Edge and Safari. In this browser, please type your question.' : 'Spracheingabe gibt es in Chrome, Edge und Safari. In diesem Browser bitte tippen.',
      'not-allowed': file ? (EN ? 'The browser blocks the microphone for files opened from your computer. Open the page via the link (http/https), e.g. the online demo.' : 'Bei einer Datei vom Computer blockiert der Browser das Mikrofon. Öffne die Seite über den Link (http/https), z. B. die Online-Demo.')
        : (EN ? 'Microphone access is blocked. Click the lock icon next to the address, allow the microphone and try again.' : 'Mikrofon ist blockiert. Klick auf das Schloss neben der Adresse, erlaube das Mikrofon und versuch es nochmal.'),
      'audio-capture': EN ? 'No microphone found. Please connect one or type your question.' : 'Kein Mikrofon gefunden. Bitte anschließen oder die Frage tippen.',
      network: EN ? 'Speech recognition needs an internet connection (your browser uses Google, Microsoft or Apple for it). Please check your connection or type.' : 'Die Spracherkennung braucht Internet (der Browser nutzt dafür Google, Microsoft oder Apple). Bitte Verbindung prüfen oder tippen.',
      'no-speech': EN ? "I didn't hear anything. Please try again." : 'Ich habe nichts gehört. Versuch es nochmal.',
      insecure: EN ? 'The microphone only works on secure pages (https or localhost).' : 'Das Mikrofon funktioniert nur auf sicheren Seiten (https oder localhost).',
      'service-not-allowed': EN ? 'This browser does not offer speech recognition (e.g. Brave, Opera, Vivaldi). Please use Chrome, Edge or Safari, or type.' : 'Dieser Browser bietet keine Spracherkennung an (z. B. Brave, Opera, Vivaldi). Bitte Chrome, Edge oder Safari nutzen oder tippen.',
      busy: EN ? 'The microphone is being used by another app (e.g. Teams or Zoom). Close it and try again.' : 'Das Mikrofon wird gerade von einer anderen App benutzt (z. B. Teams oder Zoom). Schließen und nochmal versuchen.',
      'language-not-supported': EN ? 'Speech recognition for this language is not available in this browser.' : 'Spracherkennung für diese Sprache gibt es in diesem Browser nicht.',
    };
    toast(M[code] || (EN ? 'Voice input did not work. Please type your question.' : 'Spracheingabe hat nicht geklappt. Bitte tippe die Frage.'));
  }
  VOICE.problem = micProblem;
  // Vorher einmal um Erlaubnis fürs Mikrofon fragen: so erscheint der normale Browser-Dialog und Fehler sind eindeutig
  async function micPermission() {
    if (!window.isSecureContext && location.protocol !== 'file:') return 'insecure';
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return null;
    try { const st = await navigator.mediaDevices.getUserMedia({ audio: true }); st.getTracks().forEach(t => t.stop()); return null; }
    catch (e) { const n = e && e.name; return n === 'NotFoundError' || n === 'OverconstrainedError' ? 'audio-capture' : (n === 'NotAllowedError' || n === 'SecurityError') ? 'not-allowed' : (n === 'NotReadableError' || n === 'AbortError') ? 'busy' : null; }
  }
  VOICE.permission = micPermission;
  function listen(inp, btn, done) {
    if (!SR) { micProblem('unsupported'); return; }
    if (VOICE.rec) { VOICE.rec.stop(); return; }
    if (VOICE.starting) return; // Doppelklick: nicht zweimal starten
    voiceOk(async () => {
      VOICE.starting = true;
      const bad = await micPermission();
      if (bad) { VOICE.starting = false; micProblem(bad); return; }
      const rec = new SR(); VOICE.rec = rec;
      rec.lang = LANG === 'en' ? 'en-GB' : 'de-DE'; rec.interimResults = true; rec.maxAlternatives = 1;
      let finalText = '', heard = '';
      const ph = inp.placeholder;
      btn.classList.add('on'); btn.setAttribute('aria-label', LANG === 'en' ? 'Stop listening' : 'Zuhören beenden'); inp.placeholder = LANG === 'en' ? 'Listening …' : 'Ich höre zu …';
      rec.onresult = e => { let t = ''; for (const r of e.results) { t += r[0].transcript; if (r.isFinal) finalText = t; } heard = t; inp.value = t; };
      rec.onerror = e => { if (e.error !== 'aborted') micProblem(e.error); };
      rec.onend = () => {
        VOICE.rec = null; VOICE.starting = false; inp.placeholder = ph;
        btn.classList.remove('on'); btn.setAttribute('aria-label', LANG === 'en' ? 'Ask by voice' : 'Frage sprechen');
        const t = (finalText || heard).trim(); if (t) done(t); // nur Gesprochenes abschicken, nie alten Text im Feld
      };
      try { rec.start(); VOICE.starting = false; track('voice'); } catch (e) { VOICE.rec = null; VOICE.starting = false; inp.placeholder = ph; btn.classList.remove('on'); micProblem(''); }
    });
  }
  // natürlichste verfügbare Stimme wählen (Online-/„Natural“-Stimmen zuerst), sonst die erste passende
  function bestVoice() {
    const vs = (window.speechSynthesis && speechSynthesis.getVoices()) || [], lg = LANG === 'en' ? 'en' : 'de';
    const own = vs.filter(x => (x.lang || '').toLowerCase().startsWith(lg));
    const pref = [/natural/i, /online/i, /google/i, /katja|conrad|amala|seraphina|florian|anna|petra|markus|helena/i];
    for (const re of pref) { const v = own.find(x => re.test(x.name)); if (v) return v; }
    return own[0] || null;
  }
  if (window.speechSynthesis) try { speechSynthesis.getVoices(); speechSynthesis.onvoiceschanged = () => {}; } catch (e) {}
  function speak(text, btn, after) {
    if (!VOICE.canSpeak) return;
    const s = window.speechSynthesis;
    if (s.speaking) { s.cancel(); if (btn) btn.classList.remove('on'); return; }
    const u = new SpeechSynthesisUtterance(text.replace(/\[\d+\]/g, ''));
    u.lang = LANG === 'en' ? 'en-GB' : 'de-DE';
    try { const v = bestVoice(); if (v) u.voice = v; } catch (e) {}
    u.rate = 1.02;
    u.onend = u.onerror = () => { if (btn) btn.classList.remove('on'); if (after) after(); };
    if (btn) btn.classList.add('on');
    s.speak(u); track('speak');
  }
  const askForm = (ph, chips) => `<form class="ask" data-ask>${SPARK}<input placeholder="${esc(ph)}" autocomplete="off" aria-label="Frage an Oberfranken"><button type="button" class="mic" data-mic aria-label="Frage sprechen" title="Frage sprechen"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg></button><button type="submit" aria-label="Fragen">${ARROW}</button></form>
    <div class="chips">${chips.map(c => `<button class="chip" type="button" data-q="${esc(c[1] || c)}">${esc(c[0] || c)}</button>`).join('')}</div>`;
  function bindAsk(root, target, pageRegion) {
    const f = $('[data-ask]', root), inp = $('input', f);
    f.addEventListener('submit', e => { e.preventDefault(); if (inp.value.trim()) ask(inp.value.trim(), target, pageRegion); });
    const mic = $('[data-mic]', f);
    if (mic) mic.onclick = () => listen(inp, mic, text => { VOICE.spoken = true; ask(text, target, pageRegion); });
    root.querySelectorAll('[data-q]').forEach(b => b.onclick = () => { inp.value = b.dataset.q; ask(b.dataset.q, target, pageRegion); });
  }
  async function weatherLine(region) {
    let w = {}; try { w = await api('/api/weather?region=' + encodeURIComponent(region)); } catch (e) {}
    return w.temp != null ? `${w.temp} °C, ${w.text}` : 'Wetter gerade nicht verfügbar';
  }
  const whereTxt = n => ({ Fichtelgebirge: 'im Fichtelgebirge', Frankenwald: 'im Frankenwald', 'Obermain-Jura': 'am Obermain', 'Fränkische Schweiz': 'in der Fränkischen Schweiz' }[n] || 'in ' + n);
  function greet() { const h = new Date().getHours(); return h < 11 ? 'Guten Morgen' : h < 18 ? 'Hallo' : 'Guten Abend'; }

  /* ---------- Begleiter ---------- */
  const plan = { interests: ['Kultur & Stadt'], half: false, transit: true };
  async function renderPlan() {
    const box = $('#plan-out'); if (!box) return;
    box.innerHTML = '<p class="muted">Ich stelle deinen Tag zusammen …</p>';
    const region = $('#plan-region').value;
    try {
      const r = await api(`/api/plan?interests=${encodeURIComponent(plan.interests.join(','))}&region=${encodeURIComponent(region)}&half=${plan.half}&transit=${plan.transit}`);
      box.innerHTML = `<div class="planbox">${(r.meta || []).map(m => `<span class="meta">${esc(m)}</span>`).join('')}<h3 style="margin-top:6px">${esc(r.title)}</h3><p class="muted">${esc(r.intro)}</p></div>
        ${r.steps.length ? `<h3 style="font-size:20px;font-weight:600">Dein Tag, Schritt für Schritt</h3>${r.steps.map(s => `<div class="box step"><b>${esc(s.t)}</b><span>${esc(s.item ? s.item.title + ': ' : '')}${esc(s.text)}</span>${s.item ? `<span class="src">${esc(s.item.location || '')}${s.item.event_date ? ' · ' + fmt(s.item.event_date) : ''} · ${s.item.url ? `<a href="${esc(s.item.url)}" target="_blank" rel="noopener">Quelle: ${esc(s.item.source)}</a>` : esc(s.item.source)}</span>` : ''}</div>`).join('')}` : ''}
        <div id="plan-check" hidden></div>
        ${r.steps.length ? `<button class="btn primary block" type="button" id="plan-check-btn">Was sollte ich vor dem Ausflug prüfen?</button>` : ''}
        <p class="note">Plan nur aus vorhandenen Inhalten · ${esc(r.engine || '')} · deine Auswahl wird nicht gespeichert</p>`;
      if ($('#plan-check-btn')) $('#plan-check-btn').onclick = () => { const c = $('#plan-check'); c.hidden = false; c.innerHTML = `<div class="hint"><b>Vor dem Ausflug prüfen</b><ul style="margin:8px 0 0;padding-left:18px">${r.checklist.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`; };
    } catch (e) { box.innerHTML = `<p class="empty">${esc(e.message)}</p>`; }
  }

  /* ---------- Bilder, Karte, Wetter-Stimmung ---------- */
  let IMGS = null, MAP = null;
  const images = async () => IMGS || (IMGS = await api('/api/images').catch(() => []));
  const mapData = async () => MAP || (MAP = await fetch('/static/oberfranken-map.json').then(r => r.json()).catch(() => null));
  const imgByFile = f => (IMGS || []).find(x => x.big.endsWith('/' + f));
  // Wetter darf die Seite nie aufhalten: nach 2,5 s ohne Antwort geht es ohne Wetter weiter
  async function getWx(region, t = '') { try { return await Promise.race([api('/api/weather?region=' + encodeURIComponent(region) + (t ? '&town=' + encodeURIComponent(t) : '')), new Promise(r => setTimeout(() => r({}), 2500))]); } catch (e) { return {}; } }
  function forcedMood() { const m = /[?&]wetter=(regen|sonne)/.exec(location.search); return m ? m[1] : null; } // Demo: ?wetter=regen
  function heroImage(region, rain) {
    const list = IMGS || [];
    const mood = rain ? 'rain' : 'sun';
    return list.find(x => x.region === region && x.mood === mood) || list.find(x => x.mood === mood && x.region === 'Bamberg') || list.find(x => x.mood === mood) || list[0];
  }
  const TILES = [['Wunsiedel', 'Fichtelgebirge', 'Granit, Wald und Weitblick', 'fichtelsee.jpg'], ['Kronach', 'Frankenwald', 'Täler, Flößer und Festungen', 'kronach-festung.jpg'],
    ['Lichtenfels', 'Obermain-Jura', 'Gottesgarten am Main', 'staffelberg.jpg'], ['Forchheim', 'Fränkische Schweiz', 'Felsen, Burgen, Brauereien', 'tuechersfeld.jpg']];
  function mapSVG(m, today, dots) {
    const P = (lat, lon) => [(lon - m.proj.minlon) * m.proj.kx * m.proj.s, (m.proj.maxlat - lat) * m.proj.s];
    const regs = Object.entries(m.regions).map(([r, d]) => `<a href="#/region/${r}" class="mreg" data-r="${r}" aria-label="${esc(RLABEL(r))}${today[r] ? ', ' + today[r].tmax + ' Grad, ' + today[r].text : ''}"><path d="${d}"/></a>`).join('');
    const labels = Object.entries(m.labels).map(([r, [x, y]]) => { const w = today[r]; return `<g class="mlab" transform="translate(${x},${y})"><text y="-4">${esc(r)}</text><title>${esc(RLABEL(r))}</title>${w ? `<text class="mw" y="26">${w.icon} ${w.tmax}°</text>` : ''}</g>`; }).join('');
    const pts = dots.filter(d => d.lat && d.lon).map((d, k) => { const [x, y] = P(d.lat, d.lon); return `<a href="${d.url ? esc(d.url) : '#/region/' + d.region}" ${d.url ? 'target="_blank" rel="noopener"' : ''} class="mdot" style="--k:${k}" aria-label="${esc(d.title)}, ${esc(d.location || '')}, ${fmt(d.event_date)}"><circle cx="${x.toFixed(0)}" cy="${y.toFixed(0)}" r="9"/><title>${esc(d.title)} · ${esc(d.location || '')} · ${fmt(d.event_date)}</title></a>`; }).join('');
    return `<svg viewBox="${m.viewBox}" class="omap" role="group" aria-label="Karte von Oberfranken mit den Regionen. Die gleichen Regionen gibt es darunter auch als Liste.">${regs}${labels}${pts}</svg>`;
  }

  /* ---------- Bewegung: sanftes Einblenden, Skelett beim Laden ---------- */
  const io = 'IntersectionObserver' in window ? new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { rootMargin: '0px 0px -8% 0px' }) : null;
  function reveal(root = document) {
    if (!io) return;
    root.querySelectorAll('main > section, .cards > article, .tiles > a, .know > article').forEach((el, i) => { if (el.classList.contains('rv')) return; el.classList.add('rv'); el.style.setProperty('--d', (i % 6) * 60 + 'ms'); io.observe(el); });
  }
  function skeleton() {
    $('#view').innerHTML = `<div class="wrap sk-wrap" aria-hidden="true"><div class="sk-hero"><div><i class="sk" style="width:40%"></i><i class="sk h1"></i><i class="sk h1" style="width:70%"></i><i class="sk" style="width:90%"></i><i class="sk pill"></i></div><i class="sk img"></i></div>
      <div class="cards">${'<div class="box sk-card"><i class="sk img"></i><i class="sk" style="width:60%"></i><i class="sk"></i><i class="sk" style="width:80%"></i></div>'.repeat(3)}</div></div>`;
  }
  function typeIn(el) {
    if (!el || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const words = el.textContent.split(' '); if (words.length < 4) return;
    el.textContent = ''; let k = 0;
    const step = Math.max(12, Math.min(40, 1100 / words.length));
    const t = setInterval(() => { el.textContent += (k ? ' ' : '') + words[k++]; if (k >= words.length) clearInterval(t); }, step);
  }

  /* ---------- Startseite ---------- */
  async function pageStart() {
    const myRoute = routeSeq;
    const region = home();
    const topics = profile ? profile.topics : ['Tourismus', 'Events', 'Kultur'];
    const name = profile && profile.nick ? ' ' + profile.nick : '';
    const [feed, wissen, news, start, w, , m, today, wiss, wirt] = await Promise.all([
      api(`/api/feed?topics=${encodeURIComponent(topics.join(','))}&region=${encodeURIComponent(region)}`),
      api('/api/curated?slot=wissen'), api('/api/curated?slot=news'), api('/api/curated?slot=start'), getWx(region, town()), images(), mapData(), Promise.race([api('/api/today').catch(() => ({})), new Promise(r => setTimeout(() => r({}), 2500))]),
      api('/api/items?topic=Wissenschaft&home=' + encodeURIComponent(homeKey())), api('/api/items?topic=Wirtschaft&home=' + encodeURIComponent(homeKey()))]);
    const fm = forcedMood();
    const rain = fm ? fm === 'regen' : !!w.rain;
    const hi = heroImage(region, rain);
    const wtxt = fm ? `Demo-Ansicht: ${fm === 'regen' ? 'Regen' : 'Sonne'}` : w.temp != null ? `${w.temp} °C, ${w.text}` : '';
    const where = town() || REGION_NAMES[region] || region;
    const now = new Date().toLocaleDateString(LOC(), { weekday: 'short', day: 'numeric', month: 'short' });
    const chips = rain
      ? [['Drinnen entdecken', 'Was kann ich heute bei Regen drinnen machen?'], ['Kultur & Führungen', 'Welche Führungen und Konzerte gibt es am Wochenende?'], ['Mit Kindern drinnen', 'Was kann ich am Wochenende mit Kindern bei Regen machen?'], ['Jobs finden', 'Jobs und Karriere in Oberfranken']]
      : [['Am Samstag Rad fahren', 'Ich möchte am Samstag Fahrrad fahren'], ['Ausflug planen', 'Was kann ich am Wochenende unternehmen?'], ['Jobs finden', 'Jobs und Karriere in Oberfranken'], ['Veranstaltungen entdecken', 'Was ist am Wochenende los?']];
    const innov = start.find(s => s.id === 'innovation') || { title: 'Oberfranken ist Innovationsregion', text: '' };
    const innovItems = [...wiss, ...wirt].sort((a, b) => (a.event_date || '9') < (b.event_date || '9') ? -1 : 1);
    if (myRoute !== routeSeq) return; // inzwischen woanders hin navigiert
    $('#view').innerHTML = `
    <div class="wrap">
      <section class="hero${rain ? ' rain' : ''}">
        <div>
          <div class="hello"><span>${greet()}${esc(name)}.</span><span class="pill">${esc(now)}</span><button class="pill pillbtn" type="button" id="region-pill" title="Ort ändern">📍 ${esc(where)}${wtxt ? ' · ' + esc(wtxt) : ''} <u>ändern</u></button></div>
          <p class="eyebrow mood">${rain ? `🌧️ Regenwetter ${esc(agentWhere(where))}? Hier sind Ideen für drinnen.` : (w.temp != null ? `${/sonnig/.test(w.text || '') ? '☀️' : '⛅'} ${w.temp}° ${esc(agentWhere(where))}, ${esc(w.text)}${/sonnig|bewölkt/.test(w.text || '') ? ': gut für draußen' : ''}` : 'Dein digitaler Wegweiser')}</p>
          <h1 style="margin-top:10px">Dein Oberfranken.<br>Persönlich geplant.</h1>
          <p class="lead">Regionales Wissen als Grundlage. Dein persönlicher Begleiter macht daraus einen Ausflug, der zu deinen Interessen, deinem Zeitbudget und dem Wetter passt. Wie kann ich dir heute helfen?</p>
          ${askForm(rain ? 'z. B. Was kann ich heute drinnen machen?' : 'z. B. Ich möchte am Samstag Fahrrad fahren', chips)}
          <div class="ctas"><button class="btn primary" type="button" data-go="regionen">Region entdecken ${ARROW}</button><button class="btn" type="button" data-go="begleiter">Mit dem Begleiter planen ${ARROW}</button></div>
        </div>
        <figure class="photo heroimg" style="margin:0">${hi ? `<img src="${esc(hi.big)}" alt="${esc(hi.caption)}" fetchpriority="high">` : ''}
          <figcaption class="cap"><span><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12z"/><circle cx="12" cy="9" r="2.5"/></svg>${esc(hi ? hi.caption : 'Oberfranken')}</span>${hi ? `<a class="credit" href="#/bildnachweis">${esc(hi.credit)}</a>` : ''}</figcaption>
          ${w.temp != null ? `<span class="wxfloat">${rain ? '🌧️' : /sonnig/.test(w.text || '') ? '☀️' : '⛅'} ${w.temp}°</span>` : ''}</figure>
      </section>
      <section class="box answer" id="answer" hidden></section>
    </div>
    <main class="wrap">
      <section id="wissen">
        <div class="sec-head" style="display:block"><h2>Wissen aus der Region. Vorschläge für dich.</h2><p class="sub">Geprüftes Wissen vom Team Oberfranken und dein persönlicher Tagesplan aus echten Terminen der Region, jeweils mit Quelle.</p></div>
        <div class="split">
          <div data-src="blue"><p class="col-title"><i class="code blue"></i>Regionales Wissen</p><p class="small muted" style="margin-top:6px">Vom Team Oberfranken: redaktionelle Inhalte mit Links zu offiziellen Tourismusinformationen.</p>
            <div class="know">${wissen.map(k => `<article class="box kcard"><div class="img">${img(k.image, k.title)}</div><span class="cat">${esc(k.cat)}</span><h3>${esc(k.title)}</h3><p>${esc(k.text)}</p>${k.link ? `<a href="${esc(k.link)}" target="_blank" rel="noopener">Offizielle Infos ${ARROW}</a>` : ''}</article>`).join('')}</div></div>
          <div class="box planner" id="begleiter" data-src="red">
            <div class="top"><span class="ic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg></span><div><h3>Dein persönlicher Tagesplan</h3><span class="eyebrow" style="font-size:10.5px">Begleiter · aus echten Inhalten der Region</span></div></div>
            <p class="q">1. Was interessiert dich?</p>
            <div class="chips" id="plan-int" style="margin:0">${['Kultur & Stadt', 'Natur & Ruhe', 'Familienzeit', 'Aktiv & Rad'].map(i => `<button class="chip" type="button" data-int="${i}" aria-pressed="${plan.interests.includes(i)}">${i}</button>`).join('')}</div>
            <p class="q">2. Was passt zu deinem Tag?</p>
            <div class="checks"><label><input type="checkbox" id="plan-half" ${plan.half ? 'checked' : ''}> Nur ein halber Tag</label><label><input type="checkbox" id="plan-transit" ${plan.transit ? 'checked' : ''}> Mit Bus und Bahn</label>
              <label>Region <select class="field" id="plan-region" style="width:auto;padding:6px 10px">${['', ...meta.regions].map(r => `<option value="${r}" ${r === home() ? 'selected' : ''}>${r ? esc(RLABEL(r)) : 'ganz Oberfranken'}</option>`).join('')}</select></label></div>
            <div id="plan-out" style="display:flex;flex-direction:column;gap:12px"></div>
          </div>
        </div>
      </section>
      <section data-src="red"><div class="sec-head"><div><h2>${profile && profile.nick ? `Hi ${esc(profile.nick)}, das ist für dich` : 'Für dich ausgesucht'}</h2><p class="sub">${esc(topics.join(' · '))} · ${esc(where)} zuerst · automatisch aus den Regionalseiten</p></div></div>
        ${cards(feed.for_you.slice(0, 6), 'Noch keine passenden Inhalte.', news.length ? newsCard(news[0]) : '')}</section>
      <section><div class="sec-head"><h2>${new Date().getDay() === 0 ? 'Nächstes' : 'Dieses'} Wochenende in Oberfranken</h2><span class="note">← wischen →</span></div><div class="scroller">${feed.weekend.length ? `<div class="cards row">${feed.weekend.slice(0, 8).map(card).join('')}</div>` : '<p class="empty">Am Wochenende ist noch nichts eingetragen.</p>'}</div></section>
      <section id="regionen"><div class="sec-head"><div><h2>Die Regionen entdecken</h2><p class="sub">Tippe auf eine Region · rote Punkte = Termine am Wochenende · Wetter heute</p></div><a class="btn sm" href="#/oberfranken">Mehr über Oberfranken →</a></div>
        <div class="mapgrid"><div class="box mapbox">${m ? mapSVG(m, today, feed.weekend) : ''}<p class="note mapnote">${m ? esc(m.attribution) : ''} · Wetter: Open-Meteo</p></div>
          <div class="tiles">${TILES.map(([r, n, t, f]) => { const x = imgByFile(f); return `<a class="tile" href="#/region/${r}">${x ? `<img src="${esc(x.src)}" alt="${esc(x.caption)}" loading="lazy">` : ''}<span class="tt"><b>${n}</b><span>${t}</span></span>${today[r] ? `<span class="tw">${today[r].icon} ${today[r].tmax}°</span>` : ''}</a>`; }).join('')}</div></div></section>
      <section class="innov" data-src="blue"><div class="ihead"><span class="trophy" aria-hidden="true"><svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/></svg></span>
          <div><p class="eyebrow" style="color:#CFE3EA">Von innen nach außen · Team Oberfranken</p><h2>${esc(innov.title)}</h2><p>${esc(innov.text)}${innov.link ? ` <a href="${esc(innov.link)}" target="_blank" rel="noopener" style="color:inherit">Quelle: ${esc(innov.source || 'Pressemitteilung')} ↗</a>` : ''}</p></div></div>
        <div class="chips" id="innov-f">${[['alle', 'Alle'], ['Wissenschaft', 'Forschung & Hochschulen'], ['Wirtschaft', 'Unternehmen & Karriere'], ['monat', 'Nächste 30 Tage']].map(([k, l], i) => `<button class="chip" type="button" data-if="${k}" aria-pressed="${i === 0}">${l}</button>`).join('')}</div>
        <div id="innov-list"></div></section>
      <section class="forwho"><div class="sec-head"><div><h2>Für wen ist Oberfranken da?</h2><p class="sub">Eine Plattform, drei Wege hinein. Alles mit Quelle, nichts gekauft.</p></div></div>
        <div class="fwgrid">
          <a class="box fwcard" href="#/leben"><span class="fwi">🧭</span><b>Ich will hierher ziehen oder mich weiterentwickeln</b><span>Arbeit, Studium, Ausbildung, Ankommen: die offiziellen Stellen und echte Termine.</span><u>Leben & weiterkommen →</u></a>
          <a class="box fwcard" href="#/partner"><span class="fwi">🏭</span><b>Wir sind ein Unternehmen oder eine Einrichtung</b><span>Stellen, Ausbildung und Termine anbinden, mit Prüfsiegel statt Werbung.</span><u>Teil werden →</u></a>
          <a class="box fwcard" href="#/so-funktionierts"><span class="fwi">🔍</span><b>Ich will wissen, wie das funktioniert</b><span>Quellen, Ranking, KI und Datenschutz: jeder Schritt mit Live-Zahlen.</span><u>So funktioniert's →</u></a>
        </div></section>
      ${vsSection()}
      <section class="app" id="app"><div><p class="eyebrow">Die Region passt in deine Tasche</p><h2 style="margin-top:8px">Dein Oberfranken. Auch unterwegs.</h2><p>Die geplante App bringt dieselben regionalen Inhalte und den persönlichen Begleiter aufs Smartphone. Inspiration zu Hause, Orientierung unterwegs.</p><p class="small">App-Konzept · noch keine Store-Links. Auf dem Handy siehst du unten schon die App-Leiste.</p><div style="margin-top:18px"><button class="btn" type="button" data-go="begleiter">„Frag mich“ im Browser ausprobieren ${ARROW}</button></div></div>
        <div class="phone" aria-hidden="true"><div class="scr"><b>oberfranken</b><b style="font-size:19px">Was hast du heute vor?</b><div class="img">${(x => x ? `<img src="${esc(x.src)}" alt="">` : '')(imgByFile('fichtelsee.jpg'))}</div><b style="font-size:14px">Deine nächste Auszeit</b><span class="note">Fichtelsee · ${today.Wunsiedel ? today.Wunsiedel.icon + ' ' + today.Wunsiedel.tmax + '°' : 'Entdecken · Planen · Erleben'}</span><span class="ask2">💬 Frag mich</span></div></div></section>
      <section class="box transp"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6z"/></svg><div><h2>Bewusst einfach. Transparent von Anfang an.</h2>
        <p>KI-Texte sind gekennzeichnet und verlinken auf die Quelle (EU AI Act, Art. 50). Kein Konto, keine E-Mail, keine IP-Speicherung: dein Profil bleibt in deinem Browser. <a href="#/datenschutz">So schützen wir deine Daten</a> · Fotos mit freien Lizenzen, siehe <a href="#/bildnachweis">Bildnachweis</a>.</p></div></section>
    </main>`;
    bindAsk($('.hero'), $('#answer')); $('#region-pill').onclick = openRegionPicker;
    document.querySelectorAll('#plan-int [data-int]').forEach(b => b.onclick = () => { const i = b.dataset.int, k = plan.interests.indexOf(i); if (k >= 0) { if (plan.interests.length > 1) plan.interests.splice(k, 1); } else plan.interests.push(i); b.parentNode.querySelectorAll('[data-int]').forEach(x => x.setAttribute('aria-pressed', plan.interests.includes(x.dataset.int))); renderPlan(); });
    $('#plan-half').onchange = e => { plan.half = e.target.checked; renderPlan(); };
    $('#plan-transit').onchange = e => { plan.transit = e.target.checked; renderPlan(); };
    $('#plan-region').onchange = renderPlan;
    const drawInnov = f => {
      const lim = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);
      const list = innovItems.filter(i => f === 'alle' || i.category === f || (f === 'monat' && i.event_date && i.event_date.slice(0, 10) <= lim));
      $('#innov-list').innerHTML = cards(list.slice(0, 6), 'Gerade keine Einträge in dieser Auswahl.'); bindCards($('#innov-list')); reveal($('#innov-list'));
    };
    document.querySelectorAll('#innov-f [data-if]').forEach(b => b.onclick = () => { document.querySelectorAll('#innov-f [data-if]').forEach(x => x.setAttribute('aria-pressed', x === b)); drawInnov(b.dataset.if); });
    drawInnov('alle');
    bindGo(); bindCards(); renderPlan(); reveal();
  }
  const agentWhere = n => ({ Fichtelgebirge: 'im Fichtelgebirge', Frankenwald: 'im Frankenwald', 'Obermain-Jura': 'am Obermain', 'Fränkische Schweiz': 'in der Fränkischen Schweiz' }[n] || 'in ' + n);

  async function pageAbout() {
    const myRoute = routeSeq;
    const info = await api('/api/info').catch(() => ({ sources: [], trusted: {} }));
    if (myRoute !== routeSeq) return;
    const dt = s => s ? new Date(s.replace(' ', 'T')).toLocaleString(LOC(), { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '–';
    const host = u => String(u).replace(/^https?:\/\//, '').split('/')[0];
    const T = info.trusted || {};
    $('#view').innerHTML = `<main class="wrap" style="padding-top:24px">
      <section class="about-hero"><p class="eyebrow">Regierungsbezirk in Bayern</p><h1>Das ist Oberfranken</h1>
        <p class="lead">Der Norden Bayerns zwischen Thüringen, Sachsen und Tschechien: Mittelgebirge wie Fichtelgebirge und Frankenwald, die Fränkische Schweiz, Welterbe in Bamberg und Bayreuth und vier Hochschulstandorte.</p>
        <div class="facts"><div><b>${((meta.places_meta || {}).einwohner || 1055758).toLocaleString(LOC())}</b><span>Einwohner (31.12.2024, Destatis)</span></div><div><b>${(meta.places || []).length || 214}</b><span>Städte, Märkte und Gemeinden in 9 Landkreisen + 4 kreisfreien Städten</span></div><div><b>Bayreuth</b><span>Sitz der Regierung</span></div><div><b>4</b><span>Hochschulen: Bayreuth, Bamberg, Coburg, Hof</span></div></div>
        <p class="note">Quelle: <a href="https://www.destatis.de/DE/Themen/Laender-Regionen/Regionales/Gemeindeverzeichnis/_inhalt.html" target="_blank" rel="noopener">Statistisches Bundesamt, Gemeindeverzeichnis (GV-ISys)</a>, Gebietsstand 30.06.2026, Bevölkerung 31.12.2024 (Basis Zensus 2022), Datenlizenz Deutschland – Namensnennung 2.0</p></section>
      <section id="orte"><div class="sec-head"><div><h2>Alle Städte, Märkte und Gemeinden</h2><p class="sub">Die amtliche Liste. Tipp: auf einen Ort klicken, um ihn als deinen Ort zu wählen (Entfernungen und Wetter gelten dann genau dafür).</p></div></div>
        <input class="field" id="pl-q" placeholder="Ort suchen, z. B. Pegnitz" autocomplete="off" style="max-width:420px;margin-bottom:14px" aria-label="Ort suchen">
        <div class="plgroups" id="pl-groups"></div></section>
      <section><div class="sec-head"><h2>Die Landkreise und Städte</h2></div><div class="rgrid">${meta.regions.map(r => `<a class="box rcard" href="#/region/${r}"><b>${esc(r)}</b><span>${esc(REGION_NAMES[r] !== r ? REGION_NAMES[r] : 'Landkreis und Stadt')}</span></a>`).join('')}</div></section>
      <section><div class="sec-head"><div><h2>Woher die Inhalte kommen</h2><p class="sub">Zuletzt eingesammelt: ${esc(dt(info.last_run))} · automatisch alle ${info.interval_min || 60} Minuten</p></div></div>
        <div class="tbl" tabindex="0" role="region" aria-label="Tabelle, auf dem Handy seitlich scrollbar"><table><thead><tr><th>Quelle</th><th>Methode</th><th>Zuletzt abgerufen</th><th>Status</th></tr></thead><tbody>
        ${info.sources.map(x => `<tr><td>${x.site ? `<a href="${esc(x.site)}" target="_blank" rel="noopener">${esc(x.name)}</a>` : esc(x.name)}</td><td>${esc(x.method)}</td><td>${esc(dt(x.last_run))}</td><td>${x.ok ? '✅ ok' : '⚠️ Fehler'}</td></tr>`).join('')}</tbody></table></div></section>
      <section><div class="sec-head"><div><h2>Geprüfte Seiten für die KI-Websuche</h2><p class="sub">Findet der KI-Begleiter in unseren Inhalten nichts, sucht er nur auf diesen Seiten und nennt immer die Quelle.</p></div></div>
        <div class="two"><div class="box panel"><h3>Stufe 1 · Oberfranken</h3><div class="domains">${(T.stufe1_oberfranken || []).map(d => `<a href="https://${esc(d)}" target="_blank" rel="noopener">${esc(d)}</a>`).join('')}</div></div>
        <div class="box panel"><h3>Stufe 2 · Bayern, Bund, EU</h3><div class="domains">${(T.stufe2_bayern_bund_eu || []).map(d => `<a href="https://${esc(d)}" target="_blank" rel="noopener">${esc(d)}</a>`).join('')}</div></div></div></section>
    </main>`;
    bindGo(); reveal();
    const groups = {};
    (meta.places || []).forEach(p => { const k = p[1]; (groups[k] = groups[k] || []).push(p); });
    const drawPlaces = f => {
      const fl = (f || '').trim().toLowerCase();
      $('#pl-groups').innerHTML = meta.regions.map(r => {
        const list = (groups[r] || []).filter(p => !fl || p[0].toLowerCase().includes(fl));
        if (!list.length) return '';
        return `<div class="box plg"><h3>${esc(RLABEL(r))} <small>${list.length}</small></h3><div class="pls">${list.map(p => `<button type="button" class="plc${p[0] === town() ? ' on' : ''}" data-pl="${esc(p[0])}" title="${esc(p[4])}">${esc(p[0])}${p[4] !== 'Gemeinde' ? `<small>${esc(p[4])}</small>` : ''}</button>`).join('')}</div></div>`;
      }).join('') || '<p class="muted">Kein Ort gefunden.</p>';
      document.querySelectorAll('[data-pl]').forEach(b => b.onclick = () => { const p = placeBy(b.dataset.pl); if (p) { setRegion(p[1], 'manual', p[0]); toast(`Dein Ort: ${p[0]}`); drawPlaces($('#pl-q').value); } });
      applyLang($('#pl-groups'));
    };
    if ($('#pl-groups')) { drawPlaces(''); $('#pl-q').oninput = e => drawPlaces(e.target.value); }
  }

  function pageCredits() {
    $('#view').innerHTML = `<main class="wrap" style="padding-top:24px"><section class="box panel"><h1>Bildnachweis</h1>
      <p class="muted">Alle Fotos stammen von Wikimedia Commons und stehen unter freien Lizenzen. Auf Karten sind sie teils <b>Symbolbilder</b> zum Ort oder Thema. Für den Livebetrieb sollten eigene Fotos oder Fotos der Partner mit Freigabe dazukommen.</p>
      <div class="credits">${(IMGS || []).map(x => `<figure class="cr"><img src="${esc(x.src)}" alt="${esc(x.caption)}" loading="lazy"><figcaption><b>${esc(x.caption)}</b><span>Foto: ${esc(x.author)}</span><span><a href="${esc(x.license_url || '#')}" target="_blank" rel="noopener">${esc(x.license)}</a> · <a href="${esc(x.source)}" target="_blank" rel="noopener">Quelle</a> · verkleinert</span></figcaption></figure>`).join('')}</div>
      <h2 style="font-size:20px;margin-top:8px">Weitere Daten</h2>
      <ul class="muted" style="margin:0;padding-left:18px"><li>Karte: Grenzen der Landkreise © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap-Mitwirkende</a> (ODbL), vereinfacht</li><li>Wetterdaten: <a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo.com</a> (CC BY 4.0)</li><li>Inhalte in den Karten: echte Meldungen und Termine von Behörden, Städten, Landkreisen, Hochschulen und Tourismusverbänden (Liste unter „So funktioniert\'s“). Wir zeigen Titel und eine kurze Zusammenfassung und verlinken auf das Original.</li></ul></section></main>`;
  }

  const OFFICIAL = { Wunsiedel: 'https://www.fichtelgebirge.bayern', Kronach: 'https://www.frankenwald-tourismus.de', Lichtenfels: 'https://www.obermain-jura.de', Forchheim: 'https://www.fraenkische-schweiz.com', Bamberg: 'https://www.bamberg.info' };
  async function pageRegion(region) {
    const myRoute = routeSeq;
    const name = REGION_NAMES[region] || region;
    const [items, cur, w] = await Promise.all([api('/api/items?region=' + encodeURIComponent(region) + '&home=' + encodeURIComponent(homeKey())), api('/api/curated?slot=region&region=' + encodeURIComponent(region)), getWx(region), images()]);
    const c = cur[0] || { title: name, text: `Was in ${name} los ist: automatisch gesammelt aus den Seiten der Region und vom Team Oberfranken geprüft.` };
    const pic = (c.image && imgByFile(c.image.replace(/^lib\//, '').replace('-s.jpg', '.jpg'))) || (IMGS || []).find(x => x.region === region && x.mood === 'sun') || (IMGS || []).find(x => x.region === region);
    const off = OFFICIAL[region];
    const sugg = { Wunsiedel: 'Welcher Berg eignet sich für Mountainbike-Touren?', Kronach: 'Wo kann ich am Wochenende Rad fahren?', Lichtenfels: 'Was kann ich am Staffelberg machen?' }[region] || 'Was ist am Wochenende los?';
    if (myRoute !== routeSeq) return;
    $('#view').innerHTML = `<div class="wrap" style="padding-top:20px"><p class="crumb"><a href="#/">Start</a> › <a href="#/" data-go="regionen">Die Region</a> › <b>${esc(name)}</b>${name !== region ? ` <span class="muted">(Landkreis ${esc(region)})</span>` : ''}</p></div>
      <section class="wrap"><div class="rhero" data-src="blue">${pic ? `<img src="${esc(pic.big)}" alt="${esc(pic.caption)}">` : ''}
        <div class="rtext"><p class="eyebrow">Team Oberfranken · ${esc(name)}</p><h1>${esc(c.title)}</h1><p>${esc(c.text)}</p>
          <div class="rbtns">${w.temp != null ? `<span class="glass">${w.rain ? '🌧️' : /sonnig/.test(w.text || '') ? '☀️' : '⛅'} ${w.temp}° · ${esc(w.text)}</span>` : ''}${off ? `<a class="glass" href="${off}" target="_blank" rel="noopener">Zu ${esc(off.replace(/^https:\/\/(www\.)?/, ''))} ↗</a>` : ''}</div></div>
        ${pic ? `<a class="credit" href="#/bildnachweis">${esc(pic.caption)} · ${esc(pic.credit)}</a>` : ''}</div></section>
      <main class="wrap" style="padding-top:28px">
      <section class="box gmaps" id="gmaps"><div><h2 style="font-size:22px">${esc(name)} auf der Karte</h2><p class="small muted">Die Karte kommt von Google. Erst nach deinem Klick wird sie geladen; dabei überträgt dein Browser Daten (z. B. die IP-Adresse) an Google.</p></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" type="button" id="gmaps-load">Google Maps laden</button><span class="small muted" style="align-self:center">Erst nach Klick: dann sieht Google deine IP.</span><a class="btn ghost" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(name + ', Oberfranken')}" target="_blank" rel="noopener">In Google Maps öffnen ↗</a></div></section>
      <section class="smart" data-src="red"><h2>Was möchtest du über ${esc(({ Fichtelgebirge: 'das ', Frankenwald: 'den ', 'Obermain-Jura': 'den ', 'Fränkische Schweiz': 'die ' }[name] || '') + name)} wissen?</h2>${askForm(sugg, [['Am Wochenende', 'Was ist am Wochenende ' + whereTxt(name) + ' los?'], ['Rad fahren', 'Wo kann ich ' + whereTxt(name) + ' Rad fahren?'], ['Bei Regen', 'Was kann ich ' + whereTxt(name) + ' bei Regen drinnen machen?'], ['Mit Kindern', 'Was kann ich ' + whereTxt(name) + ' mit Kindern machen?']])}</section>
      <section class="box answer" id="answer" hidden style="margin:0"></section>
      <section data-src="red"><div class="sec-head"><div><h2>Ein paar Tipps für deinen nächsten Ausflug</h2><p class="sub">Mit Entfernung von ${esc(town() || REGION_NAMES[home()] || home())} und dem Wetter am Termin</p></div></div>${cards(items, 'Für diese Region gibt es gerade keine Inhalte.')}</section>
    </main>`;
    $('.smart .chips').querySelectorAll('.chip').forEach(ch => { ch.style.background = 'transparent'; ch.style.color = '#fff'; ch.style.borderColor = 'rgba(255,255,255,.6)'; });
    $('#gmaps-load').onclick = () => { $('#gmaps').innerHTML = `<iframe title="Google Maps: ${esc(name)}" src="https://www.google.com/maps?q=${encodeURIComponent(name + ', Oberfranken')}&output=embed" loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe>`; };
    bindAsk($('.smart'), $('#answer'), region); bindCards(); bindGo(); reveal();
  }

  async function pageMein() {
    const myRoute = routeSeq;
    if (!profile) { $('#view').innerHTML = `<main class="wrap" style="padding-top:24px"><section class="box panel"><h1>Mein Oberfranken</h1><p class="muted">Richte dein persönliches Oberfranken ein: ohne Konto, ohne E-Mail.</p><div><button class="btn primary" type="button" id="m-onb">Jetzt einrichten</button></div></section></main>`; $('#m-onb').onclick = () => openOnboarding(() => route()); return; }
    const items = saved().length ? await api('/api/items/by-ids?ids=' + saved().join(',') + '&home=' + encodeURIComponent(homeKey())) : [];
    if (myRoute !== routeSeq) return;
    $('#view').innerHTML = `<main class="wrap" style="padding-top:24px">
      <section><p class="eyebrow">Mein Oberfranken</p><h1 style="font-size:clamp(30px,4vw,44px);margin-top:8px">${greet()}${profile.nick ? ', ' + esc(profile.nick) : ''}.</h1><p class="sub" style="font-size:17px">${esc(profile.role)} · ${esc(REGION_NAMES[profile.region] || profile.region)} · ${esc(profile.topics.join(', '))}</p></section>
      <section><div class="sec-head"><h2>Meine Tagespläne</h2><span class="note">${(profile.plans || []).length} gespeichert</span></div>
        ${(profile.plans || []).length ? `<div class="plans">${profile.plans.map(pl => `<article class="box plancard"><div class="ph"><span class="eyebrow">${esc(pl.when || 'Ohne festen Tag')}${pl.weather ? ' · ' + esc(pl.weather) : ''}</span><button class="linkbtn" type="button" data-delplan="${esc(pl.id)}">Entfernen</button></div><h3>${esc(pl.title)}</h3>
          ${pl.steps.map((st, k) => `<div class="step2"><b>0${k + 1}</b><span>${esc(st.title)}<small>${esc(st.location || '')}${st.event_date ? ' · ' + fmt(st.event_date) : ''}${st.url ? ` · <a href="${esc(st.url)}" target="_blank" rel="noopener">Quelle</a>` : ''}</small></span></div>`).join('')}</article>`).join('')}</div>`
        : '<p class="empty">Noch kein Plan. Frag oben auf der Startseite z. B. „Ich möchte am Samstag Fahrrad fahren“ und tippe auf „Als Tagesplan speichern“.</p>'}</section>
      <section><div class="sec-head"><h2>Gemerkt</h2><span class="note">${items.length} Einträge</span></div>${cards(items, 'Noch nichts gemerkt. Tippe auf das Herz an einem Eintrag.')}</section>
      <section class="two">
        <div class="box panel"><h2 style="font-size:22px">Einstellungen</h2>
          <div><label class="lbl" for="p-nick">Wie dürfen wir dich nennen? (optional)</label><input class="field" id="p-nick" value="${esc(profile.nick || '')}" maxlength="30"></div>
          <div><label class="lbl" for="p-role">Ich bin</label><select class="field" id="p-role">${Object.keys(meta.roles).map(r => `<option${r === profile.role ? ' selected' : ''}>${r}</option>`).join('')}</select></div>
          <div><label class="lbl" for="p-region">Region</label><select class="field" id="p-region">${meta.regions.map(r => `<option value="${r}"${r === profile.region ? ' selected' : ''}>${esc(RLABEL(r))}</option>`).join('')}</select></div>
          <div><span class="lbl">Themen</span><div class="chips" id="p-topics" style="margin:0"></div></div>
          <div><button class="btn primary" type="button" id="p-save">Speichern</button></div></div>
        <div class="box panel"><h2 style="font-size:22px">Einfacher Login: Name + PIN</h2>
          <p class="small muted">Ohne E-Mail. Sichert Profil, Merkliste und Tagespläne, damit du dich auf jedem Gerät mit Name und 6-stelliger PIN anmelden kannst. Die PIN wird nur verschlüsselt (gehasht) gespeichert.</p>
          ${profile.account ? `<p>Angemeldet als <b>${esc(profile.account)}</b> · <button class="linkbtn" type="button" id="acc-logout">Abmelden</button></p>` : ''}
          <div class="pinrow"><input class="field" id="acc-name" placeholder="Name, z. B. max.coburg" maxlength="30" autocomplete="username" value="${esc(profile.account || '')}"><input class="field" id="acc-pin" placeholder="PIN (6 Ziffern)" inputmode="numeric" maxlength="6" type="password" autocomplete="current-password"></div>
          <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" type="button" id="acc-save">${profile.account ? 'Änderungen sichern' : 'Konto anlegen / sichern'}</button><button class="btn" type="button" id="acc-login">Anmelden</button></div>
          <p class="small muted" id="acc-msg"></p>
        </div>
        <div class="box panel"><h2 style="font-size:22px">Auf anderem Gerät nutzen</h2>
          <p class="small muted">Ein Sync-Code überträgt nur Themen, Region und Merkliste. Kein Name, keine E-Mail.</p>
          <div>${profile.sync ? `<span class="codebig">${esc(profile.sync)}</span>` : '<button class="btn" type="button" id="sync-make">Sync-Code erzeugen</button>'}</div>
          <div><label class="lbl" for="sync-in">Code von einem anderen Gerät</label><div style="display:flex;gap:8px"><input class="field" id="sync-in" placeholder="XXXX-XXXX" maxlength="9"><button class="btn" type="button" id="sync-load">Laden</button></div></div>
          <h2 style="font-size:19px;margin-top:8px">Was gespeichert ist</h2><pre class="stored">${esc(JSON.stringify({ profil: profile, einwilligung: consent() || 'noch nicht gewählt' }, null, 2))}</pre>
          <p class="small">Anonyme Statistik: <b>${consent() && consent().stats ? 'an' : 'aus'}</b> · <button class="linkbtn" type="button" id="ck-change">ändern</button></p><p class="small muted">Diese Daten liegen nur in diesem Browser.</p>
          <div id="del-area"><button class="btn danger" type="button" id="del">Alles löschen</button></div></div>
      </section></main>`;
    const tp = profile.topics.slice();
    const drawT = () => { $('#p-topics').innerHTML = meta.topics.map(t => `<button type="button" class="chip" aria-pressed="${tp.includes(t)}" data-t="${t}">${t}</button>`).join(''); $('#p-topics').querySelectorAll('[data-t]').forEach(b => b.onclick = () => { const k = tp.indexOf(b.dataset.t); if (k >= 0) { if (tp.length > 1) tp.splice(k, 1); } else tp.push(b.dataset.t); drawT(); }); };
    drawT();
    $('#p-save').onclick = () => { Object.assign(profile, { nick: $('#p-nick').value.trim(), role: $('#p-role').value, region: $('#p-region').value, topics: tp }); store(KEY, profile); toast('Gespeichert, nur in diesem Browser.'); route(); };
    const accBody = () => ({ name: $('#acc-name').value.trim(), pin: $('#acc-pin').value.trim() });
    const accMsg = (t, ok) => { const m = $('#acc-msg'); m.textContent = t; m.style.color = ok ? 'var(--blue-2)' : 'var(--brand-2)'; };
    $('#acc-save').onclick = async () => { try { const r = await api('/api/account/save', { body: Object.assign(accBody(), { profile }) }); profile.account = r.name; store(KEY, profile); toast('Konto gesichert. Anmelden geht jetzt mit Name und PIN.'); route(); } catch (e) { accMsg(e.message); } };
    $('#acc-login').onclick = async () => { try { const r = await api('/api/account/login', { body: accBody() }); profile = Object.assign({ id: profile.id }, r.profile, { account: r.name }); store(KEY, profile); toast('Angemeldet. Profil geladen.'); route(); } catch (e) { accMsg(e.message); } };
    if ($('#acc-logout')) $('#acc-logout').onclick = () => { delete profile.account; store(KEY, profile); toast('Abgemeldet. Dein Profil bleibt in diesem Browser.'); route(); };
    if ($('#sync-make')) $('#sync-make').onclick = async () => { const r = await api('/api/sync', { body: profile }); profile.sync = r.code; store(KEY, profile); route(); };
    $('#sync-load').onclick = async () => { try { const code = $('#sync-in').value.trim().toUpperCase(); const p = await api('/api/sync/' + encodeURIComponent(code)); profile = Object.assign({ nick: '' }, p, { sync: code }); store(KEY, profile); toast('Profil übernommen.'); route(); } catch (e) { toast(e.message); } };
    $('#del').onclick = () => { $('#del-area').innerHTML = '<p><b>Wirklich alles löschen?</b></p><div style="display:flex;gap:8px;margin-top:8px"><button class="btn danger" type="button" id="del-yes">Ja, löschen</button><button class="btn" type="button" id="del-no">Abbrechen</button></div>'; $('#del-yes').onclick = () => { try { localStorage.removeItem(KEY); localStorage.removeItem(RK); } catch (e) {} profile = null; toast('Gelöscht.'); location.hash = '#/'; }; $('#del-no').onclick = () => route(); };
    $('#ck-change').onclick = () => { cookieCard(true); window.scrollTo(0, 0); };
    document.querySelectorAll('[data-delplan]').forEach(b => b.onclick = () => { profile.plans = profile.plans.filter(p => p.id !== b.dataset.delplan); store(KEY, profile); route(); });
    bindCards();
  }

  function pagePrivacy() {
    const c = consent();
    $('#view').innerHTML = `<main class="wrap" style="padding-top:24px"><section class="box panel privacy"><h1>So schützen wir deine Daten</h1>
      <p class="muted">Kurz gesagt: anonym personalisieren statt tracken. Prototyp, ersetzt keine Datenschutzerklärung.</p>
      <div class="ptab">
        <div><b>IP-Adresse</b><span>Wird <u>nicht</u> gespeichert, nicht protokolliert und nicht für Tracking genutzt. Nur kurz im Arbeitsspeicher: als täglich wechselnder Hash gegen Missbrauch (max. 10 Minuten) und, falls eingerichtet, einmal für einen Regionsvorschlag. Dann wird sie verworfen.</span></div>
        <div><b>Cookies</b><span>Keine Werbe- oder Tracking-Cookies. Im Browser liegen nur notwendige Einträge: deine Auswahl, deine Region und „Mein Oberfranken“, wenn du es einrichtest.</span></div>
        <div><b>Statistik</b><span>Nur mit Einwilligung. Gezählt wird „Tag + Ereignis“ (z. B. „Seite Fichtelgebirge aufgerufen“) als Summe. Keine IP, keine ID, kein Profil. Aktuell: <b>${c && c.stats ? 'an' : 'aus'}</b>. <button class="linkbtn" type="button" id="pv-ck">ändern</button></span></div>
        <div><b>Standort</b><span>Nur wenn du „Meinen Standort verwenden“ tippst. Die nächste Region wird auf deinem Gerät berechnet, die Koordinaten werden nicht gesendet.</span></div>
        <div><b>Mein Oberfranken</b><span>Kein Konto, keine E-Mail, kein Passwort. Profil, Merkliste und Tagespläne bleiben in deinem Browser. Der Sync-Code ist freiwillig, überträgt nur Themen, Region und Merkliste und gilt 30 Tage. Ein Konto mit Name + PIN ist ebenfalls freiwillig und wird 12 Monate nach der letzten Nutzung gelöscht.</span></div>
        <div><b>KI-Begleiter</b><span>Deine Fragen speichern wir nicht. Ist eine KI angebunden (z. B. Google Gemini), geht die Frage ohne IP nur zur Beantwortung an den Anbieter; findet sich in unseren Inhalten nichts, wird nur auf geprüften Seiten gesucht (Behörden, Landkreise, Hochschulen, Tourismus): per Google-Suche über Gemini oder mit unserer eigenen Suche, bei der unser Server die Seiten abruft. Die Quellen werden immer genannt. Erst bei 👎 landet sie anonym bei der Redaktion. KI-Texte sind gekennzeichnet und verlinken auf die Quelle (EU AI Act, Art. 50).</span></div>
        <div><b>Spracheingabe &amp; Vorlesen</b><span>Nur wenn du auf das Mikrofon tippst: Dein Browser wandelt die Sprache in Text um (Chrome/Edge über Google bzw. Microsoft, Safari über Apple). Wir erhalten nur den Text und speichern ihn nicht. Vorlesen läuft in deinem Browser.</span></div>
        <div><b>Schriften</b><span>Liegen auf unserem eigenen Server. Beim Laden der Seite wird keine Verbindung zu Google Fonts oder anderen Schrift-Diensten aufgebaut.</span></div>
        <div><b>Externe Dienste</b><span>Beim normalen Aufruf: <u>keine</u>. Erst wenn du etwas anklickst: Google Maps (Karte laden oder „In Google Maps öffnen“), die Spracherkennung deines Browsers (Mikrofon) und, falls angebunden, Google Gemini für KI-Antworten (nur der Fragetext, ohne IP). Das Wetter holt unser Server bei Open-Meteo, dein Browser hat damit keinen Kontakt.</span></div>
        <div><b>Speicherdauer</b><span>Im Browser: bis du es löschst (unten im Live-Check). Auf dem Server: Sync-Codes 30 Tage, Konten 12 Monate nach letzter Nutzung, Hinweise 12 Monate, Statistik-Summen 13 Monate, Abruf-Protokoll 90 Tage. Das Löschen läuft automatisch.</span></div>
        <div><b>Rechtsgrundlage</b><span>Unsere Einschätzung, vor dem Livegang von Fachleuten zu prüfen: Einträge im Browser, die für eine gewünschte Funktion nötig sind, § 25 Abs. 2 TDDDG. Statistik nur mit Einwilligung, Art. 6 Abs. 1 lit. a DSGVO, jederzeit widerrufbar. Schutz vor Missbrauch (kurzer IP-Hash im Arbeitsspeicher), Art. 6 Abs. 1 lit. f DSGVO.</span></div>
        <div><b>Hosting</b><span>Im Prototyp läuft die Seite auf einem Laptop, beim Teilen über einen Cloudflare-Tunnel. Cloudflare verarbeitet dabei technisch bedingt IP-Adressen. Für den Livebetrieb: Hosting in der EU mit Auftragsverarbeitungsvertrag.</span></div>
      </div>
      <p class="note">Vor dem Livegang: Datenschutzerklärung und Impressum, Prüfung nach DSGVO und § 25 TDDDG durch Fachleute.</p></section>
      <section class="box panel privacy" id="pv-live" aria-labelledby="pv-live-h"><p class="eyebrow">Live-Check</p><h2 id="pv-live-h">Was ist gerade gespeichert?</h2>
        <p class="muted">Nicht nur behaupten, sondern zeigen: links steht, was in <b>diesem Browser</b> liegt, rechts, was <b>unser Server</b> sieht und überhaupt speichern kann.</p>
        <div class="pv-grid"><div><h3>In deinem Browser</h3><div id="pv-browser"></div></div><div><h3>Auf unserem Server</h3><div id="pv-server"><p class="small muted">Wird geladen …</p></div></div></div>
      </section></main>`;
    $('#pv-ck').onclick = () => { cookieCard(true); window.scrollTo(0, 0); };
    privacyLive();
  }

  function pageImprint() {
    $('#view').innerHTML = `<main class="wrap" style="padding-top:24px"><section class="box panel privacy"><h1>Impressum &amp; Kontakt</h1>
      <p class="muted">Dies ist ein nicht-kommerzieller Prototyp aus einem Studienprojekt der Hochschule Coburg in Zusammenarbeit mit BERGWERK. Er ist kein offizielles Angebot von Oberfranken Offensiv e.V. oder einer Behörde.</p>
      <div class="ptab">
        <div><b>Projekt</b><span>Studienprojekt „Plattform Oberfranken“, Hochschule Coburg, Wintersemester 2026/27.</span></div>
        <div><b>Hochschule</b><span>Hochschule für angewandte Wissenschaften Coburg, Friedrich-Streib-Straße 2, 96450 Coburg · <a href="https://www.hs-coburg.de" target="_blank" rel="noopener">www.hs-coburg.de ↗</a></span></div>
        <div><b>Kontakt zum Projekt</b><span>Über die Projektbetreuung an der Hochschule Coburg. Fehler in einem Eintrag? Direkt am Eintrag „Fehler melden“ oder 👎 nutzen.</span></div>
        <div><b>Inhalte</b><span>Termine und Meldungen stammen von den genannten Quellen, jeder Eintrag verlinkt auf das Original. Für deren Inhalt sind die jeweiligen Anbieter verantwortlich.</span></div>
        <div><b>Fotos</b><span>Freie Lizenzen, siehe <a href="#/bildnachweis">Bildnachweis</a>.</span></div>
      </div>
      <p class="note">Vor einem Livebetrieb: vollständiges Impressum nach § 5 DDG mit verantwortlicher Stelle, Anschrift und E-Mail des Betreibers.</p></section></main>`;
  }
  function pageA11y() {
    $('#view').innerHTML = `<main class="wrap" style="padding-top:24px"><section class="box panel privacy"><h1>Barrierefreiheit</h1>
      <p class="muted">Ziel: WCAG 2.2, Stufe AA. Stand: automatisch mit axe geprüft, dazu Tests per Tastatur, auf dem Handy und im Dunkelmodus. Ein Test mit echten Screenreader-Nutzern steht noch aus.</p>
      <div class="ptab">
        <div><b>Tastatur</b><span>Alles ist ohne Maus bedienbar. Tab springt weiter, der Fokus ist gelb umrandet, Esc schließt Dialog, „Frag mich“ und Live-Gespräch. Ganz oben: „Zum Inhalt springen“.</span></div>
        <div><b>Kontraste</b><span>Texte erfüllen mindestens 4,5 : 1, in Hell und Dunkel. Texte auf Fotos liegen auf einem dunklen Verlauf.</span></div>
        <div><b>Bilder</b><span>Fotos mit Inhalt haben einen Alternativtext, reine Schmuckbilder werden von Screenreadern übersprungen.</span></div>
        <div><b>Ohne Karte</b><span>Alles auf der Karte gibt es auch als Liste: Regionen, Termine und alle 214 Orte auf „Über Oberfranken“.</span></div>
        <div><b>Termine</b><span>Termine stehen als Liste mit Datum im Klartext, nicht nur in einem Kalender-Raster.</span></div>
        <div><b>Frag mich</b><span>Antworten werden Screenreadern angesagt (Live-Region), Status wie „Ich höre zu“ steht als Text da. Tippen statt sprechen geht immer.</span></div>
        <div><b>Bewegung</b><span>Folgt der Einstellung „Bewegung reduzieren“ des Geräts. Zusätzlich im Footer abschaltbar.</span></div>
        <div><b>Sprache &amp; Größe</b><span>Deutsch und Englisch, Text lässt sich auf 200 % vergrößern, ohne dass etwas abgeschnitten wird.</span></div>
      </div>
      <p class="note">Barriere gefunden? Bitte über „Fehler melden“ an einem Eintrag oder über die Projektbetreuung melden.</p></section></main>`;
  }

  /* Live-Check: echte Einträge im Browser (localStorage, sessionStorage, Cookies) mit Klartext-Erklärung und Löschen */
  const STORE_INFO = {
    'oberfranken-cookie': ['Deine Datenschutz-Auswahl', 'Damit das Banner nicht jedes Mal kommt.', 'notwendig'],
    'oberfranken-profil': ['Mein Oberfranken', 'Rolle, Themen, Ort, Merkliste, Tagespläne. Nur wenn du es einrichtest.', 'notwendig'],
    'oberfranken-region': ['Deine Region / dein Ort', 'Für Wetter, Entfernungen und passende Tipps.', 'notwendig'],
    'oberfranken-theme': ['Hell / Dunkel', 'Deine Ansicht.', 'notwendig'],
    'oberfranken-lang': ['Sprache', 'Deutsch oder Englisch.', 'notwendig'],
    'oberfranken-voice-ok': ['Hinweis Spracheingabe gelesen', 'Damit der Mikrofon-Hinweis nur einmal kommt.', 'notwendig'],
    'oberfranken-motion': ['Bewegung reduzieren', 'Animationen aus, weil du es eingestellt hast.', 'notwendig'],
    'ww-hint': ['Hinweis zu „Frag mich“ gesehen', 'Nur für diesen Tab, verschwindet beim Schließen.', 'notwendig']
  };
  function privacyLive() {
    const rows = [];
    const scan = (st, where) => { try { for (let i = 0; i < st.length; i++) { const k = st.key(i); if (k && (k.startsWith('oberfranken-') || k.startsWith('ww-'))) rows.push({ k, v: st.getItem(k) || '', where, st }); } } catch (e) {} };
    scan(localStorage, 'Browser-Speicher'); scan(sessionStorage, 'Nur dieser Tab');
    const pretty = v => { try { return JSON.stringify(JSON.parse(v), null, 2); } catch (e) { return v; } };
    const cookies = (document.cookie || '').split(';').filter(c => c.trim()).length;
    const T = (de, en) => LANG === 'en' ? en : de;
    const pill = (n, de, en) => `<span><b>${n}</b> ${T(de, en)}</span>`;
    const el = $('#pv-browser'); if (!el) return;
    el.innerHTML = `<div class="pv-facts">${pill(cookies, 'Cookies', 'cookies')}${pill(rows.length, rows.length === 1 ? 'Eintrag' : 'Einträge', rows.length === 1 ? 'entry' : 'entries')}${pill(0, 'Werbe- / Tracking-Dienste', 'ad / tracking services')}</div>
      ${rows.length ? `<ul class="pv-list">${rows.map((r, i) => { const inf = STORE_INFO[r.k] || [r.k, '', 'notwendig']; return `<li><div class="pv-h"><b>${esc(inf[0])}</b><span class="pv-tag">${T('notwendig', 'necessary')} · ${r.st === localStorage ? T('Browser-Speicher', 'browser storage') : T('nur dieser Tab', 'this tab only')} · ${r.v.length} ${T('Zeichen', 'characters')}</span></div>
        <p class="small muted">${esc(inf[1])}</p><details><summary>${T('Inhalt ansehen', 'View content')} <code>${esc(r.k)}</code></summary><pre>${esc(pretty(r.v))}</pre></details>
        <button class="btn sm ghost" type="button" data-pvdel="${i}">${T('Löschen', 'Delete')}</button></li>`; }).join('')}</ul>
        <button class="btn danger" type="button" id="pv-all">${T('Alles in diesem Browser löschen', 'Delete everything in this browser')}</button>` : `<p class="small">${T('In diesem Browser ist nichts von uns gespeichert.', 'Nothing from us is stored in this browser.')}</p>`}
      <p class="small muted">${T('Selbst nachprüfen: im Browser F12 › „Anwendung“ (Chrome/Edge) bzw. „Web-Speicher“ (Firefox).', 'Check it yourself: press F12 › "Application" (Chrome/Edge) or "Storage" (Firefox).')}</p>`;
    el.querySelectorAll('[data-pvdel]').forEach(b => b.onclick = () => { const r = rows[+b.dataset.pvdel]; try { r.st.removeItem(r.k); } catch (e) {} if (r.k === KEY) profile = null; toast(T('Gelöscht.', 'Deleted.')); privacyLive(); });
    if ($('#pv-all')) $('#pv-all').onclick = () => { rows.forEach(r => { try { r.st.removeItem(r.k); } catch (e) {} }); profile = null; toast(T('Alles gelöscht. Beim nächsten Laden fragt die Seite neu.', 'All deleted. The page will ask again on next load.')); privacyLive(); };
    const SK = k => k === 'ask' ? T('Fragen an „Frag mich“', 'questions to the Wayfinder') : k === 'plan' ? T('Tagespläne', 'day plans') : k === 'save' ? T('gemerkt', 'saved') : k === 'feedback' ? 'Feedback' : k === 'followup' ? T('Folgefragen', 'follow-ups') : k.startsWith('view:region:') ? T('Seite ', 'page ') + k.slice(12) : k === 'view:datenschutz' ? T('Datenschutz-Seite', 'privacy page') : k === 'view:mein' ? T('Mein Oberfranken', 'My page') : k === 'view:start' ? T('Startseite', 'home page') : k;
    api('/api/privacy/check').then(d => {
      const s = $('#pv-server'); if (!s) return;
      s.innerHTML = `<div class="pv-facts"><span>${T('IP gesehen', 'IP seen')}: <b>${esc(d.ip_seen)}</b></span><span>${T('gespeichert', 'stored')}: <b>${d.ip_stored ? T('ja', 'yes') : T('nein', 'no')}</b></span><span>${T('Zugriffsprotokoll', 'access log')}: <b>${d.access_log ? T('an', 'on') : T('aus', 'off')}</b></span></div>
        <p class="small muted">${T('Jeder Server sieht beim Aufruf die IP, sonst käme die Antwort nicht an. Wir zeigen sie hier gekürzt und legen sie nirgends ab. Das sind <b>alle</b> Tabellen unserer Datenbank mit ihren Spalten', 'Every server sees the IP of a request, otherwise the answer could not be sent back. We show it shortened here and store it nowhere. These are <b>all</b> tables in our database with their columns')}${d.any_ip_column ? '.' : T(': eine Spalte für IP, Gerät oder Cookie gibt es <b>nicht</b>.', ': there is <b>no</b> column for IP, device or cookie.')}</p>
        <ul class="pv-list">${d.tables.map(t => `<li><div class="pv-h"><b>${esc(t.label)}</b><span class="pv-tag">${t.rows} ${t.rows === 1 ? T('Zeile', 'row') : T('Zeilen', 'rows')}</span></div><p class="small pv-cols">${t.columns.map(c => `<code>${esc(c)}</code>`).join(' ')}</p></li>`).join('')}</ul>
        ${(d.retention || []).length ? `<p class="small"><b>${T('Automatisch gelöscht', 'Deleted automatically')}</b></p><ul class="retention">${d.retention.map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
        ${d.stats_today.length ? `<p class="small muted">${T('Statistik heute, nur Summen', 'Statistics today, totals only')}: ${d.stats_today.map(x => `${esc(SK(x.key))} ${x.n}×`).join(' · ')}</p>` : `<p class="small muted">${T('Statistik heute: noch nichts gezählt.', 'Statistics today: nothing counted yet.')}</p>`}`;
    }).catch(() => { const s = $('#pv-server'); if (s) s.innerHTML = `<p class="small">${T('Server gerade nicht erreichbar.', 'Server not reachable right now.')}</p>`; });
  }


  /* ---------- Vergleich: warum diese Plattform statt einer allgemeinen KI ---------- */
  const VS_ROWS = [
    ['Aktualität', 'Termine und Meldungen jede Stunde neu von den offiziellen Seiten der Region, Wetter alle 30 Minuten.', 'Wissen aus Trainingsdaten oder einer allgemeinen Websuche. Termine können veraltet sein.'],
    ['Quellen', 'Jede Antwort nur aus geprüften Quellen, jede Karte mit Link zum Original und Ranking von amtlich bis Partner.', 'Quellen oft unklar oder beliebige Websites, schwer nachzuprüfen.'],
    ['Ehrlichkeit', 'Steht nichts in den Quellen, sagen wir das: „nichts gefunden“, nichts wird erfunden.', 'Kann plausibel klingende, aber falsche Angaben machen.'],
    ['Region', 'Alle 214 Orte Oberfrankens, Wetter pro Ort, Entfernung von deinem Wohnort, Wetter am Tag des Termins.', 'Allgemein, ohne genaue Ortskenntnis.'],
    ['Datenschutz', 'Kein Konto, keine E-Mail, Fragen werden nicht gespeichert, keine IP-Speicherung. Live-Check zeigt alles.', 'Meist Konto nötig, Gespräche werden je nach Anbieter gespeichert und teils zum Training genutzt.'],
    ['Transparenz', '„Was passiert im Hintergrund?“ zeigt bei jeder Antwort jeden Schritt.', 'Wie die Antwort entsteht, bleibt meist verborgen.'],
  ];
  const vsSection = (id = 'vergleich') => `<section class="vs" id="${id}"><div class="sec-head"><div><h2>Warum nicht einfach ChatGPT & Co. fragen?</h2>
      <p class="sub">Allgemeine KI-Chatbots wissen viel über die Welt. „Frag mich“ weiß genau, was in Oberfranken los ist, und zeigt, woher.</p></div></div>
      <div class="tbl vs-tbl" tabindex="0" role="region" aria-label="Vergleich mit allgemeinen KI-Chatbots"><table><thead><tr><th scope="col"></th><th scope="col">Plattform Oberfranken mit „Frag mich“</th><th scope="col">Allgemeine KI-Chatbots</th></tr></thead><tbody>
      ${VS_ROWS.map(r => `<tr><th scope="row">${r[0]}</th><td class="vs-us"><small class="vs-lab">Plattform Oberfranken mit „Frag mich“</small><span aria-hidden="true">✓ </span>${r[1]}</td><td class="vs-them"><small class="vs-lab">Allgemeine KI-Chatbots</small>${r[2]}</td></tr>`).join('')}</tbody></table></div>
      <p class="note">Fair gesagt: Für allgemeine Aufgaben wie Texte schreiben oder Programmieren sind allgemeine KI-Chatbots stärker. Wir sind bewusst nur auf Oberfranken spezialisiert, mit echten Daten und Quelle.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" type="button" data-vs-try>„Frag mich“ ausprobieren</button><a class="btn" href="#/so-funktionierts">So funktioniert's</a></div></section>`;
  document.addEventListener('click', e => { if (e.target.closest && e.target.closest('[data-vs-try]')) liveOpen(true); });

  /* ---------- Onboarding „Mein Oberfranken“ (anonym) ---------- */
  function openOnboarding(done, presetRole) {
    const d = { nick: '', role: presetRole || null, topics: [], region: home(), town: town() }; let step = 1;
    const m = $('#modal'); m.hidden = false;
    const draw = () => {
      m.innerHTML = `<div class="dlg" role="dialog" aria-modal="true" aria-label="Mein Oberfranken einrichten">
        <div class="steps"><i class="on"></i><i class="${step > 1 ? 'on' : ''}"></i><i class="${step > 2 ? 'on' : ''}"></i></div>
        ${step === 1 ? `<h2>Wer bist du?</h2><div class="roles">${Object.keys(meta.roles).map(r => `<button type="button" class="role" aria-pressed="${d.role === r}" data-r="${r}"><span><b style="color:var(--ink)">${r}</b><br><span>${{ Bewohner: 'Ich lebe in Oberfranken', Gast: 'Ich besuche die Region', Fachkraft: 'Ich suche Arbeit oder Kontakte', 'Neu hier': 'Ich ziehe her oder überlege es', 'Lernen & Karriere': 'Ich will mich weiterentwickeln' }[r] || ''}</span></span></button>`).join('')}</div>
          <div><label class="lbl" for="o-nick">Wie dürfen wir dich nennen? (optional)</label><input class="field" id="o-nick" maxlength="30" value="${esc(d.nick)}" placeholder="z. B. Max"></div>` : ''}
        ${step === 2 ? `<h2>Was interessiert dich?</h2><div class="chips">${meta.topics.map(t => `<button type="button" class="chip" aria-pressed="${d.topics.includes(t)}" data-t="${t}">${t}</button>`).join('')}</div>` : ''}
        ${step === 3 ? `<h2>Wo wohnst du oder bist du unterwegs?</h2><label class="lbl" for="o-town">Dein Ort (optional)</label><input class="field" id="o-town" list="place-list" autocomplete="off" placeholder="z. B. Steinbach am Wald" value="${esc(d.town || '')}">${placeOptions()}<label class="lbl" for="o-region">Region</label><select class="field" id="o-region">${meta.regions.map(r => `<option value="${r}"${r === d.region ? ' selected' : ''}>${esc(RLABEL(r))}</option>`).join('')}</select>` : ''}
        <p class="trustnote">Keine E-Mail, kein Passwort, keine gespeicherte IP. Dein Profil bleibt in diesem Browser.</p>
        ${step === 1 ? `<details class="quicklogin"><summary>Schon ein Konto? Mit Name + PIN anmelden</summary><div class="pinrow"><input class="field" id="q-name" placeholder="Name" maxlength="30" autocomplete="username"><input class="field" id="q-pin" placeholder="PIN" inputmode="numeric" maxlength="6" type="password" autocomplete="current-password"><button class="btn" type="button" id="q-login">Anmelden</button></div><p class="small" id="q-msg"></p></details>` : ''}
        <div style="display:flex;justify-content:space-between;gap:8px"><button class="btn ghost" type="button" id="o-back">${step === 1 ? 'Abbrechen' : 'Zurück'}</button><button class="btn primary" type="button" id="o-next">${step === 3 ? 'Fertig' : 'Weiter'}</button></div></div>`;
      m.querySelectorAll('[data-r]').forEach(b => b.onclick = () => { d.nick = $('#o-nick').value.trim(); d.role = b.dataset.r; d.topics = meta.roles[d.role].slice(); draw(); });
      m.querySelectorAll('[data-t]').forEach(b => b.onclick = () => { const k = d.topics.indexOf(b.dataset.t); if (k >= 0) d.topics.splice(k, 1); else d.topics.push(b.dataset.t); draw(); });
      if ($('#o-region')) $('#o-region').onchange = e => d.region = e.target.value;
      if ($('#o-town')) $('#o-town').oninput = e => { const p = placeBy(e.target.value); d.town = p ? p[0] : ''; if (p) { d.region = p[1]; $('#o-region').value = p[1]; } };
      if ($('#q-login')) $('#q-login').onclick = async () => {
        try { const r = await api('/api/account/login', { body: { name: $('#q-name').value.trim(), pin: $('#q-pin').value.trim() } });
          profile = Object.assign({ id: 'anon-' + Array.from(crypto.getRandomValues(new Uint8Array(4)), b => b.toString(16).padStart(2, '0')).join('') }, r.profile, { account: r.name });
          store(KEY, profile); m.hidden = true; toast('Angemeldet. Willkommen zurück!'); done && done();
        } catch (e) { $('#q-msg').textContent = e.message; }
      };
      $('#o-back').onclick = () => { if (step === 1) m.hidden = true; else { step--; draw(); } };
      $('#o-next').onclick = () => {
        if (step === 1) { d.nick = $('#o-nick').value.trim(); if (!d.role) { toast('Bitte wähle, wer du bist.'); return; } }
        if (step === 2 && !d.topics.length) { toast('Bitte wähle mindestens ein Thema.'); return; }
        if (step < 3) { step++; draw(); return; }
        const id = 'anon-' + Array.from(crypto.getRandomValues(new Uint8Array(4)), b => b.toString(16).padStart(2, '0')).join('');
        profile = { id, nick: d.nick, role: d.role, topics: d.topics, region: d.region, town: d.town || '', saved: [] };
        store(KEY, profile); m.hidden = true; toast('Mein Oberfranken ist eingerichtet.'); done && done();
      };
    };
    draw();
  }
  function openReport(id) {
    const m = $('#modal'); m.hidden = false;
    m.innerHTML = `<form class="dlg" id="rep"><h2>Fehler melden</h2><label class="lbl" for="rep-in">Was stimmt nicht?</label><input class="field" id="rep-in" required maxlength="300" placeholder="z. B. Das Datum ist falsch"><div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn ghost" type="button" id="rep-x">Abbrechen</button><button class="btn primary" type="submit">Senden</button></div></form>`;
    $('#rep-x').onclick = () => m.hidden = true;
    $('#rep').addEventListener('submit', async e => { e.preventDefault(); try { await api('/api/report', { body: { item_id: id, reason: $('#rep-in').value } }); m.hidden = true; toast('Danke! Die Redaktion schaut sich das an.'); } catch (err) { toast(err.message); } });
  }

  /* ---------- Navigation ---------- */
  function bindGo() {
    document.querySelectorAll('[data-go]').forEach(a => a.onclick = async e => {
      e.preventDefault();
      const id = a.dataset.go;
      if (!$('#' + id)) { location.hash = '#/'; await route(); }
      const el = $('#' + id); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }
  let routeSeq = 0;
  async function route() {
    routeSeq++;
    const h = location.hash.replace(/^#/, '') || '/';
    const mySeq = routeSeq;
    const skT = setTimeout(() => { if (mySeq === routeSeq) skeleton(); }, 120); // nur zeigen, wenn das Laden spürbar dauert
    document.querySelectorAll('.tabbar [data-tab]').forEach(t => t.classList.toggle('on', (t.dataset.tab === 'mein' && h === '/mein') || (t.dataset.tab === 'start' && (h === '/' || h === ''))));
    try {
      if (h.startsWith('/region/')) { const r = decodeURIComponent(h.split('/')[2]); await pageRegion(r); track('view:region:' + r); }
      else if (h === '/mein') { await pageMein(); track('view:mein'); }
      else if (h === '/datenschutz') { pagePrivacy(); track('view:datenschutz'); if (sessionStorage && window.__pvjump) { window.__pvjump = false; setTimeout(() => { const x = $('#pv-live'); if (x) x.scrollIntoView({ behavior: 'smooth' }); }, 50); } }
      else if (h === '/bildnachweis') { await images(); pageCredits(); }
      else if (h === '/impressum') { pageImprint(); }
      else if (h === '/barrierefreiheit') { pageA11y(); }
      else if (h === '/oberfranken') { await pageAbout(); track('view:start'); }
      else if (h === '/so-funktionierts') { await pageHow(); track('view:how'); }
      else if (h === '/leben') { await pageLive(); track('view:leben'); }
      else if (h === '/partner') { await pagePartner(); track('view:partner'); }
      else { await pageStart(); track('view:start'); }
    } catch (e) { $('#view').innerHTML = `<main class="wrap"><p class="box panel">Die Inhalte konnten nicht geladen werden: ${esc(e.message)}</p></main>`; }
    clearTimeout(skT);
    if (!h.startsWith('/') || h === '/') {} else window.scrollTo(0, 0);
  }
  document.querySelectorAll('.tabbar [data-tab]').forEach(t => t.addEventListener('click', async e => {
    const k = t.dataset.tab;
    if (k === 'fragen' || k === 'karte') {
      e.preventDefault();
      if (k === 'fragen') { liveOpen(true); return; }
      if (location.hash && location.hash !== '#/') { location.hash = '#/'; await new Promise(r => setTimeout(r, 400)); }
      else { const el = $('#regionen'); if (el) el.scrollIntoView({ behavior: 'smooth' }); }
    }
  }));
  const langBtn = $('#lang-btn');
  const setLangUi = () => { document.documentElement.lang = LANG; if (langBtn) langBtn.textContent = LANG === 'en' ? 'DE' : 'EN'; };
  if (langBtn) langBtn.onclick = () => { LANG = LANG === 'en' ? 'de' : 'en'; store('oberfranken-lang', LANG); setLangUi(); if (LANG === 'de') location.reload(); else { applyLang(document.body); route(); } };
  setLangUi();
  // Farbmodus: Gerät (folgt der Systemeinstellung) → Hell → Dunkel
  const themeBtn = $('#theme-btn'), THEMES = ['auto', 'light', 'dark'];
  const THEME_UI = { auto: ["<svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' aria-hidden='true'><circle cx='12' cy='12' r='9'/><path d='M12 3a9 9 0 0 1 0 18z' fill='currentColor'/></svg>", 'Farbmodus: Gerät'], light: ["<svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' aria-hidden='true'><circle cx='12' cy='12' r='4'/><path d='M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4'/></svg>", 'Farbmodus: Hell'], dark: ["<svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'><path d='M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z'/></svg>", 'Farbmodus: Dunkel'] };
  let THEME = (() => { try { return localStorage.getItem('oberfranken-theme'); } catch (e) { return null; } })() || 'auto';
  const setTheme = t => {
    THEME = t; if (t === 'auto') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
    try { if (t === 'auto') localStorage.removeItem('oberfranken-theme'); else localStorage.setItem('oberfranken-theme', t); } catch (e) {}
    if (themeBtn) { const [ic, lbl] = THEME_UI[t]; themeBtn.innerHTML = ic; themeBtn.title = lbl; themeBtn.setAttribute('aria-label', lbl + ' (klicken zum Wechseln)'); }
  };
  if (themeBtn) themeBtn.onclick = () => { setTheme(THEMES[(THEMES.indexOf(THEME) + 1) % 3]); toast(THEME_UI[THEME][1]); };
  setTheme(THEMES.includes(THEME) ? THEME : 'auto');
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('#modal').hidden) $('#modal').hidden = true; }); // Dialog mit Esc schließen
  $('#mein-btn').onclick = () => profile ? (location.hash = '#/mein') : openOnboarding(() => { location.hash = '#/mein'; route(); });
  $('#srctoggle').onchange = e => document.body.classList.toggle('show-src', e.target.checked);
  $('#cookie-open').onclick = () => { cookieCard(true); window.scrollTo(0, 0); };
  window.addEventListener('hashchange', async () => { await route(); window.scrollTo(0, 0); const v = $('#view'); if (v && !LIVE.open) v.focus({ preventScroll: true }); });
  $('#skip').onclick = e => { e.preventDefault(); const v = $('#view'); const h1 = v.querySelector('h1, h2'); (h1 || v).setAttribute('tabindex', '-1'); (h1 || v).focus(); };
  // Bewegung reduzieren: folgt dem Gerät, lässt sich hier zusätzlich einschalten
  const mt = $('#motion-toggle');
  if (mt) { mt.checked = load('oberfranken-motion') === 'reduce'; mt.onchange = () => { if (mt.checked) { store('oberfranken-motion', 'reduce'); document.documentElement.dataset.motion = 'reduce'; } else { try { localStorage.removeItem('oberfranken-motion'); } catch (e) {} delete document.documentElement.dataset.motion; } toast(mt.checked ? 'Animationen sind aus.' : 'Animationen folgen wieder dem Gerät.'); }; }


  /* ---------- So funktioniert's: was im Hintergrund passiert (mit Live-Zahlen) ---------- */
  async function pageHow() {
    const myRoute = routeSeq;
    const [info, items] = await Promise.all([api('/api/info').catch(() => ({ sources: [] })), api('/api/items').catch(() => [])]);
    if (myRoute !== routeSeq) return;
    const dt = s => s ? new Date(s.replace(' ', 'T')).toLocaleString(LOC(), { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '–';
    const srcs = (info.sources || []).filter(s => !/Beispiel/.test(s.name));
    const byRank = {}; items.forEach(i => { byRank[i.rank_label || 'Sonstige'] = (byRank[i.rank_label || 'Sonstige'] || 0) + 1; });
    const steps = [
      ['1', 'Abholen', `Jede Stunde fragt der Server ${srcs.length} geprüfte Quellen ab: RSS-Feeds, Veranstaltungskalender, Pressemitteilungen. robots.txt wird beachtet, zwischen Seiten wird gewartet.`],
      ['2', 'Prüfen', 'Doppelte Meldungen werden erkannt, vergangene Termine aussortiert, Orte geprüft (nur Oberfranken). Sensible Themen gehen zuerst an die Redaktion.'],
      ['3', 'Verstehen', 'Die KI fasst jeden Eintrag kurz zusammen, erkennt Thema, Ort und Datum. Der Originaltext bleibt beim Absender, wir verlinken immer auf ihn.'],
      ['4', 'Einordnen', 'Jede Quelle hat ein Ranking: amtliche Stellen zuerst, dann Städte und Landkreise, Hochschulen, Tourismus, Partner. Das Ranking ist nicht käuflich.'],
      ['5', 'Antworten', 'Fragst du etwas, sucht der Assistent zuerst in diesen Einträgen, holt das Wetter live dazu und formuliert eine Antwort nur daraus. Steht nichts da, sucht er nur auf geprüften Seiten oder sagt ehrlich: nichts gefunden.'],
      ['6', 'Vergessen', 'Deine Frage wird nicht gespeichert. Dein Profil bleibt in deinem Browser. Keine IP-Adresse, kein Tracking.']];
    $('#view').innerHTML = `<main class="wrap" style="padding-top:24px">
      <section class="about-hero"><p class="eyebrow">Transparenz</p><h1>So funktioniert's</h1>
        <p class="lead">Was passiert, wenn du klickst oder fragst? Hier siehst du jeden Schritt und die echten Zahlen von gerade eben.</p>
        <div class="facts"><div><b>${items.length}</b><span>aktuelle Einträge</span></div><div><b>${srcs.length}</b><span>angebundene Quellen</span></div><div><b>${dt(info.last_run)}</b><span>letzter Abruf</span></div><div><b>0</b><span>gespeicherte Fragen oder IP-Adressen</span></div></div></section>
      <section><div class="sec-head"><h2>Der Weg einer Information</h2></div>
        <div class="how">${steps.map(s => `<div class="box hstep"><span class="hn">${s[0]}</span><b>${s[1]}</b><p>${s[2]}</p></div>`).join('')}</div></section>
      <section><div class="sec-head"><div><h2>Quellen-Ranking</h2><p class="sub">Wem vertrauen wir wie sehr? Das Ranking steht an jeder Karte.</p></div></div>
        <div class="tbl" tabindex="0" role="region" aria-label="Tabelle, auf dem Handy seitlich scrollbar"><table><thead><tr><th>Stufe</th><th>Absender</th><th>Beispiele</th><th>Einträge jetzt</th></tr></thead><tbody>
        ${[['1', 'Amtliche Stelle', 'Regierung von Oberfranken, Bezirk Oberfranken'], ['2', 'Stadt / Landkreis', 'Städte Bayreuth, Coburg, Hof, Kulmbach, Landkreis Kronach'], ['3', 'Hochschule / Kammer', 'Uni Bamberg, Hochschule Coburg, IHK, HWK'], ['4', 'Tourismusverband', 'Fichtelgebirge, Frankenwald, Fränkische Schweiz'], ['5', 'Partner / Unternehmen', 'geprüfte Partner, z. B. Arbeitgeber der Region']].map(r => `<tr><td><span class="rk rk${r[0]}">${r[0]}</span></td><td>${r[1]}</td><td>${r[2]}</td><td>${byRank[r[1]] || (r[0] === '3' ? (byRank['Hochschule'] || 0) + (byRank['Kammer / Verband'] || 0) : 0)}</td></tr>`).join('')}</tbody></table></div></section>
      <section><div class="sec-head"><h2>Live: die Quellen gerade eben</h2></div>
        <div class="tbl" tabindex="0" role="region" aria-label="Tabelle, auf dem Handy seitlich scrollbar"><table><thead><tr><th>Quelle</th><th>Methode</th><th>Zuletzt abgerufen</th><th>Status</th></tr></thead><tbody>
        ${srcs.map(s => `<tr><td>${s.site ? `<a href="${esc(s.site)}" target="_blank" rel="noopener">${esc(s.name)}</a>` : esc(s.name)}</td><td>${esc(s.method)}</td><td>${dt(s.last_run)}</td><td>${s.ok ? '✅ ok' : '⚠️ Fehler'}</td></tr>`).join('')}</tbody></table></div></section>
      ${vsSection('vergleich-how')}
      <section class="box panel"><h2>Probier es aus</h2><p class="muted">Öffne unten rechts „Frag mich“ und klapp unter einer Antwort „Was passiert im Hintergrund?“ auf. Dort steht genau, was für diese Antwort passiert ist.</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" type="button" id="how-try">Assistent öffnen</button><a class="btn" href="#/datenschutz">Datenschutz im Detail</a></div></section></main>`;
    $('#how-try').onclick = () => liveOpen(true);
  }

  /* ---------- Nutzer-Sicht: hierher ziehen, sich weiterentwickeln ---------- */
  async function pageLive() {
    const myRoute = routeSeq;
    const items = await api('/api/items').catch(() => []);
    if (myRoute !== routeSeq) return;
    const next = items.filter(i => ['Wissenschaft', 'Wirtschaft'].includes(i.category) && i.event_date).slice(0, 6);
    const L = (u, t) => `<a href="${u}" target="_blank" rel="noopener">${t} ↗</a>`;
    const blocks = [
      ['Arbeit finden', 'Stellen in der Region, Beratung und Anerkennung von Abschlüssen.', [L('https://www.oberfrankenjobs.de', 'oberfrankenJOBS'), L('https://www.arbeitsagentur.de', 'Agentur für Arbeit'), L('https://www.ihk.de/bayreuth', 'IHK Bayreuth'), L('https://www.ihk.de/coburg', 'IHK Coburg')], 'Welche Jobs gibt es in Oberfranken für Fachkräfte?'],
      ['Studieren & Weiterbilden', 'Vier Hochschulen, duale Studiengänge, Weiterbildung neben dem Beruf.', [L('https://www.uni-bayreuth.de', 'Uni Bayreuth'), L('https://www.uni-bamberg.de', 'Uni Bamberg'), L('https://www.hs-coburg.de', 'Hochschule Coburg'), L('https://www.hof-university.de', 'Hochschule Hof')], 'Welche Infotage oder Messen gibt es für Studium und Ausbildung?'],
      ['Ausbildung & Handwerk', 'Ausbildungsplätze, Meister, Weiterbildung im Handwerk.', [L('https://www.hwk-oberfranken.de', 'Handwerkskammer'), L('https://www.ihk.de/bayreuth', 'IHK Ausbildung')], 'Wie finde ich eine Ausbildung im Handwerk?'],
      ['Ankommen & Wohnen', 'Bürgerservice, Anmeldung, Kita und Schule: zuständig sind Stadt oder Landkreis.', meta.regions.slice(0, 9).map(r => `<a href="#/region/${r}">${esc(RLABEL(r))}</a>`), 'Ich will nach Oberfranken ziehen. Wo fange ich an?'],
      ['Gründen & Förderung', 'Beratung und Förderprogramme für Gründer und Unternehmen.', [L('https://www.ihk.de/coburg', 'IHK Gründungsberatung'), L('https://www.stmwi.bayern.de', 'Wirtschaftsministerium'), L('https://www.oberfranken.de', 'Oberfranken Offensiv')], 'Welche Förderprogramme gibt es für Gründer?']];
    $('#view').innerHTML = `<main class="wrap" style="padding-top:24px">
      <section class="about-hero"><p class="eyebrow">Für Menschen mit Plänen</p><h1>Leben & weiterkommen in Oberfranken</h1>
        <p class="lead">Du überlegst herzuziehen oder willst dich hier weiterentwickeln? Hier findest du die offiziellen Stellen und echte Termine. Und wenn du nicht weißt, wo du anfangen sollst: frag einfach den Assistenten.</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" type="button" data-lv="Ich will nach Oberfranken ziehen. Wo fange ich an?">${SPARK} Frag den Assistenten</button><button class="btn" type="button" id="lv-profile">Profil „Neu hier“ einrichten</button></div></section>
      <section><div class="sec-head"><h2>Die wichtigsten Anlaufstellen</h2></div>
        <div class="lvgrid">${blocks.map(b => `<div class="box lvcard"><h3>${b[0]}</h3><p class="muted">${b[1]}</p><div class="lvlinks">${b[2].join('')}</div><button class="chip" type="button" data-lv="${esc(b[3])}">${SPARK} ${esc(b[3])}</button></div>`).join('')}</div></section>
      <section><div class="sec-head"><div><h2>Termine für deinen Start</h2><p class="sub">Echte Termine aus den Quellen: Messen, Infotage, Vorträge.</p></div></div>
        ${next.length ? cards(next, '') : '<p class="muted">Gerade keine passenden Termine.</p>'}</section></main>`;
    bindCards($('#view'));
    document.querySelectorAll('[data-lv]').forEach(b => b.onclick = () => { liveOpen(true); liveAsk(b.dataset.lv); });
    $('#lv-profile').onclick = () => openOnboarding(() => { location.hash = '#/mein'; route(); }, 'Neu hier');
  }

  /* ---------- Unternehmens-Sicht: Teil der Plattform werden ---------- */
  async function pagePartner() {
    const myRoute = routeSeq;
    const info = await api('/api/info').catch(() => ({ sources: [] }));
    if (myRoute !== routeSeq) return;
    const n = (info.sources || []).filter(s => !/Beispiel/.test(s.name)).length;
    $('#view').innerHTML = `<main class="wrap" style="padding-top:24px">
      <section class="about-hero"><p class="eyebrow">Für Unternehmen & Einrichtungen</p><h1>Teil von Oberfranken werden</h1>
        <p class="lead">Ihr seid Arbeitgeber, Hochschule, Verein oder Gemeinde und wollt Menschen erreichen, die hier leben, arbeiten oder herziehen wollen? Bindet eure Inhalte an. Sie erscheinen mit eurem Namen, eurem Link und einem Prüfsiegel.</p></section>
      <section><div class="sec-head"><h2>Was ihr davon habt</h2></div><div class="how">
        <div class="box hstep"><span class="hn">✓</span><b>Sichtbar bei den Richtigen</b><p>Eure Stellen, Ausbildungsplätze, Werksführungen und Termine erscheinen bei Menschen, die sich genau dafür interessieren, auch im KI-Assistenten.</p></div>
        <div class="box hstep"><span class="hn">✓</span><b>Euer Inhalt bleibt eurer</b><p>Wir zeigen eine kurze Zusammenfassung und verlinken immer auf eure Seite. Klicks landen bei euch.</p></div>
        <div class="box hstep"><span class="hn">✓</span><b>Vertrauen statt Werbung</b><p>Kein gekauftes Ranking. Ihr bekommt das Siegel „Partner / Unternehmen“, die Redaktion prüft jede neue Quelle.</p></div>
        <div class="box hstep"><span class="hn">✓</span><b>Wenig Aufwand</b><p>Ihr habt schon einen RSS-Feed, Veranstaltungskalender oder eine Karriereseite? Dann reicht der Link. Den Rest macht die Plattform jede Stunde automatisch.</p></div></div></section>
      <section><div class="sec-head"><h2>So läuft es ab</h2></div><ol class="flow">
        <li><b>Quelle vorschlagen</b> mit dem Formular unten (Website, Feed oder Kalender).</li>
        <li><b>Redaktion prüft</b> Absender, Inhalte und Datenschutz und legt die Ranking-Stufe fest.</li>
        <li><b>Automatisch aktuell:</b> Die Plattform holt eure Inhalte stündlich ab, wie bereits bei ${n} Quellen.</li>
        <li><b>Anonyme Zahlen:</b> Ihr seht, wie oft eure Einträge angesehen und geklickt wurden, ohne Daten über Personen.</li></ol></section>
      <section class="box panel"><h2>Quelle vorschlagen</h2>
        <div class="pform"><label class="lbl" for="p-org">Name (Unternehmen / Einrichtung)</label><input class="field" id="p-org" maxlength="120">
        <label class="lbl" for="p-site">Website</label><input class="field" id="p-site" placeholder="https://" maxlength="200">
        <label class="lbl" for="p-feed">Feed, Kalender oder Karriereseite (optional)</label><input class="field" id="p-feed" placeholder="https://…/rss.xml" maxlength="200">
        <label class="lbl" for="p-what">Was wollt ihr zeigen? (optional)</label><input class="field" id="p-what" placeholder="z. B. Ausbildungsplätze, Tag der offenen Tür" maxlength="300">
        <p class="small muted">Wir speichern nur diese Angaben, damit die Redaktion sich meldet. Keine personenbezogenen Daten nötig.</p>
        <button class="btn primary" type="button" id="p-send">Vorschlag senden</button></div></section></main>`;
    $('#p-send').onclick = async () => {
      try { await api('/api/partner', { body: { org: $('#p-org').value, site: $('#p-site').value, feed: $('#p-feed').value, what: $('#p-what').value } }); $('.pform').innerHTML = '<p><b>Danke!</b> Die Redaktion prüft euren Vorschlag und meldet sich.</p>'; track('partner'); }
      catch (e) { toast(e.message); }
    };
  }
  /* ---------- Live-Assistent: Chatfenster auf jeder Seite (tippen oder sprechen, mit Verlauf und Quellen) ---------- */
  const LIVE = { open: false, hist: [], talk: false, busy: false };
  // Logo „Wegweiser“: Wegweiser-Schild mit zwei Richtungspfeilen und Funken, in den Markenfarben
  const WW = (s = 40, cls = '') => `<svg class="ww-logo ${cls}" width="${s}" height="${s}" viewBox="0 0 48 48" aria-hidden="true"><defs><linearGradient id="wwg${s}${cls}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#E04A63"/><stop offset=".55" stop-color="#B3122E"/><stop offset="1" stop-color="#5A0A18"/></linearGradient></defs><circle cx="24" cy="24" r="24" fill="url(#wwg${s}${cls})"/><rect x="22.6" y="13" width="2.8" height="26" rx="1.4" fill="#FBEAED"/><path class="ww-s1" d="M12.5 15.5h15.8l4.2 3.6-4.2 3.6H12.5a1 1 0 0 1-1-1v-5.2a1 1 0 0 1 1-1z" fill="#fff"/><path class="ww-s2" d="M35.5 25.5H19.7l-4.2 3.6 4.2 3.6h15.8a1 1 0 0 0 1-1v-5.2a1 1 0 0 0-1-1z" fill="#F7C9D1"/><path class="ww-spark" d="M24 4.5l1.2 3 3 1.2-3 1.2-1.2 3-1.2-3-3-1.2 3-1.2z" fill="#FFD7A3"/></svg>`;
  const LCHIPS = () => {
    const r = town() || REGION_NAMES[home()] || home();
    return [['🎉', 'Was ist am Wochenende los?'], ['🌦️', `Wie wird das Wetter in ${r}?`], ['🧭', 'Ich will nach Oberfranken ziehen. Wo fange ich an?'], ['💼', 'Welche Förderprogramme gibt es für Gründer?']];
  };
  function liveInit() {
    const fab = document.createElement('button');
    fab.className = 'live-fab'; fab.type = 'button'; fab.id = 'live-fab';
    fab.innerHTML = `<span class="ww-badge">${WW(44, 'fab')}<i class="ww-dot"></i></span><span class="ww-txt"><b>Frag mich</b><small>Frag mich etwas</small></span>`;
    fab.setAttribute('aria-label', '„Frag mich“ öffnen: KI-Assistent für Oberfranken');
    const hint = document.createElement('div');
    hint.className = 'ww-hint'; hint.id = 'ww-hint'; hint.hidden = true;
    hint.innerHTML = `<button type="button" class="ww-hint-x" aria-label="Hinweis schließen">✕</button><b>Hallo! Wohin soll's gehen?</b><span>Frag mich nach Terminen, Wetter oder dem Leben in Oberfranken, gern auch per Sprache.</span>`;
    const box = document.createElement('section');
    box.className = 'live'; box.id = 'live'; box.hidden = true; box.setAttribute('aria-label', 'Frag mich, KI-Assistent');
    box.innerHTML = `<header class="live-h"><div class="live-id"><span class="ww-badge">${WW(42, 'head')}<i class="ww-dot"></i></span><div><b>Frag mich</b><small>KI-Begleiter · nur geprüfte Quellen</small></div></div>
        <div class="live-tools"><button type="button" class="live-talk" id="live-call" title="Live-Gespräch: einfach sprechen wie am Telefon">📞 Live</button>
        <button type="button" class="iconbtn" id="live-new" title="Neues Gespräch" aria-label="Neues Gespräch">↺</button>
        <button type="button" class="iconbtn" id="live-x" aria-label="Schließen">✕</button></div></header>
      <div class="live-msgs" id="live-msgs" aria-live="polite"></div>
      <form class="live-in" id="live-form"><div class="live-field"><input id="live-q" autocomplete="off" placeholder="Deine Frage …" aria-label="Deine Frage"><span class="wave" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span></div>
        ${true ? `<button type="button" class="mic" id="live-mic" aria-label="Frage sprechen" title="Frage sprechen"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg></button>` : ''}<button type="submit" class="send" aria-label="Senden">${ARROW}</button></form>
      <p class="live-foot">Immer mit Quelle · Fragen werden nicht gespeichert · <a href="#/so-funktionierts" data-live-close>So funktioniert's</a></p>`;
    document.body.append(fab, hint, box);
    fab.onclick = () => liveOpen(true);
    $('#live-x').onclick = () => liveOpen(false);
    $('#live-new').onclick = () => { LIVE.hist = []; liveWelcome(); };
    box.querySelectorAll('.live-foot [data-live-close]').forEach(x => x.onclick = () => { if (innerWidth < 760) liveOpen(false); });
    const inp = $('#live-q');
    $('#live-form').onsubmit = e => { e.preventDefault(); const q = inp.value.trim(); if (q && !LIVE.busy) { inp.value = ''; liveAsk(q); } };
    if ($('#live-mic')) $('#live-mic').onclick = () => listen(inp, $('#live-mic'), t => { inp.value = ''; VOICE.spoken = true; liveAsk(t); });
    $('#live-call').onclick = () => callOpen();
    if ($('#live-talk')) $('#live-talk').onclick = () => {
      LIVE.talk = !LIVE.talk; $('#live-talk').setAttribute('aria-pressed', LIVE.talk);
      toast(LIVE.talk ? 'Gesprächsmodus an: sprich einfach, ich antworte laut und höre dann wieder zu.' : 'Gesprächsmodus aus.');
      if (LIVE.talk && $('#live-mic') && !VOICE.rec) $('#live-mic').click();
    };
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && LIVE.open) liveOpen(false); });
    // einmal pro Sitzung ein kurzer Hinweis neben dem Knopf (verschwindet von selbst)
    let seen = false; try { seen = sessionStorage.getItem('ww-hint') === '1'; } catch (e) {}
    if (!seen) setTimeout(() => {
      if (LIVE.open || innerWidth < 760 || ($('#modal') && !$('#modal').hidden)) return;
      hint.hidden = false; try { sessionStorage.setItem('ww-hint', '1'); } catch (e) {}
      applyLang(hint);
      setTimeout(() => { hint.hidden = true; }, 9000);
    }, 4500);
    hint.onclick = e => { hint.hidden = true; if (!e.target.closest('.ww-hint-x')) liveOpen(true); };
    liveWelcome();
  }
  function liveOpen(on) {
    LIVE.open = on; $('#live').hidden = !on; $('#live-fab').hidden = on; $('#ww-hint').hidden = true;
    if (on) { setTimeout(() => $('#live-q').focus(), 50); track('live:open'); applyLang($('#live')); }
    else if (window.speechSynthesis) speechSynthesis.cancel();
  }
  function liveMsg(html, who) {
    const list = $('#live-msgs');
    const m = document.createElement('div'); m.className = 'lm ' + who; m.innerHTML = html;
    if (who === 'bot') {
      const row = document.createElement('div'); row.className = 'lrow';
      row.innerHTML = `<span class="lav">${WW(30, 'av')}</span>`; row.append(m); list.append(row);
    } else list.append(m);
    list.scrollTop = list.scrollHeight; return m;
  }
  function liveWelcome() {
    $('#live-msgs').innerHTML = `<div class="ww-hello">${WW(72, 'hello')}<h3>${greet()}! Ich bin „Frag mich“, dein KI-Assistent.</h3>
      <p>Frag mich nach Ausflügen, Terminen, Wetter, Arbeit oder dem Leben in Oberfranken. Ich antworte nur aus geprüften Quellen und zeige sie dir immer.</p>
      <button type="button" class="ww-callbtn" id="ww-callbtn"><span class="ww-callic">📞</span><span><b>Live mit mir sprechen</b><small>Wie ein Telefonat: fragen, Antwort hören, weiterreden</small></span></button>
      <div class="ww-chips">${LCHIPS().map(([i, q]) => `<button type="button" data-lq="${esc(q)}"><span>${i}</span>${esc(q)}</button>`).join('')}</div></div>`;
    $('#live-msgs').querySelectorAll('[data-lq]').forEach(b => b.onclick = () => liveAsk(b.dataset.lq));
    if ($('#ww-callbtn')) $('#ww-callbtn').onclick = () => callOpen();
  }
  async function liveAsk(q) {
    LIVE.busy = true;
    liveMsg(`<p>${esc(q)}</p>`, 'me');
    const wait = liveMsg('<p class="dots"><i></i><i></i><i></i></p><p class="note">Ich suche in den Inhalten der Region …</p>', 'bot');
    const hello = $('#live-msgs .ww-hello'); if (hello) hello.classList.add('small');
    const spoken = VOICE.spoken; VOICE.spoken = false;
    try {
      const r = await api('/api/ask', { body: { q, home: home(), town: town(), region: '', history: LIVE.hist, lang: LANG } });
      LIVE.hist = [...LIVE.hist, { q, a: r.answer }].slice(-3); track('live:ask');
      const wx = r.weather ? `<p class="lwx">${r.weather.icon} ${esc(REGION_NAMES[r.weather.region] || r.weather.region)}: ${esc(r.weather.text)}, bis ${r.weather.tmax} °C</p>` : '';
      const fc = (r.forecast || []).length > 1 ? `<div class="lfc">${r.forecast.slice(0, 3).map(f => `<span>${f.icon} ${esc(new Date(f.date + 'T00:00').toLocaleDateString(LOC(), { weekday: 'short' }))} ${f.tmax}°</span>`).join('')}</div>` : '';
      const its = [...(r.items || []), ...(r.alternatives || [])].slice(0, 3);
      const list = its.length ? `<ul class="litems">${its.map(i => `<li><a href="${esc(i.url || '#')}" target="_blank" rel="noopener" data-click="${i.id}"><b>${esc(i.title)}</b></a><span>${[i.event_date ? fmt(i.event_date) : '', i.location || ''].filter(Boolean).map(esc).join(' · ')}</span><small>Quelle: ${i.url ? `<a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.source || '')}</a>` : esc(i.source || '')}</small></li>`).join('')}</ul>` : '';
      const web = (r.web_sources || []).length ? `<div class="lsrc"><span class="note">Quellen:</span>${r.web_sources.map(w => `<a href="${esc(w.url)}" target="_blank" rel="noopener" title="${esc(w.url)}">${esc(w.domain)} ↗</a>`).join('')}</div>` : '';
      const fu = (r.followups || []).slice(0, 3);
      wait.innerHTML = `${fc || wx}<p class="txt">${esc(r.answer)}</p>${list}${web}${(r.trace || []).length ? `<details class="trace"><summary>Was passiert im Hintergrund?</summary><ol>${r.trace.map(t => `<li>${esc(t)}</li>`).join('')}</ol><a href="#/so-funktionierts" data-live-close>So funktioniert die Plattform →</a></details>` : ''}
        <div class="lact">${VOICE.canSpeak ? `<button type="button" class="speak" data-speak>🔊 Vorlesen</button>` : ''}<span class="note">${esc(r.engine || '')}</span></div>
        ${fu.length ? `<div class="chips">${fu.map(f => `<button class="chip" type="button" data-lq="${esc(f)}">${esc(f)}</button>`).join('')}</div>` : ''}`;
      wait.querySelectorAll('[data-lq]').forEach(b => b.onclick = () => liveAsk(b.dataset.lq));
      wait.querySelectorAll('[data-live-close]').forEach(x => x.onclick = () => { if (innerWidth < 760) liveOpen(false); });
      wait.querySelectorAll('[data-click]').forEach(a => a.addEventListener('click', () => api(`/api/items/${a.dataset.click}/click`, { body: {} }).catch(() => {})));
      const sp = $('[data-speak]', wait);
      const again = () => { if (LIVE.talk && LIVE.open && $('#live-mic') && !VOICE.rec) setTimeout(() => $('#live-mic').click(), 400); };
      if (sp) sp.onclick = () => speak(r.answer, sp);
      if (sp && (spoken || LIVE.talk)) speak(r.answer, sp, again);
      $('#live-msgs').scrollTop = $('#live-msgs').scrollHeight;
    } catch (e) { wait.innerHTML = `<p>${esc(e.message)}</p>`; }
    LIVE.busy = false;
  }

  /* ---------- Live-Gespräch mit „Frag mich“ (Vollbild, wie ein Telefonat) ----------
     Ablauf: zuhören (Sprache -> Text im Browser) -> fragen (/api/ask, gleiche Quellen wie im Chat) -> kurze Antwort sprechen
     -> wieder zuhören. Unterbrechen per Knopf oder Tippen. Nichts wird aufgenommen oder gespeichert. */
  const CALL = { on: false, state: 'idle', rec: null, muted: false, t0: 0, timer: null, misses: 0, finalText: '' };
  function callShort(r) {
    // fürs Sprechen: 2 Sätze + die wichtigsten Treffer; der volle Text steht im Chat
    const sent = (r.answer || '').replace(/\[\d+\]/g, '').split(/(?<=[.!?])\s+/).slice(0, 2).join(' ');
    const its = [...(r.items || []), ...(r.alternatives || [])].slice(0, 2);
    const EN = LANG === 'en';
    const ex = its.length ? (EN ? ' For example: ' : ' Zum Beispiel: ') + its.map(i => `${i.title.replace(/[„“"]/g, '').split(/:\s| - | – |\|/)[0].trim()}${i.event_date ? ', ' + new Date(i.event_date.slice(0, 10) + 'T00:00').toLocaleDateString(LOC(), { weekday: 'long', day: 'numeric', month: 'long' }) : ''}${i.location ? ' in ' + i.location : ''}`).join(EN ? '; and ' : '; und ') + '.' : '';
    return (sent + ex + (its.length ? (EN ? ' You can see the details on screen.' : ' Die Details siehst du auf dem Bildschirm.') : '')).trim();
  }
  function callUI() {
    if ($('#call')) return;
    const c = document.createElement('section');
    c.id = 'call'; c.className = 'call'; c.hidden = true; c.setAttribute('aria-label', 'Live-Gespräch mit „Frag mich“'); c.setAttribute('role', 'dialog');
    c.innerHTML = `<header class="call-h"><span class="call-live"><i></i>LIVE</span><span id="call-time">00:00</span><span class="call-note">Frag mich · nur geprüfte Quellen</span></header>
      <div class="call-mid">
        <div class="orb" id="call-orb"><span class="ring r1"></span><span class="ring r2"></span><span class="ring r3"></span>${WW(140, 'call')}</div>
        <p class="call-state" id="call-state" aria-live="polite">Verbinde …</p>
        <p class="call-you" id="call-you"></p>
        <p class="call-cap" id="call-cap" aria-live="polite"></p>
        <div class="call-cards" id="call-cards"></div>
        ${VOICE.canListen ? '' : `<form class="call-type" id="call-type"><input id="call-q" placeholder="Dein Browser kann keine Sprache erkennen: hier tippen" autocomplete="off"><button type="submit" aria-label="Senden">${ARROW}</button></form>`}
      </div>
      <footer class="call-f">
        <button type="button" class="cbtn" id="call-mute" aria-pressed="false"><span>🎙️</span><small>Stumm</small></button>
        <button type="button" class="cbtn" id="call-skip"><span>⏭️</span><small>Unterbrechen</small></button>
        <button type="button" class="cbtn" id="call-text"><span>💬</span><small>Als Text</small></button>
        <button type="button" class="cbtn end" id="call-end" aria-label="Gespräch beenden"><span>✕</span><small>Beenden</small></button>
      </footer>
      <p class="call-priv">Dein Browser wandelt Sprache in Text um. Wir bekommen nur den Text und speichern nichts. <a href="#/datenschutz" id="call-priv">Mehr</a></p>`;
    document.body.append(c);
    $('#call-end').onclick = () => callClose();
    $('#call-text').onclick = () => { callClose(); liveOpen(true); };
    $('#call-skip').onclick = () => callInterrupt();
    $('#call-mute').onclick = () => { CALL.muted = !CALL.muted; $('#call-mute').setAttribute('aria-pressed', CALL.muted); $('#call-mute small').textContent = CALL.muted ? 'Stumm an' : 'Stumm'; if (CALL.muted) { callStopListen(); callSet('muted'); } else callListen(); };
    $('#call-orb').onclick = () => { if (CALL.state === 'speaking') callInterrupt(); else if (CALL.state !== 'thinking' && !CALL.rec) { CALL.muted = false; callListen(); } };
    $('#call-priv').onclick = () => callClose();
    if ($('#call-type')) $('#call-type').onsubmit = e => { e.preventDefault(); const q = $('#call-q').value.trim(); if (q) { $('#call-q').value = ''; callAsk(q); } };
    document.addEventListener('keydown', e => { if (!CALL.on) return; if (e.key === 'Escape') callClose(); if (e.key === ' ' && e.target === document.body) { e.preventDefault(); callInterrupt(); } });
  }
  function callSet(state, text) {
    CALL.state = state;
    const c = $('#call'); if (!c) return;
    c.dataset.state = state;
    const T = { listening: 'Ich höre zu …', thinking: 'Ich schaue nach …', speaking: 'Ich spreche · tippen zum Unterbrechen', muted: 'Mikrofon aus · tippe auf das Logo zum Weitersprechen', idle: 'Tippe auf das Logo und sprich', connecting: 'Verbinde …' };
    $('#call-state').textContent = text || T[state] || '';
    $('#call-skip').disabled = state !== 'speaking';
    applyLang($('#call-state'));
  }
  function callOpen() {
    if (!VOICE.canSpeak) { toast('Dein Browser kann nicht vorlesen. Nutze den Text-Chat.'); liveOpen(true); return; }
    const go = () => {
      callUI(); liveOpen(false); $('#live-fab').hidden = true;
      CALL.on = true; CALL.misses = 0; CALL.muted = false; CALL.t0 = Date.now();
      $('#call').hidden = false; document.body.classList.add('in-call');
      $('#call-you').textContent = ''; $('#call-cap').textContent = ''; $('#call-cards').innerHTML = '';
      clearInterval(CALL.timer);
      CALL.timer = setInterval(() => { const s = Math.floor((Date.now() - CALL.t0) / 1000); $('#call-time').textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0'); }, 1000);
      applyLang($('#call')); track('call:start');
      const where = town() || REGION_NAMES[home()] || home();
      callSay(LANG === 'en' ? `Hi, this is “Ask me”. Just ask me something, for example: what's on this weekend in ${where}?` : `${greet()}! Hier ist „Frag mich“. Stell mir einfach eine Frage, zum Beispiel: Was ist am Wochenende in ${where} los?`, () => callListen());
    };
    if (VOICE.canListen) voiceOk(async () => { const bad = await micPermission(); if (bad) { micProblem(bad); VOICE.callBlocked = true; } go(); }); else go();
  }
  function callClose() {
    CALL.on = false; callStopListen(); clearInterval(CALL.timer);
    try { speechSynthesis.cancel(); } catch (e) {}
    if ($('#call')) $('#call').hidden = true;
    document.body.classList.remove('in-call');
    if (!LIVE.open && innerWidth >= 760) $('#live-fab').hidden = false;
    track('call:end');
  }
  function callStopListen() { if (CALL.rec) { try { CALL.rec.onend = null; CALL.rec.abort(); } catch (e) {} CALL.rec = null; } }
  function callListen() {
    if (VOICE.callBlocked) { VOICE.callBlocked = false; CALL.muted = true; callSet('muted', LANG === 'en' ? 'Microphone not available. Use “As text” or allow the microphone.' : 'Mikrofon nicht verfügbar. Nutze „Als Text“ oder erlaube das Mikrofon.'); return; }
    if (!CALL.on || CALL.muted || !VOICE.canListen) { if (!VOICE.canListen) callSet('idle', LANG === 'en' ? 'Type your question below' : 'Tippe deine Frage unten ein'); return; }
    callStopListen();
    const rec = new SR(); CALL.rec = rec; CALL.finalText = '';
    rec.lang = LANG === 'en' ? 'en-GB' : 'de-DE'; rec.interimResults = true; rec.maxAlternatives = 1;
    callSet('listening');
    rec.onresult = e => { let t = ''; for (const r of e.results) { t += r[0].transcript; if (r.isFinal) CALL.finalText = t; } $('#call-you').textContent = '„' + t + '“'; };
    rec.onerror = e => {
      if (['not-allowed', 'service-not-allowed', 'audio-capture', 'network', 'language-not-supported'].includes(e.error)) { CALL.muted = true; callSet('muted', LANG === 'en' ? 'Microphone not available. Use “As text” or allow the microphone.' : 'Mikrofon nicht verfügbar. Nutze „Als Text“ oder erlaube das Mikrofon.'); micProblem(e.error); }
      if (e.error === 'no-speech') CALL.misses++;
    };
    rec.onend = () => {
      if (CALL.rec !== rec) return;
      CALL.rec = null;
      const t = (CALL.finalText || '').trim();
      if (!CALL.on || CALL.muted) return;
      if (t) { CALL.misses = 0; callAsk(t); return; }
      if (CALL.misses >= 2) { callSet('idle', 'Bist du noch da? Tippe auf das Logo und sprich.'); return; }
      setTimeout(() => callListen(), 250); // nichts gehört: weiter zuhören
    };
    try { rec.start(); } catch (e) { CALL.rec = null; setTimeout(() => callListen(), 400); }
  }
  function callSay(text, after) {
    callSet('speaking'); $('#call-cap').textContent = text;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = LANG === 'en' ? 'en-GB' : 'de-DE'; try { const v = bestVoice(); if (v) u.voice = v; } catch (e) {} u.rate = 1.04;
    let done = false;
    const fin = () => { if (done) return; done = true; if (CALL.on && after) after(); };
    u.onend = fin; u.onerror = fin;
    CALL.after = after;
    try { speechSynthesis.cancel(); speechSynthesis.speak(u); } catch (e) { fin(); }
    // Sicherheitsnetz: manche Browser melden das Ende nicht
    setTimeout(() => { if (!done && !speechSynthesis.speaking) fin(); }, Math.max(4000, text.length * 90));
  }
  function callInterrupt() {
    if (CALL.state !== 'speaking') return;
    try { speechSynthesis.cancel(); } catch (e) {}
    CALL.muted = false; setTimeout(() => callListen(), 150); track('call:interrupt');
  }
  async function callAsk(q) {
    callStopListen(); callSet('thinking');
    $('#call-you').textContent = '„' + q + '“'; $('#call-cap').textContent = ''; $('#call-cards').innerHTML = '';
    // Gesprächsverlauf auch im Chat mitschreiben
    liveMsg(`<p>${esc(q)}</p>`, 'me');
    try {
      const r = await api('/api/ask', { body: { q, home: home(), town: town(), region: '', history: LIVE.hist, lang: LANG } });
      if (!CALL.on) return;
      LIVE.hist = [...LIVE.hist, { q, a: r.answer }].slice(-3); track('call:ask');
      liveMsg(`<p class="txt">${esc(r.answer)}</p><p class="note">📞 im Live-Gespräch beantwortet · ${esc(r.engine || '')}</p>`, 'bot');
      const its = [...(r.items || []), ...(r.alternatives || [])].slice(0, 3);
      const wx = (r.forecast || []).length > 1 ? `<div class="call-wx">${r.forecast.slice(0, 3).map(f => `<span>${f.icon} ${esc(new Date(f.date + 'T00:00').toLocaleDateString(LOC(), { weekday: 'short' }))} ${f.tmax}°</span>`).join('')}</div>` : '';
      $('#call-cards').innerHTML = wx + its.map(i => `<a class="ccard" href="${esc(i.url || '#')}" target="_blank" rel="noopener"><b>${esc(i.title)}</b><span>${[i.event_date ? fmt(i.event_date) : '', i.location || ''].filter(Boolean).map(esc).join(' · ')}</span><small>Quelle: ${esc(i.source || '')}${i.rank_label ? ' · ' + esc(i.rank_label) : ''}</small></a>`).join('') + ((r.web_sources || []).length ? `<div class="call-src">Quellen: ${r.web_sources.map(w => `<a href="${esc(w.url)}" target="_blank" rel="noopener">${esc(w.domain)}</a>`).join(' · ')}</div>` : '');
      applyLang($('#call-cards'));
      callSay(callShort(r), () => callListen());
    } catch (e) { callSay('Da ist gerade etwas schiefgegangen. Frag mich gern noch einmal.', () => callListen()); }
  }
  bindGo(); cookieCard(false); liveInit();
  api('/api/meta').then(m => { meta = m; route().then(guessRegion); });
})();
