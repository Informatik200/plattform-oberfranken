"""Web-Server: Website + API für Nutzer und Redaktion."""
import asyncio
import json
import os
import re
import secrets
import threading
from datetime import date, datetime, timedelta

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import en, agent, ai, db, envfile, pipeline, privacy, sitesearch
from .collect import COORDS, OF_TOWNS, PLACES, TOWN_COORDS
with open(os.path.join(os.path.dirname(__file__), "places.json"), encoding="utf-8") as _pf:
    PLACES_META = json.load(_pf)["meta"]

ROOT = os.path.join(os.path.dirname(__file__), "..")
STATIC = os.path.join(ROOT, "static")
ADMIN_USER = os.environ.get("ADMIN_USER", "redaktion@beispiel.de")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "demo1234")
INTERVAL = int(os.environ.get("RUN_INTERVAL_MIN", "60"))
REGIONS = ["Bamberg", "Bayreuth", "Coburg", "Forchheim", "Hof", "Kronach", "Kulmbach", "Lichtenfels", "Wunsiedel"]
ROLES = {"Bewohner": ["Events", "Kultur"], "Gast": ["Tourismus", "Events", "Kultur"], "Fachkraft": ["Wirtschaft", "Wissenschaft"],
         "Neu hier": ["Region", "Wirtschaft", "Kultur"], "Lernen & Karriere": ["Wissenschaft", "Wirtschaft"]}

# Quellen-Ranking (Transparenz): wie verlässlich ist der Absender? 1 = amtlich … 5 = Partner/Unternehmen
RANKS = {"Behörde": (1, "Amtliche Stelle"), "Kommune": (2, "Stadt / Landkreis"), "Hochschule": (3, "Hochschule"),
         "Kammer": (3, "Kammer / Verband"), "Tourismus": (4, "Tourismusverband"), "Partner": (5, "Partner / Unternehmen")}
_SRC = {"t": 0, "conf": {}}


def src_conf():
    """sources.json (zwischengespeichert, neu geladen wenn geändert)."""
    p = os.path.join(os.path.dirname(__file__), "sources.json")
    t = os.path.getmtime(p)
    if t != _SRC["t"]:
        with open(p, encoding="utf-8") as f:
            _SRC.update(t=t, conf={s["id"]: s for s in json.load(f)})
    return _SRC["conf"]


def site_of(cfg, url=None):
    """Startseite des Anbieters: „Quelle“ führt auf die Website, nicht auf den einzelnen Termin."""
    if cfg.get("site"):
        return cfg["site"]
    from urllib.parse import urlparse
    u = urlparse(url or cfg.get("url") or "")
    return f"{u.scheme}://{u.netloc}/" if u.scheme in ("http", "https") and u.netloc else None


def with_rank(it):
    c = src_conf().get(it.get("source_id")) or {}
    it["site"] = site_of(c, it.get("url"))
    r = c.get("rank") or ("Partner" if not c.get("trusted") else "Kommune")
    it["rank"], it["rank_label"] = RANKS.get(r, (5, r))[0], RANKS.get(r, (5, r))[1]
    it["stufe"] = "Stufe 1: Oberfranken"
    return it

app = FastAPI(title="Bühne Oberfranken")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
TOKENS = set()
RUNNING = threading.Lock()


def start_run(only=None):
    if not RUNNING.acquire(blocking=False):
        return False
    def work():
        try:
            pipeline.run(only)
        finally:
            RUNNING.release()
    threading.Thread(target=work, daemon=True).start()
    return True


def refresh_samples():
    """Beispieldaten haben Termine rund um den nächsten Samstag. Liegt einer davon in der Vergangenheit
    (z. B. Server am Montag neu gestartet), werden die Beispiel-Einträge gelöscht und neu eingesammelt,
    damit Wochenende, Begleiter und Karte nie leer sind. Echte Quellen bleiben unberührt."""
    old = db.one("select count(*) n from items where source_id like 'bsp-%' and event_date is not null and event_date < date('now','localtime')")
    stale = db.one("select count(*) n from items where source_id like 'bsp-%' and (url like '%example.org%' or url is null "
                   "or source_id in (select id from sources where enabled=0))")
    if (old and old["n"]) or (stale and stale["n"]):  # alte Termine oder alte Platzhalter-Links -> neu einsammeln
        db.exec_("delete from items where source_id like 'bsp-%'")
        return True
    return False


@app.on_event("startup")
async def startup():
    agent.forecast()  # Wettervorhersage im Hintergrund vorladen
    threading.Thread(target=ai.selftest, daemon=True).start()
    if ai.LLM_KEY:
        sitesearch.start(ai.TRUSTED)  # Verzeichnis der geprüften Seiten im Hintergrund (alle 7 Tage neu)  # zeigt im Fenster, ob der KI-Schlüssel funktioniert
    db.init()
    privacy.cleanup()  # Speicherdauer einhalten
    pipeline.load_sources()
    if refresh_samples() or not db.one("select id from items limit 1"):
        start_run()

    async def scheduler():
        while True:
            await asyncio.sleep(INTERVAL * 60)
            refresh_samples()
            privacy.cleanup()
            start_run()
    asyncio.create_task(scheduler())


# ---------------- Seiten ----------------
@app.get("/")
def page_user(request: Request):
    """Startseite mit absoluter Adresse für die Link-Vorschau (Teams, WhatsApp …), auch hinter Cloudflare."""
    h = request.headers
    proto = (h.get("x-forwarded-proto") or request.url.scheme).split(",")[0]
    host = h.get("x-forwarded-host") or h.get("host") or "localhost:8000"
    with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as f:
        # ?v=Version: nach einem Update lädt der Browser garantiert die neuen Dateien statt alter aus dem Cache
        return HTMLResponse(f.read().replace("{{BASE}}", f"{proto}://{host}").replace("{{V}}", envfile.VERSION),
                            headers={"Cache-Control": "no-cache"})


@app.get("/admin")
def page_admin():
    return FileResponse(os.path.join(STATIC, "admin.html"))


# ---------------- Nutzer-API ----------------
def weekend_range(today=None):
    today = today or date.today()
    # kommendes Wochenende (am Sonntag: das nächste)
    sat = today + timedelta(days=(5 - today.weekday()) % 7)
    return sat, sat + timedelta(days=1)


def score(it, topics, region, today):
    """Empfehlung: Punkte für Thema, Region, Zeitnähe, Wochenende + Begründung."""
    s, why = 0, []
    if it["category"] in topics:
        s += 3; why.append(f"+3 dein Thema „{it['category']}“")
    if region and it.get("region") == region:
        s += 2; why.append(f"+2 in deiner Region {region}")
    ev = it.get("event_date")
    if ev:
        d = date.fromisoformat(ev[:10])
        if today <= d <= today + timedelta(days=7):
            s += 1; why.append("+1 in den nächsten 7 Tagen")
        sat, sun = weekend_range(today)
        if sat <= d <= sun:
            s += 1; why.append("+1 am Wochenende")
    s += (it.get("priority") or 3) / 10
    if not why:
        why.append("außerhalb deiner Themen, gegen die Filterblase")
    return round(s, 1), why


def live_items():
    today = date.today().isoformat()
    return [with_rank(db.item_out(r)) for r in db.rows(
        "select * from items where status='live' and (event_date is null or event_date>=?) order by coalesce(event_date,'9999'), id desc", (today,))]


# ---------------- Bilder (freie Lizenzen, siehe app/images.json und Seite „Bildnachweis“) ----------------
with open(os.path.join(os.path.dirname(__file__), "images.json"), encoding="utf-8") as _f:
    IMAGES = json.load(_f)


def img_info(x):
    return {"src": "/static/img/lib/" + x["file"].replace(".jpg", "-s.jpg"), "big": "/static/img/lib/" + x["file"],
            "caption": x["caption"], "credit": f"Foto: {x['author']} · {x['license']}", "source": x["source"],
            "region": x["region"], "mood": x["mood"], "tags": x["tags"], "license_url": x.get("license_url"), "author": x["author"],
            "license": x["license"], "title": x.get("title")}


def pick_image(it, used):
    """Passendes Foto: Schlagwörter im Text > gleiche Region; schon benutzte Bilder nur, wenn nichts anderes passt."""
    hay = " ".join(str(it.get(k) or "") for k in ("title", "summary", "location")).lower()
    best, bs = None, -99
    for x in IMAGES:
        if it.get("category") not in x.get("cats", [it.get("category")]):
            continue  # z. B. kein Waldfoto für eine Karrieremesse
        tag = sum(3 for t in x["tags"] if t in hay)
        same = x["region"] == it.get("region")
        if x["region"] and not same and not any(t in hay for t in x["tags"] if t.lower() == (it.get("location") or "").lower()):
            if not tag or x["region"] != it.get("region"):
                if x["region"]:
                    continue  # nie ein Ortsfoto aus einer anderen Gegend
        if not tag and not same:
            continue
        # schon gezeigte Bilder stark abwerten, damit nicht jede Karte gleich aussieht
        sc = tag + (2 if same else 0) - (6 if x["file"] in used else 0)
        if sc > bs:
            best, bs = x, sc
    if best:
        used.add(best["file"])
    return img_info(best) if best else None


def decorate(items, home):
    """Entfernung (Luftlinie vom Wohnort), Wetter am Termin und ein passendes Foto an jeden Eintrag hängen."""
    hx = (COORDS.get(home) or TOWN_COORDS.get(home)) if home else None
    used = set()
    for it in items:
        if "img" not in it:
            it["img"] = pick_image(it, used)
        it["km"] = agent.km(hx, (it.get("lat"), it.get("lon"))) if hx else None
        ev = (it.get("event_date") or "")[:10]
        w = agent.day_weather(it.get("region"), date.fromisoformat(ev)) if ev and it.get("region") in COORDS else None
        it["wx"] = {"icon": w["icon"], "tmax": w["tmax"], "text": w["text"], "rain": w["rain"]} if w else None
    return items


@app.get("/api/meta")
def meta():
    return {"topics": ai.TOPICS, "regions": REGIONS, "roles": ROLES, "coords": COORDS, "weekend": [d.isoformat() for d in weekend_range()],
            "places": [[p["name"], p["region"], p["lat"], p["lon"], p["art"]] for p in PLACES], "places_meta": PLACES_META}


@app.get("/api/feed")
def feed(topics: str = "", region: str = "", lang: str = ""):
    """Das Profil wird nur als Parameter geschickt und NICHT gespeichert."""
    tps = [t for t in topics.split(",") if t]
    today = date.today()
    items = live_items()
    for it in items:
        it["score"], it["why"] = score(it, tps, region, today)
    sat, sun = weekend_range(today)
    def on(it, a, b):
        return it.get("event_date") and a.isoformat() <= it["event_date"][:10] <= b.isoformat()
    for_you = sorted([i for i in items if i["category"] in tps], key=lambda i: -i["score"])[:9]
    near = [i for i in items if i.get("region") == region][:9]
    week = sorted([i for i in items if on(i, today, today + timedelta(days=7)) and (i.get("region") == region or i["category"] in tps)],
                  key=lambda i: i["event_date"])[:8]
    weekend = sorted([i for i in items if on(i, sat, sun)], key=lambda i: -i["score"])[:9]
    also = [i for i in items if i["category"] not in tps][:3]
    if for_you:
        ids = [i["id"] for i in for_you]
        db.exec_(f"update items set views=views+1 where id in ({','.join('?'*len(ids))})", ids)
    decorate(for_you + near + week + weekend + also, region)
    if lang == "en":
        en.items(for_you + near + week + weekend + also)
    return {"for_you": for_you, "near": near, "week": week, "weekend": weekend, "also": also,
            "counts": {"near_week": len([i for i in items if i.get("region") == region and on(i, today, today + timedelta(days=7))]),
                       "weekend": len([i for i in items if on(i, sat, sun)]),
                       "new": db.one("select count(*) n from items where status='live' and created>=datetime('now','localtime','-1 day')")["n"]}}


@app.get("/api/items")
def items(topic: str = "", region: str = "", q: str = "", home: str = "", lang: str = ""):
    out = live_items()
    if topic:
        out = [i for i in out if i["category"] == topic]
    if region:
        out = [i for i in out if agent.in_area(i, region)]
    if q:
        ql = q.lower()
        out = [i for i in out if ql in (i["title"] + " " + (i.get("summary") or "")).lower()]
    out = decorate(out, home or region)
    return en.items(out) if lang == "en" else out


@app.get("/api/items/by-ids")
def items_by_ids(ids: str = "", home: str = "", lang: str = ""):
    nums = [int(x) for x in ids.split(",") if x.isdigit()][:200]
    if not nums:
        return []
    out = decorate([db.item_out(r) for r in db.rows(f"select * from items where id in ({','.join('?'*len(nums))})", nums)], home)
    return en.items(out) if lang == "en" else out


def limit(request, bucket, n, window=600):
    """Missbrauchsschutz: zu viele Anfragen von derselben Verbindung -> 429. Nichts wird gespeichert."""
    if not privacy.rate_ok(privacy.client_ip(request), bucket, n, window):
        raise HTTPException(429, "Zu viele Anfragen in kurzer Zeit. Bitte warte ein paar Minuten.")


@app.post("/api/ask")
def ask(request: Request, body: dict = Body(...)):
    """KI-Begleiter: Frage -> kurze Antwort + Karten aus unseren Inhalten (+ Wetter, Alternativen, Folgefragen).
    Die Frage wird NICHT gespeichert (außer die Person gibt aktiv 👎-Feedback)."""
    q = (body.get("q") or "").strip()[:300]
    if not q:
        raise HTTPException(400, "Bitte eine Frage eingeben.")
    limit(request, "ask", 120)  # großzügig: ganze Gruppe im selben WLAN teilt sich eine IP
    home = body.get("home") if body.get("home") in COORDS else "Bamberg"
    page_region = body.get("region") if body.get("region") in COORDS else None
    hist = body.get("history") if isinstance(body.get("history"), list) else []
    curated = [c for c in load_curated() if c["slot"] in ("wissen", "region", "start")]
    lang = "en" if body.get("lang") == "en" else "de"
    town = body.get("town") if body.get("town") in TOWN_COORDS else None
    res = agent.respond(q, live_items(), curated, home=home, page_region=page_region, history=hist, lang=lang, town=town)
    res["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    decorate(res["items"] + res["alternatives"], town or home)
    # „Was passiert im Hintergrund?“ – jeder Schritt dieser Antwort, für Nutzer nachvollziehbar
    pool = live_items()
    nsrc = len({i.get("source_id") for i in pool})
    eng = res.get("engine") or ""
    steps = [f"Frage verstanden{(': ' + res['label']) if res.get('label') else ''}. Sie wird nicht gespeichert."]
    if res.get("web_sources"):
        steps.append("In unseren Einträgen stand nichts Passendes, darum wurde nur auf geprüften Seiten gesucht "
                     f"({'eigene Suche' if 'eigene Suche' in eng else 'Google-Suche über Gemini'}).")
        steps.append(f"{len(res['web_sources'])} Seite(n) als Quelle genutzt: " + ", ".join(w["domain"] for w in res["web_sources"]) + ".")
    else:
        steps.append(f"Gesucht in {len(pool)} aktuellen Einträgen aus {nsrc} geprüften Quellen (Behörden, Städte, Hochschulen, Tourismus).")
        if res["items"]:
            ranks = sorted({i.get("rank_label") for i in res["items"] if i.get("rank_label")})
            steps.append(f"{len(res['items'])} Treffer ausgewählt nach Datum, Ort, Interesse und Wetter. Absender: {', '.join(ranks)}.")
    if res.get("weather") or res.get("forecast"):
        steps.append("Wettervorhersage live von Open-Meteo (Deutscher Wetterdienst u. a.) abgerufen.")
    steps.append("Antwort formuliert von " + ("Gemini (KI) nur aus diesen Treffern." if "LLM" in eng or "Gemini" in eng or "gemini" in eng else "unseren Regeln (ohne KI)."))
    res["trace"] = steps
    if not res["found"]:  # ehrlich: nichts gefunden -> offizielle Seiten zeigen
        res["links"] = [{"title": c["title"], "link": c["link"]} for c in curated if c.get("link")][:3]
    return en.ask_response(res) if lang == "en" else res


@app.post("/api/ask/feedback")
def ask_feedback(request: Request, body: dict = Body(...)):
    """👍/👎 zu einer KI-Antwort. Nur bei 👎 landet die Frage anonym in den Meldungen der Redaktion."""
    vote = body.get("vote")
    if vote not in ("up", "down"):
        raise HTTPException(400, "Ungültig.")
    limit(request, "feedback", 20)
    if vote == "down":
        q = (body.get("q") or "").strip()[:200]
        note = (body.get("note") or "").strip()[:200]
        db.exec_("insert into reports(item_id, reason) values(0, ?)", (f"KI-Antwort 👎 · Frage: „{q}“" + (f" · Hinweis: {note}" if note else ""),))
    ai.USAGE["up" if vote == "up" else "down"] = ai.USAGE.get("up" if vote == "up" else "down", 0) + 1
    return {"ok": True}


@app.post("/api/items/{iid}/click")
def click(iid: int):
    db.exec_("update items set clicks=clicks+1 where id=?", (iid,))
    return {"ok": True}


@app.post("/api/items/{iid}/save")
def save_count(iid: int, body: dict = Body(default={})):
    db.exec_("update items set saves=max(0, saves+?) where id=?", (1 if body.get("on", True) else -1, iid))
    return {"ok": True}


@app.post("/api/report")
def report(request: Request, body: dict = Body(...)):
    limit(request, "report", 10)
    iid = int(body.get("item_id") or 0)
    reason = (body.get("reason") or "").strip()[:300]
    if not db.one("select id from items where id=?", (iid,)) or not reason:
        raise HTTPException(400, "Bitte einen Grund angeben.")
    db.exec_("insert into reports(item_id, reason) values(?,?)", (iid, reason))
    return {"ok": True}


@app.post("/api/partner")
def partner(request: Request, body: dict = Body(...)):
    """Unternehmen/Einrichtung schlägt sich als Quelle vor. Landet bei der Redaktion (Meldungen), nichts geht automatisch live."""
    limit(request, "partner", 5)
    org = (body.get("org") or "").strip()[:120]
    site = (body.get("site") or "").strip()[:200]
    feed = (body.get("feed") or "").strip()[:200]
    what = (body.get("what") or "").strip()[:300]
    if not org or not re.match(r"https?://", site):
        raise HTTPException(400, "Bitte Name und Website (mit https://) angeben.")
    db.exec_("insert into reports(item_id, reason) values(?,?)", (None, f"Partner-Anfrage: {org} · {site} · Feed: {feed or '–'} · {what}"))
    return {"ok": True}


ALPH = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


@app.post("/api/sync")
def sync_create(request: Request, body: dict = Body(...)):
    limit(request, "sync", 10)
    """Speichert NUR Interessen (keine ID, keine IP, keine E-Mail)."""
    prof = {k: body.get(k) for k in ("role", "topics", "region", "saved")}
    code = "".join(secrets.choice(ALPH) for _ in range(4)) + "-" + "".join(secrets.choice(ALPH) for _ in range(4))
    db.exec_("insert into sync_codes(code, profile) values(?,?)", (code, json.dumps(prof, ensure_ascii=False)))
    return {"code": code}


@app.get("/api/sync/{code}")
def sync_get(code: str, request: Request):
    limit(request, "sync-get", 20)  # erschwert das Durchprobieren von Codes
    r = db.one("select profile from sync_codes where code=? and created >= datetime('now','localtime','-30 days')", (code.upper(),))
    if not r:
        raise HTTPException(404, "Diesen Sync-Code gibt es nicht (mehr). Codes gelten 30 Tage.")
    return json.loads(r["profile"])


# ---------------- Redaktion ----------------
@app.get("/api/images")
def images():
    return [img_info(x) for x in IMAGES]


@app.get("/api/today")
def today_weather(lang: str = ""):
    """Wetter heute für alle 9 Regionen (für Karte und Hero)."""
    t = date.today()
    out = {}
    for r in COORDS:
        w = agent.day_weather(r, t)
        if w:
            out[r] = {"icon": w["icon"], "tmax": w["tmax"], "text": w["text"], "rain": w["rain"]}
    return en.weather(out) if lang == "en" else out


@app.get("/api/info")
def info():
    """Datenstand: wann zuletzt eingesammelt wurde, je Quelle."""
    run = db.one("select finished from runs where finished is not null order by id desc limit 1")
    srcs = db.rows("select id, name, method, url, last_run, last_status, total from sources where enabled=1 order by name")
    return {"last_run": run["finished"] if run else None, "interval_min": INTERVAL,
            "sources": [{"name": x["name"], "method": x["method"], "url": x["url"] if str(x["url"]).startswith("http") else None,
                         "site": site_of(src_conf().get(x["id"]) or {}, x["url"] if str(x["url"]).startswith("http") else None),
                         "last_run": x["last_run"], "ok": x["last_status"] == "ok", "items": x["total"]} for x in srcs],
            "trusted": {k: v for k, v in ai.TRUSTED.items() if not k.startswith("_")}}


# ---------------- Einfacher Login: Name + 6-stellige PIN (ohne E-Mail) ----------------
import hashlib as _hl


def _pin_hash(pin, salt):
    return _hl.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 200_000).hex()


def _check_name_pin(body):
    name = (body.get("name") or "").strip().lower()
    pin = (body.get("pin") or "").strip()
    if not re.fullmatch(r"[a-z0-9_.-]{3,30}", name):
        raise HTTPException(400, "Name: 3–30 Zeichen, nur Buchstaben, Zahlen, Punkt, Minus, Unterstrich.")
    if not re.fullmatch(r"\d{6}", pin):
        raise HTTPException(400, "Die PIN muss genau 6 Ziffern haben.")
    return name, pin


@app.post("/api/account/save")
def account_save(request: Request, body: dict = Body(...)):
    """Speichert NUR Profil (Rolle, Themen, Region, Merkliste, Tagespläne) unter Name + PIN. Keine E-Mail, keine IP."""
    limit(request, "account-save", 10)
    name, pin = _check_name_pin(body)
    prof = body.get("profile") or {}
    prof = {k: prof.get(k) for k in ("nick", "role", "topics", "region", "saved", "plans")}
    row = db.one("select salt, pin_hash from accounts where name=?", (name,))
    if row:
        if _pin_hash(pin, row["salt"]) != row["pin_hash"]:
            raise HTTPException(409, "Diesen Namen gibt es schon. Bitte anderen Namen wählen oder richtige PIN eingeben.")
        db.exec_("update accounts set profile=?, updated=datetime('now','localtime') where name=?", (json.dumps(prof, ensure_ascii=False), name))
    else:
        salt = secrets.token_hex(16)
        db.exec_("insert into accounts(name, salt, pin_hash, profile) values(?,?,?,?)", (name, salt, _pin_hash(pin, salt), json.dumps(prof, ensure_ascii=False)))
    return {"ok": True, "name": name}


@app.post("/api/account/login")
def account_login(request: Request, body: dict = Body(...)):
    limit(request, "account-login", 8)  # schützt vor Durchprobieren der PIN
    name, pin = _check_name_pin(body)
    row = db.one("select salt, pin_hash, profile from accounts where name=?", (name,))
    if not row or _pin_hash(pin, row["salt"]) != row["pin_hash"]:
        raise HTTPException(401, "Name oder PIN stimmt nicht.")
    return {"ok": True, "name": name, "profile": json.loads(row["profile"] or "{}")}


@app.post("/api/account/delete")
def account_delete(request: Request, body: dict = Body(...)):
    limit(request, "account-login", 8)
    name, pin = _check_name_pin(body)
    row = db.one("select salt, pin_hash from accounts where name=?", (name,))
    if not row or _pin_hash(pin, row["salt"]) != row["pin_hash"]:
        raise HTTPException(401, "Name oder PIN stimmt nicht.")
    db.exec_("delete from accounts where name=?", (name,))
    return {"ok": True}


# ---------------- Datenschutz: Region-Vorschlag + anonyme Statistik ----------------
@app.get("/api/region-guess")
def region_guess(request: Request):
    """Schätzt die Region EINMAL aus der Verbindung (lokale GeoIP-Datei). Die IP wird nicht gespeichert,
    nicht geloggt und nicht weitergegeben. Ohne GeoIP-Datei: keine Schätzung."""
    reg, how = privacy.region_from_ip(privacy.client_ip(request))
    return {"region": reg, "how": how, "stored": False}


def _mask_ip(ip):
    if ":" in ip:
        parts = ip.split(":")
        return ":".join(parts[:2]) + ":…" if len(parts) > 2 else ip
    p = ip.split(".")
    return f"{p[0]}.{p[1]}.x.x" if len(p) == 4 else "unbekannt"


@app.get("/api/privacy/check")
def privacy_check(request: Request):
    """Transparenz-Check für die Datenschutz-Seite: was der Server JETZT sieht und was er überhaupt speichern KANN.
    Die IP wird nur maskiert angezeigt und nirgends abgelegt."""
    labels = {"items": "Inhalte aus den Quellen", "sources": "Liste der Quellen", "runs": "Protokoll der Abrufe",
              "stats": "Anonyme Statistik (nur mit Einwilligung)", "accounts": "Freiwillige Konten (Name + PIN)",
              "reports": "Hinweise der Nutzer (nur bei 👎 oder Formular)", "sync_codes": "Sync-Codes (freiwillig, gelten 30 Tage)"}
    tables = []
    for t, label in labels.items():
        try:
            cols = [r["name"] for r in db.rows(f"pragma table_info({t})")]
            n = db.one(f"select count(*) c from {t}")["c"]
        except Exception:
            continue
        tables.append({"table": t, "label": label, "columns": cols, "rows": n})
    has_ip = any(re.search(r"(^|_)(ip|ip_addr|ipaddress|user_agent|cookie)($|_)", c, re.I) for t in tables for c in t["columns"])
    stats_today = [dict(r) for r in db.rows("select key, n from stats where day=date('now','localtime') order by n desc limit 8")]
    return {"ip_seen": _mask_ip(privacy.client_ip(request)), "ip_stored": False, "access_log": False,
            "retention": [r[2] for r in privacy.RETENTION],
            "tables": tables, "any_ip_column": has_ip, "stats_today": stats_today}


STAT_KEYS = re.compile(r"^(view:(start|mein|datenschutz|region:[A-Za-z]{2,20})|ask|plan|save|followup|feedback)$")


@app.post("/api/stats")
def stats(request: Request, body: dict = Body(...)):
    """Nur nach Einwilligung (Browser schickt sonst nichts). Gezählt wird NUR „Tag + Ereignis + Anzahl“:
    keine IP, keine ID, keine Uhrzeit, kein Profil."""
    key = str(body.get("key") or "")
    if not STAT_KEYS.match(key):
        raise HTTPException(400, "Unbekanntes Ereignis.")
    if not privacy.rate_ok(privacy.client_ip(request), "stats", 120):
        return {"ok": False}
    db.exec_("insert into stats(day, key, n) values(date('now','localtime'), ?, 1) on conflict(day, key) do update set n = n + 1", (key,))
    return {"ok": True}


def auth(token):
    if token not in TOKENS:
        raise HTTPException(401, "Bitte anmelden.")


@app.post("/api/admin/login")
def admin_login(request: Request, body: dict = Body(...)):
    limit(request, "admin-login", 10)  # Schutz gegen Durchprobieren von Passwörtern
    if ADMIN_PASS in ("demo1234", "") and privacy.is_public(privacy.client_ip(request)):
        # Standard-Passwort steht in der Anleitung -> über den Cloudflare-Link gesperrt
        raise HTTPException(403, "Das Standard-Passwort gilt nur am eigenen Rechner. Bitte ADMIN_PASSWORD in der Datei .env ändern und neu starten.")
    if body.get("user") != ADMIN_USER or not secrets.compare_digest(str(body.get("password") or ""), ADMIN_PASS):
        raise HTTPException(401, "E-Mail oder Passwort stimmt nicht.")
    t = secrets.token_urlsafe(24)
    TOKENS.add(t)
    return {"token": t}


@app.get("/api/admin/overview")
def admin_overview(x_token: str = Header("")):
    auth(x_token)
    srcs = db.rows("select * from sources order by name")
    run = db.one("select * from runs where finished is not null order by id desc limit 1")
    cats = db.rows("select category, count(*) n from items where status='live' group by category order by n desc")
    tok = db.one("select coalesce(sum(tokens_in),0) ti, coalesce(sum(tokens_out),0) tou, count(*) runs from runs where started>=date('now','start of month')")
    processed = db.one("select count(*) n from items where created>=date('now','start of month')")["n"]
    avg = db.one("select avg(confidence) a from items where status='live'")["a"] or 0
    words = {}
    for r in db.rows("select title, summary from items where status='live' and created>=datetime('now','localtime','-7 day')"):
        for w in set(re.findall(r"[a-zäöüß]{6,}", (r["title"] + " " + (r["summary"] or "")).lower())) - ai.STOP:
            words[w] = words.get(w, 0) + 1
    return {
        "sources_active": len([s for s in srcs if s["enabled"] and s["last_status"] != "err"]), "sources_total": len([s for s in srcs if s["enabled"]]),
        "new_24h": db.one("select count(*) n from items where created>=datetime('now','localtime','-1 day')")["n"],
        "queue": db.one("select count(*) n from items where status='review'")["n"],
        "reports": db.one("select count(*) n from reports where status='offen'")["n"],
        "avg_conf": round(avg, 2), "last_run": run, "running": RUNNING.locked(), "interval": INTERVAL,
        "categories": cats, "engine": ai.engine_name() + (f" · Status: {ai.LAST_STATUS['text']}" if ai.LLM_KEY else ""),
        "cost": {"processed": processed, "tokens_in": tok["ti"], "tokens_out": tok["tou"],
                 "usd": round(tok["ti"] / 1e6 * ai.PRICE_IN + tok["tou"] / 1e6 * ai.PRICE_OUT, 4),
                 "est_usd": round(processed * (1500 * ai.PRICE_IN + 300 * ai.PRICE_OUT) / 1e6, 2),
                 "price_in": ai.PRICE_IN, "price_out": ai.PRICE_OUT},
        "stats": db.rows("select key, sum(n) n from stats where day >= date('now','localtime','-6 day') group by key order by n desc"),
        "stats_days": db.rows("select day, sum(n) n from stats where day >= date('now','localtime','-6 day') group by day order by day"),
        "geoip": bool(privacy._reader),
        "chat": {"calls": ai.USAGE["chat_calls"], "tokens_in": ai.USAGE["tokens_in"], "tokens_out": ai.USAGE["tokens_out"],
                 "usd": round(ai.USAGE["tokens_in"] / 1e6 * ai.PRICE_IN + ai.USAGE["tokens_out"] / 1e6 * ai.PRICE_OUT, 4),
                 "up": ai.USAGE.get("up", 0), "down": ai.USAGE.get("down", 0)},
        "trends": sorted(([w, n] for w, n in words.items() if n > 1), key=lambda x: -x[1])[:12],
    }


@app.get("/api/admin/sources")
def admin_sources(x_token: str = Header("")):
    auth(x_token)
    return db.rows("""select s.*, (select count(*) from items i where i.source_id=s.id and i.status='live') live,
                      (select coalesce(sum(views),0) from items i where i.source_id=s.id) views,
                      (select coalesce(sum(clicks),0) from items i where i.source_id=s.id) clicks,
                      (select coalesce(sum(saves),0) from items i where i.source_id=s.id) saves
                      from sources s order by s.enabled desc, s.name""")


@app.post("/api/admin/run")
def admin_run(body: dict = Body(default={}), x_token: str = Header("")):
    auth(x_token)
    if not start_run(body.get("source")):
        raise HTTPException(409, "Es läuft bereits ein Durchlauf.")
    return {"ok": True}


@app.get("/api/admin/runs")
def admin_runs(x_token: str = Header("")):
    auth(x_token)
    return {"running": RUNNING.locked(), "runs": db.rows("select * from runs order by id desc limit 15")}


@app.get("/api/admin/queue")
def admin_queue(x_token: str = Header("")):
    auth(x_token)
    return [db.item_out(r) for r in db.rows("select * from items where status='review' order by id desc")]


@app.post("/api/admin/items/{iid}/{action}")
def admin_decide(iid: int, action: str, x_token: str = Header("")):
    auth(x_token)
    if action not in ("approve", "reject"):
        raise HTTPException(400, "Unbekannte Aktion")
    db.exec_("update items set status=? where id=?", ("live" if action == "approve" else "rejected", iid))
    return {"ok": True}


@app.post("/api/admin/process")
def admin_process(body: dict = Body(...), x_token: str = Header("")):
    """KI-Labor: beliebigen Text verarbeiten und prüfen (ohne zu speichern)."""
    auth(x_token)
    text = (body.get("text") or "").strip()
    if len(text) < 20:
        raise HTTPException(400, "Bitte mindestens einen Satz eingeben.")
    res, tin, tout = ai.process(text)
    res["checks"] = pipeline.checks(res)
    res["coords"] = COORDS.get(OF_TOWNS.get(res.get("location") or ""))
    res["prompt"] = ai.prompt(text)
    res["tokens"] = [tin, tout]
    return res


@app.post("/api/admin/publish")
def admin_publish(body: dict = Body(...), x_token: str = Header("")):
    auth(x_token)
    res, text = body.get("result") or {}, body.get("text") or ""
    flags = pipeline.checks(res)
    src = {"id": "ki-labor", "name": "KI-Labor (manuell)", "method": "llm"}
    iid, status = pipeline.save_item({"title": res.get("title"), "text": text, "url": None}, res, src, flags)
    return {"id": iid, "status": status}


@app.get("/api/admin/reports")
def admin_reports(x_token: str = Header("")):
    auth(x_token)
    return db.rows("select r.*, i.title from reports r left join items i on i.id=r.item_id order by r.id desc limit 100")


@app.post("/api/admin/reports/{rid}/done")
def admin_report_done(rid: int, x_token: str = Header("")):
    auth(x_token)
    db.exec_("update reports set status='erledigt' where id=?", (rid,))
    return {"ok": True}


# ---------------- Kuratierte Inhalte (blau, „CMS“) ----------------
CURATED = os.path.join(os.path.dirname(__file__), "curated.json")


def load_curated():
    with open(CURATED, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/curated")
def curated(slot: str = "", region: str = ""):
    out = load_curated()
    if slot:
        out = [c for c in out if c.get("slot") == slot]
    if region:
        out = [c for c in out if c.get("region") == region]
    return out


@app.post("/api/admin/curated")
def admin_curated_save(body: dict = Body(...), x_token: str = Header("")):
    """Team Oberfranken bearbeitet einen kuratierten Block (100 % Kontrolle)."""
    auth(x_token)
    items = load_curated()
    cid = body.get("id")
    for c in items:
        if c["id"] == cid:
            c["title"] = (body.get("title") or c["title"])[:120]
            c["text"] = (body.get("text") or c["text"])[:1200]
            break
    else:
        raise HTTPException(404, "Block nicht gefunden.")
    with open(CURATED, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return {"ok": True}


# ---------------- Wetter (Open-Meteo, kostenlos, ohne Schlüssel) ----------------
_weather = {}
WCODE = {0: "sonnig", 1: "überwiegend sonnig", 2: "teils bewölkt", 3: "bewölkt", 45: "Nebel", 48: "Nebel",
         51: "Nieselregen", 53: "Nieselregen", 55: "Nieselregen", 61: "leichter Regen", 63: "Regen", 65: "starker Regen",
         71: "Schnee", 73: "Schnee", 75: "starker Schnee", 80: "Regenschauer", 81: "Regenschauer", 82: "Regenschauer", 95: "Gewitter"}


@app.get("/api/weather")
def weather(region: str = "Bamberg", town: str = "", lang: str = ""):
    w = _weather_de(region, town)
    return en.weather(dict(w)) if lang == "en" and isinstance(w, dict) else w


def _weather_de(region="Bamberg", town=""):
    import time
    import httpx
    if town in TOWN_COORDS:  # genauer Ort (amtliche Mittelpunktkoordinaten)
        region = town
    lat, lon = TOWN_COORDS.get(region) or COORDS.get(region, COORDS["Bamberg"])
    hit = _weather.get(region)
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    res = {"region": region, "temp": None, "text": None, "rain": False}
    try:
        r = httpx.get("https://api.open-meteo.com/v1/forecast",
                      params={"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code", "timezone": "Europe/Berlin"}, timeout=4)
        cur = r.json()["current"]
        code = int(cur["weather_code"])
        res.update(temp=round(cur["temperature_2m"]), text=WCODE.get(code, "wechselhaft"), rain=code >= 51)
    except Exception:
        pass
    if res["temp"] is None:  # Ersatz: Tageswerte aus der (zwischengespeicherten) Vorhersage
        reg = region if region in COORDS else OF_TOWNS.get(region, "Bamberg")
        w = agent.day_weather(reg, date.today(), region if region in TOWN_COORDS and region not in COORDS else None)
        if w:
            res.update(temp=w["tmax"], text=w["text"], rain=w["rain"])
            return res
    _weather[region] = (time.time() if res["temp"] is not None else time.time() - 1680, res)  # Fehler nur 2 min merken
    return res


# ---------------- Begleiter: persönlicher Tagesplan  ----------------
INTERESTS = {
    "Kultur & Stadt": (["Kultur", "Events"], ["museum", "burg", "führung", "altstadt", "konzert", "ausstellung", "schloss"]),
    "Natur & Ruhe": (["Tourismus"], ["wander", "natur", "see", "wald", "felsen", "staffelberg", "rundweg"]),
    "Familienzeit": (["Events"], ["familie", "kinder", "mitmachen", "ferien"]),
    "Aktiv & Rad": (["Tourismus"], ["rad", "bike", "tour", "mountainbike"]),
}


@app.get("/api/plan")
def plan(interests: str = "", region: str = "", half: bool = False, transit: bool = True, lang: str = ""):
    p = _plan(interests, region, half, transit)
    return en.plan(p) if lang == "en" else p


def _plan(interests, region, half, transit):
    """Erstellt einen Tagesplan NUR aus vorhandenen Inhalten. Keine Speicherung der Auswahl."""
    picks = [i for i in interests.split(",") if i in INTERESTS] or ["Kultur & Stadt"]
    today = date.today()
    sat, sun = weekend_range(today)
    cats = set(c for p in picks for c in INTERESTS[p][0])
    kws = [k for p in picks for k in INTERESTS[p][1]]
    scored = []
    for it in live_items():
        ev = it.get("event_date")
        if ev and date.fromisoformat(ev[:10]) > today + timedelta(days=14):
            continue
        hay = (it["title"] + " " + (it.get("summary") or "")).lower()
        s = (2 if it["category"] in cats else 0) + sum(2 for k in kws if k in hay)
        if region and it.get("region") == region:
            s += 3
        if ev and sat.isoformat() <= ev[:10] <= sun.isoformat():
            s += 1
        if s > 0:
            scored.append((s, it))
    scored.sort(key=lambda x: -x[0])
    # Tag + Gegend mit den besten Treffern wählen (ein Ausflug = ein Tag, eine Gegend)
    groups = {}
    for s, it in scored:
        key = (it.get("region"), (it.get("event_date") or "")[:10])
        groups.setdefault(key, []).append((s, it))
    def gscore(kv):
        top = kv[1][:3]
        return sum(s for s, _ in top) + 2 * len(top)
    chosen = []
    if groups:
        best_key, best = max(groups.items(), key=gscore)
        chosen = [it for _, it in best][: (2 if half else 3)]
        if len(chosen) < (2 if half else 3):  # mit undatierten Einträgen derselben Gegend auffüllen
            chosen += [it for _, it in groups.get((best_key[0], ""), []) if it not in chosen][: (2 if half else 3) - len(chosen)]
    chosen.sort(key=lambda i: (i.get("event_date") or "9999", any(w in (i["title"] + " " + (i.get("summary") or "")).lower() for w in ("abend", "sonnenuntergang", "19 uhr", "18 uhr"))))
    if not chosen:
        return {"title": "Noch nichts Passendes", "intro": "Für diese Auswahl gibt es in den nächsten zwei Wochen keine Einträge. Probier ein anderes Interesse oder eine andere Region.", "steps": [], "checklist": [], "picks": picks}
    place = chosen[0].get("location") or chosen[0].get("region") or "Oberfranken"
    area = chosen[0].get("region") or place
    steps = [{"t": "01 · Ankommen & entdecken", "text": chosen[0]["summary"], "item": chosen[0]}]
    if half:
        if len(chosen) > 1:
            steps.append({"t": "02 · Zum Abschluss", "text": chosen[1]["summary"], "item": chosen[1]})
    else:
        steps.append({"t": "02 · Pause & genießen", "text": f"Plane eine längere Mittagspause in {place} ein. Ein Café oder Gasthaus kannst du nach deinen Vorlieben auswählen.", "item": None})
        if len(chosen) > 1:
            steps.append({"t": "03 · Den Tag ausklingen lassen", "text": chosen[-1]["summary"], "item": chosen[-1]})
        else:
            steps.append({"t": "03 · Den Tag ausklingen lassen", "text": f"Lass den Tag mit einem Spaziergang durch {place} ausklingen. Tipps dafür findest du bei den offiziellen Infos der Region.", "item": None})
    intro = f"Für deinen {'halben' if half else 'ganzen'} Tag passt {area}: " + " und ".join(i["title"] for i in chosen[:2]) + "."
    llm_intro = ai.answer(f"Schreibe zwei freundliche Sätze, warum dieser Tagesplan zu den Interessen {', '.join(picks)} passt.", chosen) if ai.LLM_KEY else None
    w = weather(area if area in COORDS else "Bamberg")
    checklist = []
    checklist.append(f"Wetter in {w['region']}: {w['temp']} °C, {w['text']}." if w.get("temp") is not None else "Wetter vorab prüfen (im Prototyp gerade nicht abrufbar).")
    for it in chosen:
        if it.get("event_date"):
            checklist.append(f"Termin „{it['title']}“: {date.fromisoformat(it['event_date'][:10]).strftime('%d.%m.')} – Uhrzeit und Anmeldung beim Anbieter prüfen.")
    checklist.append("Öffnungszeiten und Eintritt beim Anbieter prüfen, die Links führen zur Originalquelle.")
    if transit:
        checklist.append(f"Anreise mit Bus und Bahn: Verbindung nach {place} und die Rückfahrt in der Fahrplanauskunft prüfen.")
    return {"title": f"Für dich: {' & '.join(picks)}", "meta": [f"Zeitbudget · {'halber Tag' if half else 'ein ganzer Tag'}", f"Anreise · {'Bus und Bahn' if transit else 'flexibel'}"],
            "intro": llm_intro or intro, "steps": steps, "checklist": checklist, "picks": picks, "engine": ai.engine_name()}
