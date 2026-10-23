"""Ein Durchlauf: Quellen abrufen -> Format -> Duplikate -> KI -> Prüfung -> Datenbank."""
import json
import os
import re
from datetime import date, datetime

from . import db
from .ai import pick_town, process, process_budget_reset
from .collect import OF_TOWNS, UA, SourceError, collect, geocode

CANCELLED = re.compile(r"\b(abgesagt|entfällt|entfaellt|ausgefallen|verschoben|cancelled)\b", re.I)

CONF_MIN = 0.75
SENSITIVE = ["unfall", "polizei", "verletzt", "wahl", "partei", "krankheit", "klinik"]


def words(t):
    return set(w for w in re.findall(r"[a-zäöüß]{5,}", (t or "").lower()))


def find_duplicate(title, url=None, exclude_id=None):
    if url:
        r = db.one("select id,title from items where url=?", (url,))
        if r and r["id"] != exclude_id:
            return r
    nt = words(title)
    if not nt:
        return None
    for r in db.rows("select id,title from items where status!='rejected' order by id desc limit 400"):
        if r["id"] == exclude_id:
            continue
        it = words(r["title"])
        if it and len(nt & it) / max(len(nt), len(it)) >= 0.6:
            return r
    return None


def checks(res, exclude_id=None, trusted=False):
    """Qualitätssicherung: Liste der Gründe, warum ein Mensch prüfen soll.
    trusted = amtliche Quelle (z. B. Regierung): kein Datum/Ort/KI-Sicherheit nötig, Duplikate und Sensibles prüfen wir trotzdem."""
    flags = []
    cat = res.get("category")
    ev = res.get("event_date")
    loc = res.get("location")
    if ev:
        try:
            if date.fromisoformat(ev[:10]) < date.today():
                flags.append("Datum liegt in der Vergangenheit")
        except ValueError:
            flags.append("Datum nicht lesbar")
    elif cat in ("Events", "Kultur", "Tourismus") and not trusted:
        flags.append("Kein Datum erkannt")
    if not loc:
        if not trusted:
            flags.append("Kein Ort erkannt")
    elif loc not in OF_TOWNS:
        flags.append(f"Ort liegt außerhalb Oberfrankens ({loc})")
    if float(res.get("confidence") or 0) < CONF_MIN and not trusted:
        flags.append("KI-Sicherheit unter 75 %")
    text = (res.get("title", "") + " " + res.get("summary", "")).lower()
    if any(w in text for w in SENSITIVE):
        flags.append("Sensibles Thema, bitte prüfen")
    d = find_duplicate(res.get("title"), None, exclude_id)
    if d:
        flags.append(f"Mögliches Duplikat von „{d['title']}“")
    return flags


def save_item(raw, res, src, flags):
    loc = res.get("location") or raw.get("location")
    coords = geocode(loc) if loc in OF_TOWNS else None
    status = "review" if flags else "live"
    return db.exec_(
        """insert into items(title,text,url,source_id,source,method,published,summary,summary_en,category,keywords,priority,
           location,region,lat,lon,event_date,confidence,engine,status,flags) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (res.get("title") or raw.get("title"), raw.get("text"), raw.get("url"), src.get("id"), src.get("name"), src.get("method"),
         raw.get("published"), res.get("summary"), res.get("summary_en"), res.get("category"), json.dumps(res.get("keywords") or [], ensure_ascii=False),
         res.get("priority"), loc, OF_TOWNS.get(loc), coords[0] if coords else None, coords[1] if coords else None,
         res.get("event_date") or raw.get("event_date"), res.get("confidence"), res.get("engine"), status,
         json.dumps(flags, ensure_ascii=False)),
    ), status


def run(only=None):
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    process_budget_reset()
    rid = db.exec_("insert into runs(started) values(?)", (started,))
    st = dict(fetched=0, new=0, duplicates=0, processed=0, live=0, review=0, tokens_in=0, tokens_out=0)
    log = []
    sources = db.rows("select * from sources where enabled=1" + (" and id=?" if only else ""), (only,) if only else ())
    for src in sources:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            src = dict(src)
            src["known"] = {r["url"] for r in db.rows("select url from items where source_id=? and url is not null", (src["id"],))}
            items = collect(src)
        except (SourceError, Exception) as e:
            msg = str(e) if isinstance(e, SourceError) else f"{type(e).__name__}: {e}"[:160]
            db.exec_("update sources set last_run=?, last_status='err', last_error=?, last_new=0 where id=?", (now, msg, src["id"]))
            log.append(f"✗ {src['name']}: {msg}")
            continue
        st["fetched"] += len(items)
        new = 0
        for raw in items:
            if not raw.get("title"):
                continue
            if CANCELLED.search(raw["title"]):
                continue  # abgesagte Termine gar nicht erst zeigen
            if find_duplicate(raw["title"], raw.get("url")):
                st["duplicates"] += 1
                continue
            text = "\n".join(x for x in [raw["title"], raw.get("text") or "",
                                         f"Ort: {raw['location']}" if raw.get("location") else "",
                                         f"Datum: {raw['event_date']}" if raw.get("event_date") else ""] if x)
            res, tin, tout = process(text)
            if raw.get("event_date") and not res.get("event_date"):
                res["event_date"] = raw["event_date"]
            # Ort: 1. was der Termin selbst angibt, 2. Titel/Text (KI oder Regeln), 3. feste Stadt der Quelle
            cfg0 = _src_cfg(src["id"])
            if raw.get("location_exact") or (raw.get("location") and not res.get("location")):
                res["location"] = raw["location"]
            elif cfg0.get("venue_fixed") and raw.get("location"):
                # Kalender einer Stadt: Ort aus dem Titel, sonst die Stadt selbst (nicht ein im Text erwähnter Ort)
                res["location"] = pick_town(raw["title"], "") or raw["location"]
            st["tokens_in"] += tin
            st["tokens_out"] += tout
            st["processed"] += 1
            cfg = _src_cfg(src["id"])
            if cfg.get("category"):
                res["category"] = cfg["category"]  # feste Kategorie der Quelle, z. B. „Region“ für Behördenmeldungen
                if res.get("event_date") and not raw.get("event_date"):
                    res["event_date"] = None  # Behördenmeldungen sind keine Termine
            flags = checks(res, trusted=bool(cfg.get("trusted")))
            try:
                _, status = save_item(raw, res, src, flags)
            except Exception:
                st["duplicates"] += 1
                continue
            new += 1
            st[status] += 1
        st["new"] += new
        db.exec_("update sources set last_run=?, last_status='ok', last_error=null, last_new=?, total=total+? where id=?",
                 (now, new, new, src["id"]))
        log.append(f"✓ {src['name']} ({src['method']}): {len(items)} abgerufen, {new} neu")
    dead = check_links()
    if dead:
        log.append(f"⚠ {dead} Einträge ausgeblendet (abgesagt oder Original-Seite nicht mehr erreichbar)")
    db.exec_("""update runs set finished=?, fetched=?, new=?, duplicates=?, processed=?, live=?, review=?, tokens_in=?, tokens_out=?, log=? where id=?""",
             (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st["fetched"], st["new"], st["duplicates"], st["processed"],
              st["live"], st["review"], st["tokens_in"], st["tokens_out"], "\n".join(log), rid))
    return rid


def check_links(max_checks=25):
    """Abgesagte Termine und tote Original-Links ausblenden, damit „Quelle“ immer funktioniert."""
    import httpx
    hidden = 0
    for r in db.rows("select id,title from items where status='live'"):
        if CANCELLED.search(r["title"] or ""):
            db.exec_("update items set status='rejected', flags=? where id=?", (json.dumps(["abgesagt"]), r["id"]))
            hidden += 1
    today = date.today().isoformat()
    rows = db.rows("select id,url from items where status='live' and url like 'http%' and (event_date is null or event_date>=?) "
                   "order by random() limit ?", (today, max_checks))
    for r in rows:
        try:
            resp = httpx.get(r["url"], headers={"User-Agent": UA}, timeout=10, follow_redirects=True)
            code = resp.status_code
        except Exception:
            continue  # Netzwerkfehler: nicht gleich ausblenden
        if code in (404, 410):
            db.exec_("update items set status='rejected', flags=? where id=?", (json.dumps([f"Original-Seite {code}"]), r["id"]))
            hidden += 1
    return hidden


def _src_cfg(sid):
    path = os.path.join(os.path.dirname(__file__), "sources.json")
    try:
        with open(path, encoding="utf-8") as f:
            return next((x for x in json.load(f) if x.get("id") == sid), {})
    except Exception:
        return {}


def load_sources():
    path = os.path.join(os.path.dirname(__file__), "sources.json")
    with open(path, encoding="utf-8") as f:
        conf = json.load(f)
        ids = [s["id"] for s in conf]
        db.exec_(f"update sources set enabled=0 where id not in ({','.join('?' * len(ids))})", tuple(ids))  # entfernte Quellen abschalten
        for s in conf:
            db.exec_("""insert into sources(id,name,method,url,enabled) values(?,?,?,?,?)
                        on conflict(id) do update set name=excluded.name, method=excluded.method, url=excluded.url, enabled=excluded.enabled""",
                     (s["id"], s["name"], s["method"], s["url"], 1 if s.get("enabled", True) else 0))
