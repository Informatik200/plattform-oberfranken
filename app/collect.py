"""Datenerfassung: RSS, schema.org (JSON-LD), API, Webcrawler, Open Data.

Jede Methode liefert Einträge im EINHEITLICHEN FORMAT:
  title, text, url, source, published, event_date, location
"""
import json
import os
import re
import time
import urllib.robotparser
from datetime import datetime
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

BASE = os.path.dirname(__file__)
UA = "BuehneOberfranken-Prototyp/1.0 (Studienprojekt Hochschule Coburg)"
OFFLINE = os.environ.get("OFFLINE", "0") == "1"


class SourceError(Exception):
    pass


# ---------- Laden (Datei oder Web, mit robots.txt-Prüfung) ----------
_robots = {}


def allowed_by_robots(url):
    """§ 44b UrhG: maschinenlesbaren Nutzungsvorbehalt (robots.txt) respektieren."""
    p = urlparse(url)
    root = f"{p.scheme}://{p.netloc}"
    if root not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = httpx.get(root + "/robots.txt", headers={"User-Agent": UA}, timeout=10, follow_redirects=True)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _robots[root] = rp
    return _robots[root].can_fetch(UA, url)


def _fill_dates(text):
    """Beispieldateien: {{SAT+n}} = Datum ab dem kommenden Samstag, {{PUB-n}} = RSS-Datum vor n Tagen."""
    from datetime import date, timedelta
    from email.utils import format_datetime
    today = date.today()
    sat = today + timedelta(days=(5 - today.weekday()) % 7)

    def d(m):
        return (sat + timedelta(days=int(m.group(1) or 0))).isoformat()

    def pub(m):
        dt = datetime.combine(today - timedelta(days=int(m.group(1))), datetime.min.time()).replace(hour=9)
        return format_datetime(dt.astimezone())
    text = re.sub(r"\{\{SAT([+-]\d+)?\}\}", d, text)
    return re.sub(r"\{\{PUB-(\d+)\}\}", pub, text)


def load(url):
    if not url.startswith("http"):
        with open(os.path.join(BASE, url), encoding="utf-8") as f:
            return _fill_dates(f.read())
    if OFFLINE:
        raise SourceError("Offline-Modus: Webquellen deaktiviert")
    if not allowed_by_robots(url):
        raise SourceError("robots.txt verbietet den Abruf")
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
    except Exception as e:
        raise SourceError(f"Nicht erreichbar: {type(e).__name__}")
    if r.status_code != 200:
        raise SourceError(f"HTTP {r.status_code}")
    return r.text


def norm_town(name):
    """„Schönbrunn i. Steigerwald“ -> „Schönbrunn im Steigerwald“ (amtliche Abkürzungen ausschreiben)."""
    n = re.sub(r"\bi\.\s*OFr\.?", "in Oberfranken", name or "")
    n = re.sub(r"\ba\.\s*d\.\s*", "an der ", n)
    n = re.sub(r"\bi\.\s*", "im ", n)
    n = re.sub(r"\ba\.\s*", "am ", n)
    n = re.sub(r"\bb\.\s*", "bei ", n)
    return re.sub(r"\s+", " ", n).strip(" ,.")


def clean(html):
    return re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ")).strip()


def entry(**kw):
    keys = ("title", "text", "url", "source", "published", "event_date", "location")
    return {k: kw.get(k) for k in keys}


# ---------- Methoden ----------
def _rss_date(v):
    """RSS-Datum (RFC 822 oder ISO) -> JJJJ-MM-TT."""
    if not v:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(v).date().isoformat()
    except Exception:
        m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", v)
        return m.group(0) if m else None


def from_rss(src):
    """RSS/Atom. Optionen in sources.json: limit, max_age_days (alte Meldungen weglassen),
    event_date_from = "published" (Termin-Feeds, bei denen das Datum der Termin ist). Kennt auch ev:startdate."""
    from datetime import date, timedelta
    from urllib.parse import urljoin
    feed = feedparser.parse(load(src["url"]))
    if feed.bozo and not feed.entries:
        raise SourceError("Feed ist kein gültiges RSS/Atom")
    base = feed.feed.get("link") or src["url"]
    max_age = int(src.get("max_age_days") or 0)
    out = []
    for e in feed.entries[: int(src.get("limit") or 30)]:
        pub = time.strftime("%Y-%m-%d", e.published_parsed) if e.get("published_parsed") else None
        if max_age and pub and date.fromisoformat(pub) < date.today() - timedelta(days=max_age):
            continue
        ev = _rss_date(e.get("ev_startdate"))
        if not ev and src.get("event_date_from") == "published":
            ev = pub
        venue = clean(e.get("ev_location") or "")
        text = clean(e.get("summary", ""))
        if venue:
            text = (text + f" Ort: {venue}.").strip()
        if e.get("ev_type"):
            text = (text + f" Art: {clean(e.get('ev_type'))}.").strip()
        out.append(entry(title=clean(e.get("title")), text=text, url=urljoin(base, e.get("link") or ""),
                         source=src["name"], published=pub, event_date=ev))
    return out


def _schema_events(objs, src, page_url=None):
    out = []
    stack = list(objs if isinstance(objs, list) else [objs])
    while stack:
        o = stack.pop(0)
        if isinstance(o, list):
            stack.extend(o)
            continue
        if not isinstance(o, dict):
            continue
        if "@graph" in o:
            stack.extend(o["@graph"])
        t = o.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(x and "Event" in x for x in types):
            loc = o.get("location") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            addr = loc.get("address") or {}
            city = addr.get("addressLocality") if isinstance(addr, dict) else None
            out.append(entry(title=o.get("name"), text=clean(o.get("description", "")),
                             url=o.get("url") or page_url, source=src["name"],
                             event_date=(o.get("startDate") or "")[:10] or None,
                             location=city or loc.get("name")))
    return out


def from_jsonld(src):
    soup = BeautifulSoup(load(src["url"]), "html.parser")
    objs = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            objs.append(json.loads(s.string or ""))
        except json.JSONDecodeError:
            continue
    page = src["url"] if src["url"].startswith("http") else None
    return _schema_events(objs, src, page)


def from_api(src):
    try:
        data = json.loads(load(src["url"]))
    except json.JSONDecodeError:
        raise SourceError("API-Antwort ist kein JSON")
    return _schema_events(data, src)


def from_crawler(src):
    soup = BeautifulSoup(load(src["url"]), "html.parser")
    for tag in soup(["nav", "footer", "header", "script", "style", "aside", "form"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body
    if not main:
        raise SourceError("Kein Inhalt gefunden")
    blocks = main.find_all(["article", "section"]) or [main]
    out = []
    for b in blocks[:15]:
        h = b.find(["h1", "h2", "h3"])
        text = " ".join(p.get_text(" ", strip=True) for p in b.find_all("p"))
        if not h or len(text) < 40:
            continue
        a = b.find("a", href=True)
        url = a["href"] if a and a["href"].startswith("http") else (src["url"] + "#" + re.sub(r"\W+", "-", h.get_text()).lower()[:40] if src["url"].startswith("http") else None)
        out.append(entry(title=h.get_text(" ", strip=True), text=text, url=url, source=src["name"]))
    if not out:
        raise SourceError("Seitenlayout geändert: kein Text gefunden")
    return out


def from_listing(src):
    """Übersichtsseite ohne Feed (z. B. Pressemitteilungen einer Behörde): Links nach Muster finden,
    die einzelnen Seiten höflich nacheinander abrufen (robots.txt, Pause) und Titel, Datum und Text auslesen."""
    from urllib.parse import urljoin
    html = load(src["url"])
    pattern = re.compile(src.get("pattern") or r".")
    links = []
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        u = urljoin(src["url"], a["href"])
        if pattern.search(u) and u not in links:
            links.append(u)
    if not links:
        raise SourceError("Keine passenden Links auf der Übersichtsseite (Layout geändert?)")
    from datetime import date
    url_date = re.compile(src["date_from_url"]) if src.get("date_from_url") else None
    if url_date and src.get("future_only"):  # nur kommende Termine, die nächsten zuerst
        def _d(u):
            m = url_date.search(u)
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""
        today = date.today().isoformat()
        links = sorted([u for u in links if _d(u) >= today], key=_d)
    known = src.get("known") or set()
    links = [u for u in links if u not in known]  # schon bekannte Seiten nicht erneut laden
    out = []
    for u in links[: int(src.get("limit") or 6)]:
        try:
            soup = BeautifulSoup(load(u), "html.parser")
        except SourceError:
            continue
        for tag in soup(["nav", "footer", "header", "script", "style", "aside", "form"]):
            tag.decompose()
        h = soup.find("h1")
        main = soup.find("main") or soup.find("article") or soup.body
        paras = [p.get_text(" ", strip=True) for p in (main.find_all("p") if main else [])]
        paras = [t for t in paras if len(t) > 60 and not re.search(r"JavaScript|Cookie|Einwilligung|Matomo", t)]
        if not h or (not paras and not url_date):
            continue
        if not paras:  # Terminseiten haben oft nur kurze Absätze
            paras = [t for t in (p.get_text(" ", strip=True) for p in (main.find_all(["p", "div"]) if main else [])) if 30 < len(t) < 600][:3]
        m = re.search(r"\b(\d{2})\.(\d{2})\.(20\d{2})\b", soup.get_text(" "))
        pub = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None
        ev = None
        if url_date and url_date.search(u):
            g = url_date.search(u)
            ev = f"{g.group(1)}-{g.group(2)}-{g.group(3)}"
        town = None
        if src.get("event_page"):  # Terminseite: „Datum:/Beginn: TT.MM.JJJJ“ und „Ortschaft: …“
            txt = re.sub(r"\s+", " ", soup.get_text(" "))
            dm = re.search(r"(?:Datum|Beginn)\s*:\s*(\d{1,2})\.(\d{1,2})\.(20\d{2})", txt) or re.search(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b", txt)
            if dm:
                ev = f"{dm.group(3)}-{int(dm.group(2)):02d}-{int(dm.group(1)):02d}"
            tm = re.search(r"Ortschaft\s*:\s*(.+?)\s+(?:Region|Preis|Termin|Veranstalter|Kontakt|Uhrzeit)\b", txt)
            if tm:
                town = norm_town(tm.group(1))
            if not paras:
                paras = [txt[txt.find(h.get_text(" ", strip=True)):][:600]]
        out.append(entry(title=h.get_text(" ", strip=True), text=" ".join(paras[:4])[:1500], url=u, source=src["name"],
                         published=None if ev else pub, event_date=ev, location=town))
        time.sleep(float(src.get("delay") or 1.5))
    if not out and links:
        raise SourceError("Seiten gefunden, aber kein Text lesbar")
    return out


def from_we2p(src):
    """Veranstaltungskalender der Tourismus-Plattform (Frankenwald, Hof, Fichtelgebirge …):
    Übersicht -> Detailseiten /detail/id=… -> strukturierte Daten (schema.org: Name, Beginn, Ende, Ort)."""
    from datetime import date, datetime as _dt
    from urllib.parse import urljoin
    html = load(src["url"])
    ids = list(dict.fromkeys(re.findall(r'href="(/detail/id=[0-9a-f]{24})"', html)))
    if not ids:
        raise SourceError("Keine Termine auf der Übersichtsseite (Layout geändert?)")
    today = date.today()
    known = src.get("known") or set()
    out = []
    for path in ids[: int(src.get("scan") or 40)]:
        if len(out) >= int(src.get("limit") or 15):
            break
        u = urljoin(src["url"], path)
        if u in known:  # schon bekannt: nicht erneut abrufen
            continue
        try:
            soup = BeautifulSoup(load(u), "html.parser")
        except SourceError:
            continue
        data = None
        for sc in soup.find_all("script", type="application/ld+json"):
            try:
                o = json.loads(sc.string or "")
            except Exception:
                continue
            if isinstance(o, dict) and o.get("startDate"):
                data = o
                break
        if not data or re.search(r"sperrung|umleitung|baustelle", data.get("name", ""), re.I):
            continue
        try:
            start = _dt.fromisoformat(data["startDate"].replace("Z", "+00:00")).date()
            end = _dt.fromisoformat((data.get("endDate") or data["startDate"]).replace("Z", "+00:00")).date()
        except Exception:
            continue
        if end < today or (start < today and (end - start).days > 21):  # vorbei oder Dauerangebot
            continue
        ev = max(start, today)
        loc = data.get("location") or {}
        loc = loc[0] if isinstance(loc, list) and loc else loc
        addr = (loc or {}).get("address") or {}
        town = norm_town(addr.get("addressLocality")) if isinstance(addr, dict) and addr.get("addressLocality") else None
        desc = clean(data.get("description") or "")
        if not desc:
            main = soup.find("main") or soup.body
            paras = [p.get_text(" ", strip=True) for p in (main.find_all("p") if main else [])]
            desc = " ".join(t for t in paras if len(t) > 50)[:800]
        text = (desc + (f" Ort: {town}." if town else "") + (f" Bis {end.strftime('%d.%m.%Y')}." if end > start else "")).strip()
        out.append(entry(title=clean(data.get("name")), text=text, url=data.get("url") or u, source=src["name"],
                         event_date=ev.isoformat(), location=town))
        time.sleep(float(src.get("delay") or 0.8))
    if not out and not any(urljoin(src["url"], pth) in known for pth in ids):
        raise SourceError("Keine kommenden Termine gefunden")
    return out


METHODS = {"we2p": from_we2p, "rss": from_rss, "jsonld": from_jsonld, "api": from_api, "crawler": from_crawler, "listing": from_listing}


def _config(sid):
    """Zusatz-Einstellungen einer Quelle (pattern, limit, delay) aus sources.json."""
    try:
        with open(os.path.join(BASE, "sources.json"), encoding="utf-8") as f:
            return next((x for x in json.load(f) if x.get("id") == sid), {})
    except Exception:
        return {}


def collect(src):
    src = dict(src)
    for k, v in _config(src.get("id")).items():
        src.setdefault(k, v)
    if src["method"] not in METHODS:
        raise SourceError(f"Unbekannte Methode {src['method']}")
    out = METHODS[src["method"]](src)
    for e in out:  # nennt der Termin selbst einen Ort, ist das die genaueste Angabe
        e["location_exact"] = e.get("location") in OF_TOWNS
    if src.get("location"):  # sonst: feste Stadt der Quelle als Rückfall (z. B. Veranstaltungskalender Kulmbach)
        for e in out:
            e["location"] = e.get("location") if e.get("location") in OF_TOWNS else src["location"]
    return out


# ---------- Open Data: Orte -> Koordinaten ----------
OF_TOWNS = {  # Ort -> Landkreis/Stadt in Oberfranken
    "Coburg": "Coburg", "Rödental": "Coburg", "Neustadt bei Coburg": "Coburg", "Bad Rodach": "Coburg",
    "Bamberg": "Bamberg", "Hallstadt": "Bamberg", "Scheßlitz": "Bamberg",
    "Bayreuth": "Bayreuth", "Pegnitz": "Bayreuth", "Pottenstein": "Bayreuth", "Bischofsgrün": "Bayreuth", "Fichtelberg": "Bayreuth", "Warmensteinach": "Bayreuth",
    "Hof": "Hof", "Naila": "Hof", "Münchberg": "Hof", "Rehau": "Hof", "Bad Steben": "Hof", "Helmbrechts": "Hof", "Schwarzenbach an der Saale": "Hof",
    "Selbitz": "Hof", "Lichtenberg": "Hof", "Geroldsgrün": "Hof", "Schauenstein": "Hof", "Berg": "Hof", "Köditz": "Hof", "Konradsreuth": "Hof", "Oberkotzau": "Hof", "Schwarzenbach am Wald": "Hof", "Issigau": "Hof", "Bad Steben-Lichtenberg": "Hof",
    "Kronach": "Kronach", "Ludwigsstadt": "Kronach", "Teuschnitz": "Kronach", "Wallenfels": "Kronach", "Steinwiesen": "Kronach",
    "Steinbach am Wald": "Kronach", "Tettau": "Kronach", "Pressig": "Kronach", "Mitwitz": "Kronach", "Küps": "Kronach", "Marktrodach": "Kronach",
    "Nordhalben": "Kronach", "Stockheim": "Kronach", "Weißenbrunn": "Kronach", "Wilhelmsthal": "Kronach", "Tschirn": "Kronach", "Reichenbach": "Kronach",
    "Kulmbach": "Kulmbach", "Thurnau": "Kulmbach", "Stadtsteinach": "Kulmbach", "Presseck": "Kulmbach", "Marktleugast": "Kulmbach", "Mainleus": "Kulmbach",
    "Neuenmarkt": "Kulmbach", "Kasendorf": "Kulmbach", "Untersteinach": "Kulmbach", "Wirsberg": "Kulmbach",
    "Bad Berneck im Fichtelgebirge": "Bayreuth", "Bad Berneck": "Bayreuth", "Gefrees": "Bayreuth", "Weidenberg": "Bayreuth", "Mehlmeisel": "Bayreuth", "Speichersdorf": "Bayreuth", "Creußen": "Bayreuth", "Hollfeld": "Bayreuth",
    "Lichtenfels": "Lichtenfels", "Bad Staffelstein": "Lichtenfels", "Burgkunstadt": "Lichtenfels",
    "Forchheim": "Forchheim", "Ebermannstadt": "Forchheim", "Gößweinstein": "Forchheim",
    "Wunsiedel": "Wunsiedel", "Marktredwitz": "Wunsiedel", "Kirchenlamitz": "Wunsiedel", "Selb": "Wunsiedel", "Bad Alexandersbad": "Wunsiedel",
    "Arzberg": "Wunsiedel", "Weißenstadt": "Wunsiedel", "Tröstau": "Wunsiedel", "Nagel": "Wunsiedel", "Hohenberg an der Eger": "Wunsiedel", "Schönwald": "Wunsiedel",
    "Thierstein": "Wunsiedel", "Thiersheim": "Wunsiedel", "Höchstädt im Fichtelgebirge": "Wunsiedel", "Marktleuthen": "Wunsiedel", "Röslau": "Wunsiedel", "Schirnding": "Wunsiedel",
    "Wunsiedel im Fichtelgebirge": "Wunsiedel",
}
OTHER_TOWNS = ["Würzburg", "Nürnberg", "Erlangen", "München", "Schweinfurt", "Regensburg", "Fürth", "Sonneberg", "Suhl", "Plauen"]
# Näherungswerte (Stadtzentren); online werden Orte über Nominatim/OpenStreetMap aufgelöst
COORDS = {"Coburg": (50.258, 10.964), "Bamberg": (49.899, 10.903), "Bayreuth": (49.946, 11.571), "Hof": (50.314, 11.913),
          "Kronach": (50.241, 11.328), "Kulmbach": (50.101, 11.447), "Lichtenfels": (50.145, 11.060),
          "Forchheim": (49.720, 11.058), "Wunsiedel": (50.039, 12.003)}
# Alle 214 Städte, Märkte und Gemeinden (amtlich, Destatis GV-ISys) -> Region + Koordinaten, siehe app/places.json
with open(os.path.join(BASE, "places.json"), encoding="utf-8") as _f:
    PLACES = json.load(_f)["orte"]
TOWN_COORDS = {}
_short = {}
for _p in PLACES:
    for _n in {_p["name"], _p["amtlich"]}:
        OF_TOWNS[_n] = _p["region"]
        TOWN_COORDS[_n] = (_p["lat"], _p["lon"])
    _s = re.split(r" (?:im|am|an der|bei|in) ", _p["name"])[0]
    if _s != _p["name"]:
        _short.setdefault(_s, []).append(_p)
for _s, _ps in _short.items():  # Kurzform („Bad Berneck“), nur wenn eindeutig
    if len(_ps) == 1 and _s not in OF_TOWNS and _s not in ("Neustadt",):
        OF_TOWNS[_s] = _ps[0]["region"]
        TOWN_COORDS[_s] = (_ps[0]["lat"], _ps[0]["lon"])
OF_TOWNS.setdefault("Weißenstadt", "Wunsiedel")
TOWN_COORDS.setdefault("Weißenstadt", TOWN_COORDS.get("Bad Weißenstadt"))
_geo_cache = {}
_last_geo = [0.0]


def geocode(place):
    """Ort -> (lat, lon). Erst lokale Tabelle, dann Nominatim (max. 1 Anfrage/Sekunde)."""
    if not place:
        return None
    region = OF_TOWNS.get(place)
    if TOWN_COORDS.get(place):  # amtliche Mittelpunktkoordinaten, kein Online-Abruf nötig
        return TOWN_COORDS[place]
    if region in COORDS and place == region:
        return COORDS[region]
    if place in _geo_cache:
        return _geo_cache[place]
    res = COORDS.get(region) if region else None
    if not OFFLINE:
        try:
            wait = 1.1 - (time.time() - _last_geo[0])
            if wait > 0:
                time.sleep(wait)
            _last_geo[0] = time.time()
            r = httpx.get("https://nominatim.openstreetmap.org/search",
                          params={"q": place + ", Bayern", "format": "json", "limit": 1},
                          headers={"User-Agent": UA}, timeout=10)
            js = r.json()
            if js:
                res = (round(float(js[0]["lat"]), 4), round(float(js[0]["lon"]), 4))
        except Exception:
            pass
    _geo_cache[place] = res
    return res
