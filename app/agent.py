"""KI-Begleiter für Oberfranken („Wie kann ich dir heute helfen?“).

Ablauf pro Frage:
1. Prüfen, ob die Frage zu Oberfranken passt (andere Regionen -> freundlich zurückleiten).
2. Tag erkennen (heute, morgen, Samstag, Wochenende, 17.10.) und Wettervorhersage dafür holen.
3. Passende Einträge aus der eigenen Datenbank suchen (RAG). Bei Regen + Draußen-Frage: Alternativen für drinnen.
4. Antwort schreiben: mit LLM (z. B. Gemini) NUR aus diesen Einträgen, sonst regelbasiert.
Die KI darf nichts erfinden und nur Einträge nennen, die wir ihr mitgeben.
"""
import json
import math
import os
import re
import threading
import time
from datetime import date, timedelta

import httpx

from . import ai
from .collect import COORDS, OF_TOWNS, OTHER_TOWNS, TOWN_COORDS

OFFLINE = os.environ.get("OFFLINE", "0") == "1"
REGION_NAMES = {"Wunsiedel": "Fichtelgebirge", "Kronach": "Frankenwald", "Lichtenfels": "Obermain-Jura", "Forchheim": "Fränkische Schweiz",
                "Bamberg": "Bamberg", "Bayreuth": "Bayreuth", "Coburg": "Coburg", "Hof": "Hof", "Kulmbach": "Kulmbach"}
# Landschaftsnamen -> Landkreis/Region in unseren Daten
AREAS = {"fichtelgebirge": "Wunsiedel", "frankenwald": "Kronach", "obermain": "Lichtenfels", "jura": "Lichtenfels",
         "fränkische schweiz": "Forchheim", "steigerwald": "Bamberg", "coburger land": "Coburg", "hofer land": "Hof"}
OUTSIDE = OTHER_TOWNS + ["Berlin", "Hamburg", "Köln", "Frankfurt", "Stuttgart", "Leipzig", "Dresden", "Mittelfranken",
                         "Unterfranken", "Oberpfalz", "Oberbayern", "Allgäu", "Mallorca", "Österreich", "Tschechien", "Prag", "Wien"]
WDAYS = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]
OUTDOOR = ["rad", "fahrrad", "bike", "wander", "ausflug", "draußen", "spazier", "natur", "see", "berg", "tour", "picknick", "klettern"]
INDOOR = ["museum", "ausstellung", "führung", "burg", "konzert", "theater", "lesung", "labor", "therme", "workshop", "vortrag", "mitmachen", "slam", "messe"]
BADWX = ["regen", "regnet", "schlechtwetter", "schlechtem wetter", "drinnen", "nass", "indoor"]
STOPQ = set(("was ist am im in los gibt es der die das und ein eine an auf zu mit für wo wann welche welcher welches bei von dem den des "
             "ich wir möchte möchten will wollen kann können man mache machen tun fahren gehen unternehmen tipps tipp gute guten schöne "
             "schönen etwas mir uns dir heute morgen übermorgen nächste nächsten diese dieses diesem wochenende oder auch noch mal bitte "
             "planen plan hallo wie sonst nähe näher mich "
             "what can i do this is there the in at on for with my me to go a an where when which any some things thing are you "
             "recommend should we near").split())
SYN = {"konzert": ["konzert", "orgel", "musik"], "konzerte": ["konzert", "orgel", "musik"], "job": ["karriere", "arbeitgeber", "fachkräft", "bewerb"],
       "jobs": ["karriere", "arbeitgeber", "fachkräft", "bewerb", "messe"], "arbeit": ["karriere", "fachkräft", "bewerb"],
       "radfahren": ["rad"], "fahrrad": ["rad"], "radtour": ["rad"], "wandern": ["wander", "rundweg"], "kinder": ["kinder", "familie", "mitmachen"],
       "kindern": ["kinder", "familie", "mitmachen"], "familie": ["familie", "kinder", "mitmachen"], "veranstaltungen": [], "events": [],
       "essen": ["gasthaus", "brauerei", "markt", "fest"], "studium": ["studien", "hochschule", "universität"]}

SYSTEM = """Du bist der KI-Begleiter von „oberfranken“, der Plattform von Oberfranken Offensiv e.V. für die Region Oberfranken in Bayern
(Landkreise und Städte Bamberg, Bayreuth, Coburg, Forchheim, Hof, Kronach, Kulmbach, Lichtenfels, Wunsiedel; Ferienregionen u. a.
Fichtelgebirge, Frankenwald, Fränkische Schweiz, Obermain-Jura, Steigerwald, Coburger Land).

Regeln:
- Du hilfst NUR bei Fragen zu Oberfranken: Ausflüge, Freizeit, Veranstaltungen, Kultur, Natur, Wohnen, Arbeit, Studium, Zukunft der Region.
- Passt eine Frage nicht zu Oberfranken (andere Regionen, Allgemeinwissen, Programmieren, Politik, Hausaufgaben …), setze "in_scope": false,
  antworte in einem freundlichen Satz, dass du nur für Oberfranken da bist, und schlage eine passende Frage zu Oberfranken vor.
- „eintraege_stichwortsuche“ sind die Treffer einer einfachen Wortsuche; prüfe auch „weitere_eintraege“, ob etwas besser zur Frage passt (andere Wörter, gleiche Bedeutung), und wähle die passendsten.
- Nutze AUSSCHLIESSLICH die mitgegebenen Einträge, das Wissen der Redaktion und die Wettervorhersage. Erfinde keine Orte, Termine, Preise,
  Öffnungszeiten oder Links. Wenn die Einträge die Frage nicht beantworten, sag ehrlich, dass du dazu nichts Sicheres gefunden hast.
- Sprich die Person mit „du“ an, freundlich und knapp: höchstens 3 kurze Sätze. Keine Aufzählungen, keine Emojis.
- Bei Wetterfragen antworte mit „wettervorhersage_region“ (Tag, Wetter, Höchsttemperatur, Regenrisiko); du hast diese Daten, sag nie, dass du keinen Zugriff hast. Danach 1–2 passende Einträge.
- Wenn für den Tag Regen vorhergesagt ist und die Frage nach draußen geht, sag das offen und verweise auf die Alternativen für drinnen.
- Nenne Entfernungen nur, wenn sie im Eintrag stehen („km“ = Luftlinie vom Wohnort der Person).

Antworte NUR mit JSON in genau diesem Format:
{"in_scope": true|false, "answer": "höchstens 3 Sätze", "ids": [IDs der passenden Einträge, beste zuerst, höchstens 4],
 "alt_ids": [IDs der Alternativen für drinnen, nur wenn sinnvoll], "followups": ["3 kurze Folgefragen, jeweils als vollständige Frage, die ohne Vorwissen verständlich ist"]}"""


# ---------------- Hilfsfunktionen ----------------
WXQ = re.compile(r"\b(wetter\w*|temperatur\w*|vorhersage|wie warm|wie kalt|grad|regnet|regnen|schneit|sonnig|weather|forecast)\b")


def km(a, b):
    """Luftlinie in km zwischen zwei (lat, lon)."""
    if not a or not b or None in (*a, *b):
        return None
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return round(2 * 6371 * math.asin(math.sqrt(h)))


def wx_icon(code):
    if code is None:
        return ""
    return "☀️" if code <= 1 else "⛅" if code == 2 else "☁️" if code in (3, 45, 48) else "❄️" if 71 <= code <= 77 else "⛈️" if code >= 95 else "🌧️"


WCODE = {0: "sonnig", 1: "überwiegend sonnig", 2: "teils bewölkt", 3: "bewölkt", 45: "Nebel", 48: "Nebel", 51: "Nieselregen", 53: "Nieselregen",
         55: "Nieselregen", 61: "leichter Regen", 63: "Regen", 65: "starker Regen", 71: "Schnee", 73: "Schnee", 75: "starker Schnee",
         80: "Regenschauer", 81: "Regenschauer", 82: "Regenschauer", 95: "Gewitter"}
_fc = {"t": 0, "data": {}}
_fc_lock = threading.Lock()


def _get_fc(names):
    return httpx.get("https://api.open-meteo.com/v1/forecast", timeout=8, params={
        "latitude": ",".join(str(COORDS[n][0]) for n in names), "longitude": ",".join(str(COORDS[n][1]) for n in names),
        "daily": "weather_code,temperature_2m_max,precipitation_probability_max", "timezone": "Europe/Berlin", "forecast_days": 8})


def _refresh_fc():
    data = {}
    names = list(COORDS)
    try:
        try:
            r = _get_fc(names)
        except httpx.TransportError:  # zweiter Versuch bei kurzem Netzproblem
            r = _get_fc(names)
        js = r.json()
        js = js if isinstance(js, list) else [js]
        for n, d in zip(names, js):
            dd = d["daily"]
            data[n] = {day: {"code": int(c), "tmax": round(t), "prob": p or 0} for day, c, t, p in
                       zip(dd["time"], dd["weather_code"], dd["temperature_2m_max"], dd["precipitation_probability_max"]) if c is not None}
    except Exception as e:
        print("Wettervorhersage nicht erreichbar:", type(e).__name__, e)
    with _fc_lock:
        if data or not _fc["data"]:  # alte Daten behalten, wenn der neue Abruf scheitert
            _fc["data"] = data or _fc["data"]
        _fc.update(t=time.time(), busy=False, ok=bool(data))


def forecast():
    """7-Tage-Vorhersage für alle 9 Regionen in EINEM Aufruf (Open-Meteo, ohne Schlüssel), 30 min Cache.
    Blockiert nie: ist der Cache alt, wird im Hintergrund neu geladen und solange der alte Stand genutzt.
    So bleibt die Seite schnell, auch bei schlechtem WLAN."""
    if OFFLINE:
        return {}
    with _fc_lock:
        age = time.time() - _fc["t"]
        stale = age >= (1800 if _fc.get("ok") else 30)
        if stale and not _fc.get("busy"):
            _fc["busy"] = True
            threading.Thread(target=_refresh_fc, daemon=True).start()
        return _fc["data"]


_town_fc = {}


def town_fc(name):
    """Vorhersage für einen genauen Ort (amtliche Koordinaten), 30 min Cache. Fehler -> None (dann gilt die Region)."""
    xy = TOWN_COORDS.get(name)
    if not xy or OFFLINE:
        return None
    hit = _town_fc.get(name)
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    try:
        p = {"latitude": xy[0], "longitude": xy[1], "daily": "weather_code,temperature_2m_max,precipitation_probability_max",
             "timezone": "Europe/Berlin", "forecast_days": 8}
        try:
            r = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=8, params=p)
        except httpx.TransportError:  # zweiter Versuch bei kurzem Netzproblem
            r = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=8, params=p)
        dd = r.json()["daily"]
        data = {day: {"code": int(c), "tmax": round(t), "prob": p or 0} for day, c, t, p in
                zip(dd["time"], dd["weather_code"], dd["temperature_2m_max"], dd["precipitation_probability_max"]) if c is not None}
        _town_fc[name] = (time.time(), data)
        return data
    except Exception:
        return hit[1] if hit else None


def day_weather(region, day, town=None):
    """Wetter für Region (oder genauen Ort) + Tag (date) oder None."""
    if not day:
        return None
    tf = town_fc(town) if town else None
    if tf and tf.get(day.isoformat()):
        d = tf[day.isoformat()]
        rain = d["code"] >= 51 or d["prob"] >= 60
        return {"date": day.isoformat(), "region": town, "code": d["code"], "icon": wx_icon(d["code"]), "text": WCODE.get(d["code"], "wechselhaft"),
                "tmax": d["tmax"], "prob": d["prob"], "rain": rain, "town": town}
    d = forecast().get(region if region in COORDS else "Bamberg", {}).get(day.isoformat())
    if not d:
        return None
    rain = d["code"] >= 51 or d["prob"] >= 60
    return {"date": day.isoformat(), "region": region, "code": d["code"], "icon": wx_icon(d["code"]), "text": WCODE.get(d["code"], "wechselhaft"),
            "tmax": d["tmax"], "prob": d["prob"], "rain": rain}


def target_days(q, today=None):
    """Erkennt den gewünschten Zeitraum. Gibt (von, bis, Bezeichnung) oder (None, None, '')."""
    today = today or date.today()
    low = q.lower()
    if "übermorgen" in low:
        d = today + timedelta(days=2); return d, d, "übermorgen"
    if re.search(r"\bmorgen\b", low):
        d = today + timedelta(days=1); return d, d, "morgen"
    if "heute" in low:
        return today, today, "heute"
    if "wochenende" in low:
        sat = today + timedelta(days=(5 - today.weekday()) % 7)
        if today.weekday() == 6:
            sat = today - timedelta(days=1)
        return sat, sat + timedelta(days=1), "am Wochenende"
    for i, w in enumerate(WDAYS):
        if re.search(r"\b" + w, low):
            d = today + timedelta(days=(i - today.weekday()) % 7)
            return d, d, f"am {w.capitalize()}"
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.?", low)
    if m:
        try:
            d = date(today.year, int(m.group(2)), int(m.group(1)))
            if d < today:
                d = d.replace(year=today.year + 1)
            return d, d, f"am {d.strftime('%d.%m.')}"
        except ValueError:
            pass
    return None, None, ""


# Ferienregionen reichen über Landkreisgrenzen: Orte, die zusätzlich dazugehören
AREA_TOWNS = {
    "Wunsiedel": {"Bischofsgrün", "Fichtelberg", "Warmensteinach", "Mehlmeisel", "Weißenstadt", "Marktredwitz", "Selb", "Kirchenlamitz", "Bad Berneck", "Gefrees"},
    "Kronach": {"Naila", "Geroldsgrün", "Bad Steben", "Lichtenberg", "Schwarzenbach am Wald", "Presseck", "Wallenfels", "Steinwiesen", "Ludwigsstadt"},
    "Forchheim": {"Pottenstein", "Gößweinstein", "Ebermannstadt", "Muggendorf", "Waischenfeld", "Tüchersfeld", "Hollfeld", "Heiligenstadt"},
    "Lichtenfels": {"Bad Staffelstein", "Weismain", "Burgkunstadt", "Altenkunstadt"},
}


def in_area(it, region):
    """Gehört der Eintrag zur Region? Landkreis ODER ein Ort der gleichnamigen Ferienregion (z. B. Ochsenkopf → Fichtelgebirge)."""
    return bool(region) and (it.get("region") == region or it.get("location") in AREA_TOWNS.get(region, ()))


EN = {"weekend": "wochenende", "today": "heute", "tomorrow": "morgen", "saturday": "samstag", "sunday": "sonntag", "friday": "freitag",
      "hiking": "wandern", "hike": "wandern", "bike": "rad", "cycling": "rad", "kids": "kinder", "children": "kinder", "family": "familie",
      "rain": "regen", "rains": "regen", "raining": "regen", "rainy": "regen", "museum": "museum", "museums": "museum", "concert": "konzert", "concerts": "konzert",
      "job": "job", "jobs": "jobs", "events": "events", "event": "events", "weather": "wetter", "indoors": "drinnen", "inside": "drinnen", "indoor": "drinnen",
      "outdoors": "draußen", "outside": "draußen", "monday": "montag", "tuesday": "dienstag", "wednesday": "mittwoch", "thursday": "donnerstag",
      "study": "studium", "studies": "studium", "university": "hochschule", "universities": "hochschule", "apprenticeship": "ausbildung", "training": "ausbildung",
      "career": "karriere", "careers": "karriere", "work": "arbeit", "else": "sonst", "trip": "ausflug", "excursion": "ausflug", "walk": "spazier",
      "theatre": "theater", "theater": "theater", "market": "markt", "markets": "markt", "beer": "bier", "brewery": "brauerei", "church": "kirche",
      "castle": "burg", "exhibition": "ausstellung", "exhibitions": "ausstellung", "tour": "führung", "tours": "führung", "guided": "", "festival": "fest",
      "move": "ziehen", "moving": "ziehen", "funding": "förderung", "founders": "gründer", "founder": "gründer", "nearby": "nähe", "near": "nähe"}
EN_STOP = set("what whats s is are on this the a an in at there any can could i do me my to for with if it of and or which where when how about "
              "some something going happening up do does be should would like want go get find there's here please tell show".split())


def normalize(q):
    """Englische Stichwörter für die Suche ins Deutsche (die Antwort selbst schreibt das LLM in der Sprache der Frage)."""
    q = re.sub(r"(?i)upper franconia", "Oberfranken", q).replace("’", "'")
    toks = [t.lower() for t in re.findall(r"[A-Za-z]+", q)]
    if not any((t in EN or t in EN_STOP) and t not in ("in", "an", "so", "museum", "theater", "events", "job", "jobs") for t in toks):
        return q  # deutsche Frage: nichts ändern
    def w(m):
        x = m.group(0).lower()
        return EN[x] if x in EN else ("" if x in EN_STOP else m.group(0))
    return re.sub(r"\s+", " ", re.sub(r"[A-Za-z]+", w, q)).strip()


def where_txt(region):
    name = REGION_NAMES.get(region, region)
    return {"Fichtelgebirge": "im Fichtelgebirge", "Frankenwald": "im Frankenwald", "Obermain-Jura": "am Obermain",
            "Fränkische Schweiz": "in der Fränkischen Schweiz"}.get(name, f"in {name}")


AMBIG = {"Berg", "Ahorn", "Nagel", "Lauter", "Haag", "Hausen", "Gerach", "Trogen", "Weißenbrunn", "Eckental"}


def find_place(q):
    """Ort oder Landschaft in der Frage -> (Anzeigename, Region)."""
    low = q.lower()
    for a, reg in AREAS.items():
        if a in low:
            return a.title() if a != "fränkische schweiz" else "Fränkische Schweiz", reg
    for t in sorted(OF_TOWNS, key=len, reverse=True):
        if t in AMBIG:  # Ortsnamen, die auch normale Wörter sind: nur nach „in/nach/aus/bei …“
            if re.search(r"\b(in|nach|aus|bei|um|von)\s+" + re.escape(t.lower()) + r"\b", low):
                return t, OF_TOWNS[t]
            continue
        if re.search(r"(?<![\w-])" + re.escape(t.lower()) + r"(?![\w-])", low):
            return t, OF_TOWNS[t]
    return None, None


def outside_place(q):
    low = q.lower()
    return next((t for t in OUTSIDE if re.search(r"\b" + re.escape(t.lower()) + r"\b", low)), None)


# ---------------- Suche in den eigenen Inhalten (RAG) ----------------
def retrieve(q, items, region=None, d_from=None, d_to=None, limit=4, exclude=(), home=None):
    low = q.lower()
    words = [w for w in re.findall(r"[a-zäöüß]+", low) if w not in STOPQ and w not in WDAYS and not any(b in w for b in BADWX)]
    place, place_region = find_place(q)
    if place:
        words = [w for w in words if w not in place.lower()]
    terms = []
    for w in words:
        terms += SYN.get(w, [w])
    region = place_region or region
    hits = []
    for it in items:
        if it["id"] in exclude:
            continue
        hay = (it["title"] + " " + (it.get("summary") or "") + " " + (it.get("text") or "") + " " + it["category"]).lower()
        topic = sum(2 for t in terms if len(t) > 2 and re.search(r"\b" + re.escape(t[:max(3, len(t) - 2)]), hay))
        s = topic
        if terms and not topic:
            continue  # Thema gefragt, aber nicht getroffen
        if region:
            s += 3 if in_area(it, region) else (-6 if place_region else 0)
        elif home in COORDS:  # keine Region gefragt: Nähe zum eigenen Wohnort bevorzugen
            d = km(COORDS[home], (it.get("lat"), it.get("lon")))
            s += 2 if in_area(it, home) else (1 if d is not None and d <= 35 else 0)
        ev = (it.get("event_date") or "")[:10]
        if d_from:
            if ev and d_from.isoformat() <= ev <= d_to.isoformat():
                s += 3
            elif ev:
                s -= 6
        elif ev and ev < date.today().isoformat():
            s -= 6
        if not terms:
            s += 1
        if s > 0:
            hits.append((s, it))
    hits.sort(key=lambda x: (-x[0], x[1].get("event_date") or "9999"))
    return [it for _, it in hits[:limit]], terms, place, region


def indoor_alternatives(items, d_from, d_to, region, exclude):
    """Alternativen für drinnen am selben Tag (oder ±1 Tag), Region bevorzugt."""
    out = []
    lo = d_from.isoformat() if d_from else date.today().isoformat()
    hi = d_to.isoformat() if d_to else (date.today() + timedelta(days=7)).isoformat()
    for it in items:
        if it["id"] in exclude:
            continue
        hay = (it["title"] + " " + (it.get("summary") or "")).lower()
        ev = (it.get("event_date") or "")[:10]
        if not any(k in hay for k in INDOOR) or (ev and not lo <= ev <= hi):
            continue
        s = (3 if in_area(it, region) else 0) + (2 if ev and d_from and d_from.isoformat() <= ev <= d_to.isoformat() else 0)
        out.append((s, it))
    out.sort(key=lambda x: -x[0])
    return [it for _, it in out[:3]]


# ---------------- Begrenzung der LLM-Aufrufe (schützt Kosten / Gratis-Kontingent) ----------------
_calls = []
MAX_PER_MIN = int(os.environ.get("CHAT_MAX_PER_MIN", "20"))


def _budget_ok():
    now = time.time()
    while _calls and now - _calls[0] > 60:
        _calls.pop(0)
    if len(_calls) >= MAX_PER_MIN:
        return False
    _calls.append(now)
    return True


def _short(it, home_xy, n=300):
    return {"id": it["id"], "titel": it["title"], "datum": (it.get("event_date") or "")[:10] or None, "ort": it.get("location"),
            "region": REGION_NAMES.get(it.get("region"), it.get("region")), "kategorie": it["category"],
            "km": km(home_xy, (it.get("lat"), it.get("lon"))), "kurz": (it.get("summary") or "")[:n], "quelle": it.get("source")}


def _web(res, question, lang="de"):
    """Nichts in unseren Einträgen? Dann Suche auf den geprüften Seiten (erst Stufe 1 Oberfranken, dann Stufe 2).
    Weg 1: Google-Suche über Gemini (braucht Kontingent für „Grounding“).
    Weg 2 (wenn Weg 1 nicht geht): eigene Suche in den Sitemaps der geprüften Seiten + Gemini liest die Seiten.
    Nur Antworten mit Quellen von diesen Seiten werden gezeigt."""
    if ai.grounding_ok():
        for key, label in (("stufe1_oberfranken", "Stufe 1: Oberfranken"), ("stufe2_bayern_bund_eu", "Stufe 2: Bayern, Bund, EU")):
            try:
                txt, src = ai.web_answer(question, ai.TRUSTED[key], label, lang)
            except Exception as e:
                if isinstance(e, ai.LLMError) and e.status in (429, 403, 404):
                    ai.grounding_off(f"HTTP {e.status}")  # kein Kontingent -> eine Stunde lang direkt eigene Suche
                else:
                    res["engine_note"] = f"Google-Suche nicht möglich ({type(e).__name__})"
                break
            if txt:
                res.update(answer=txt, web_sources=src, found=True, items=[], alternatives=[],
                           engine=f"{ai.engine_name()} + Google-Suche nur auf geprüften Seiten ({label})")
                return True
    try:
        txt, src = ai.site_answer(question, lang)
    except Exception as e:
        why = f"HTTP {e.status}: {e.hint}" if isinstance(e, ai.LLMError) else type(e).__name__
        res["engine_note"] = f"Suche auf geprüften Seiten nicht möglich ({why})"
        return False
    if txt:
        res.update(answer=txt, web_sources=src, found=True, items=[], alternatives=[],
                   engine=f"{ai.engine_name()} + eigene Suche auf geprüften Seiten")
        return True
    return False


# ---------------- Hauptfunktion ----------------
def respond(q, items, curated, home="Bamberg", page_region=None, history=None, lang="de", town=None):
    q_orig, q = q, normalize(q)
    today = date.today()
    home = home if home in COORDS else "Bamberg"
    home_xy = COORDS[home]
    d_from, d_to, label = target_days(q, today)
    low = q.lower()
    bad_wx_q = any(b in low for b in BADWX)
    outdoor_q = any(o in low for o in OUTDOOR)

    # 1. Außerhalb von Oberfranken?
    out = outside_place(q)
    place, place_region = find_place(q)
    if out and not place:
        return {"in_scope": False, "answer": f"Ich bin dein Begleiter für Oberfranken, zu {out} kann ich dir leider nichts sagen. "
                f"Wie wäre es stattdessen mit einem Ausflug ins Fichtelgebirge oder in den Frankenwald?",
                "items": [], "alternatives": [], "weather": None, "found": False,
                "followups": ["Was kann ich am Wochenende im Frankenwald machen?", "Welche Radtouren gibt es in Oberfranken?", "Was ist heute in Oberfranken los?"],
                "engine": "Regel: außerhalb Oberfrankens", "label": label}

    # 1b. „Warum bist du besser als ChatGPT?“ – ehrlicher Vergleich statt Suche
    if re.search(r"(?i)chat\s?gpt|gemini|copilot|andere[nr]? ki|other ai|besser als|unterschied zu|warum (soll|sollte) ich (dich|euch|diese)|why (should i use|are you better)|better than", q_orig):
        return {"in_scope": True, "found": True, "items": [], "alternatives": [], "weather": None, "label": label,
                "answer": "Allgemeine KI-Chatbots wissen viel über die Welt, ich weiß genau, was in Oberfranken los ist. "
                          "Meine Termine und Meldungen kommen jede Stunde neu von den offiziellen Seiten der Region, jede Antwort hat eine Quelle mit Link, "
                          "und wenn nichts in den Quellen steht, sage ich das, statt etwas zu erfinden. Ich kenne alle 214 Orte mit eigenem Wetter. "
                          "Du brauchst kein Konto und deine Fragen werden nicht gespeichert. Für Texte schreiben oder Programmieren sind allgemeine Chatbots stärker.",
                "followups": ["Was ist am Wochenende los?", "Wie wird das Wetter in Bamberg?", "Ich will nach Oberfranken ziehen. Wo fange ich an?"],
                "engine": "Regel: Vergleich"}

    # 2a. Wetterfrage („Wie wird das Wetter in Coburg?“): Vorhersage + passende Tipps
    weather_q = bool(WXQ.search(low)) and "drinnen" not in low
    fc_days = []
    if weather_q:
        region = place_region or page_region or home
        # genauer Ort: aus der Frage („Wetter in Steinbach am Wald“) oder der eigene Wohnort
        wx_town = place if (place and place in TOWN_COORDS and place not in COORDS) else (town if (not place and not page_region and town in TOWN_COORDS and town not in COORDS) else None)
        start = d_from or today
        days = [d_from, d_to] if (d_from and d_to and d_to != d_from) else [start + timedelta(days=k) for k in range(3)]
        fc_days = [w for w in (day_weather(region, d, wx_town) for d in days) if w]
        if not fc_days and not OFFLINE:  # Vorhersage fehlt (z. B. kurz nach dem Start): einmal direkt nachladen
            _refresh_fc()
            fc_days = [w for w in (day_weather(region, d) for d in days) if w]
        wx = fc_days[0] if fc_days else None
        if wx and wx["rain"]:
            hits = indoor_alternatives(items, days[0], days[-1], region, ())
        else:
            hits = [h for h in retrieve("", items, region, days[0], days[-1], limit=8)[0] if in_area(h, region)][:3]
        terms, next_up, alts, wx_region = [], False, [], region
    else:
        # 2. Suche + Wetter
        if bad_wx_q:  # „Was geht bei Regen?“ -> direkt drinnen suchen
            region = place_region or page_region or home
            hits = indoor_alternatives(items, d_from or today, d_to or today + timedelta(days=7), region, ())
            terms = []
        else:
            hits, terms, place, region = retrieve(q, items, page_region, d_from, d_to, home=home)
        next_up = False
        if d_from and not hits and not bad_wx_q:  # am gefragten Tag nichts -> die nächsten Termine zeigen statt „nichts gefunden“
            later = [h for h in retrieve(q, items, page_region, None, None, limit=6, home=home)[0] if (h.get("event_date") or "9") >= d_from.isoformat()][:3]
            if later:
                hits, next_up = later, True
        wx_region = region or (hits[0].get("region") if hits else None) or home
        wx = day_weather(wx_region, d_from) if d_from else None
        if wx and d_to and d_to != d_from:  # Wochenende: schlechterer der beiden Tage zählt
            wx2 = day_weather(wx_region, d_to)
            if wx2 and wx2["rain"] and not wx["rain"]:
                wx = wx2
        alts = []
        if not bad_wx_q and (outdoor_q or not terms) and ((wx and wx["rain"]) or not hits):
            alts = indoor_alternatives(items, d_from, d_to, wx_region, {h["id"] for h in hits}) if (wx and wx["rain"]) else []

    # 3. Folgefragen (Regel-Variante)
    when = label or "am Wochenende"
    area = REGION_NAMES.get(region, region) if region else None
    wtxt = " " + where_txt(region) if region else ""
    work = hits and sum(1 for h in hits if h["category"] in ("Wirtschaft", "Wissenschaft")) > len(hits) / 2
    follow = []
    if weather_q:
        follow += [f"Was kann ich {when}{wtxt} bei Regen drinnen machen?", "Ich möchte am Samstag Fahrrad fahren", f"Was ist {when}{wtxt} los?"]
    elif work:
        follow += [f"Welche Karriere-Termine gibt es in der Nähe von {home}?", "Wo kann ich in Oberfranken studieren?", "Gibt es Hilfe beim Bewerben?"]
    else:
        if not bad_wx_q:
            follow.append(f"Was kann ich {when}{wtxt} bei Regen drinnen machen?")
        if "kinder" not in low and "familie" not in low:
            follow.append(f"Was kann ich {when}{wtxt} mit Kindern machen?")
        if region and region != home:
            follow.append(f"Was ist {when} in der Nähe von {home} los?")
        follow.append(f"Was ist {when} sonst in Oberfranken los?")
    follow = follow[:3]

    by_id = {it["id"]: it for it in items}
    res = {"in_scope": True, "next_up": next_up, "items": hits, "alternatives": alts, "weather": wx, "followups": follow, "label": label,
           "found": bool(hits or alts), "region": region, "home": home, "forecast": fc_days}

    # 4. Antwort mit LLM (Gemini o. a.) – nur aus unseren Einträgen
    if ai.LLM_KEY and _budget_ok():
        # Gemini bekommt die Treffer der Stichwortsuche ZUERST und dazu alle kommenden Einträge (max. LLM_POOL),
        # damit es auch Fragen mit anderen Wörtern versteht („Kirche“ → Basilika, „Essen“ → Biergarten).
        # Bei ~40 Einträgen sind das ca. 3.000 Tokens pro Frage, mit Gemini Flash unter 0,1 Cent.
        rest = sorted([it for it in items if it not in hits and it not in alts], key=lambda it: it.get("event_date") or "9999")
        pool = hits + alts + rest[:max(0, int(os.environ.get("LLM_POOL", "40")) - len(hits) - len(alts))]
        ctx = {"heute": today.isoformat(), "wohnort_der_person": home, "gefragter_zeitraum": label or "offen",
               "hinweis": "Am gefragten Tag ist nichts eingetragen; die Einträge sind die nächsten Termine danach. Sag das kurz." if next_up else "",
               "wetter": wx, "wettervorhersage_region": fc_days or None,
               "eintraege_stichwortsuche": [_short(it, home_xy) for it in hits],
               "weitere_eintraege": [_short(it, home_xy, 160) for it in pool if it not in hits and it not in alts],
               "alternativen_drinnen": [_short(it, home_xy) for it in alts],
               "wissen_der_redaktion": [{"titel": c["title"], "text": c["text"], "link": c.get("link")} for c in curated][:8]}
        msgs = [{"role": "system", "content": SYSTEM + ("\n\nWICHTIG: Die Person nutzt die englische Ansicht. Schreibe „answer“ und „followups“ auf Englisch." if lang == "en" else "")}]
        for h in (history or [])[-2:]:
            if h.get("q") and h.get("a"):
                msgs += [{"role": "user", "content": str(h["q"])[:300]}, {"role": "assistant", "content": str(h["a"])[:600]}]
        msgs.append({"role": "user", "content": f"Kontext (JSON):\n{json.dumps(ctx, ensure_ascii=False)}\n\nFrage: {q_orig}"})
        try:
            content, tin, tout = ai.chat(msgs, json_mode=True, temperature=0.3, max_tokens=2000, timeout=30)
            ai.USAGE["chat_calls"] += 1; ai.USAGE["tokens_in"] += tin; ai.USAGE["tokens_out"] += tout
            js = ai._parse_json(content)
            ok_ids = {p["id"] for p in pool} | {a["id"] for a in alts}
            ids = [int(i) for i in js.get("ids", []) if str(i).isdigit() and int(i) in ok_ids][:4]
            alt_ids = [int(i) for i in js.get("alt_ids", []) if str(i).isdigit() and int(i) in ok_ids and int(i) not in ids][:3]
            res["in_scope"] = bool(js.get("in_scope", True))
            res["answer"] = str(js.get("answer") or "").strip()[:700]
            if not res["in_scope"]:
                res.update(items=[], alternatives=[], found=False)
            else:
                res["items"] = [by_id[i] for i in ids] if ids else hits
                res["alternatives"] = [by_id[i] for i in alt_ids] if alt_ids else alts
                res["found"] = bool(res["items"] or res["alternatives"])
            fu = [str(f).strip()[:120] for f in js.get("followups", []) if str(f).strip()]
            if fu:
                res["followups"] = fu[:3]
            res["engine"] = ai.engine_name()
            if res["answer"]:
                if res["in_scope"] and not res["found"] and not weather_q and _budget_ok():
                    _web(res, q_orig, lang)
                return res
        except Exception as e:
            why = f"HTTP {e.status}: {e.hint}" if isinstance(e, ai.LLMError) else type(e).__name__
            res["engine_note"] = f"KI-Fehler ({why}), Antwort regelbasiert"

    # 5. Regel-Antwort (ohne Schlüssel, bei Fehler oder Limit) – vorher noch die Websuche, falls nichts gefunden
    if ai.LLM_KEY and not hits and not alts and not weather_q and _web(res, q_orig, lang):
        return res
    parts = []
    where = " " + where_txt(region) if region else " in Oberfranken"
    if weather_q:
        if fc_days:
            def dname(w):
                d = date.fromisoformat(w["date"])
                return "Heute" if d == today else "Morgen" if d == today + timedelta(days=1) else ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][d.weekday()]
            parts.append(f"Wetter {('in ' + fc_days[0]['town']) if fc_days[0].get('town') else where_txt(region)}: " + "; ".join(f"{dname(w)} {w['text']}, bis {w['tmax']} °C, Regenrisiko {w['prob']} %" for w in fc_days) + ".")
            if hits:
                parts.append("Bei Regen passt das hier gut, drinnen:" if wx and wx["rain"] else "Das ist in der Nähe los:")
        else:
            parts.append("Die Wettervorhersage (Open-Meteo) ist gerade nicht erreichbar. Versuch es in einer Minute noch einmal.")
    elif hits and next_up:
        lead = label.capitalize() if label in ("heute", "morgen", "übermorgen") else (f"Am {label[3:]}" if label.startswith("am ") else "Dann")
        parts.append(f"{lead} ist{where} noch nichts eingetragen. Das {'ist der nächste Termin' if len(hits) == 1 else f'sind die nächsten {len(hits)} Termine'}:")
    elif hits and bad_wx_q:
        lead = {"am Wochenende": "Fürs Wochenende", "heute": "Für heute", "morgen": "Für morgen"}.get(label) \
            or (f"Für den {label[3:]}" if label.startswith("am ") else "Für die nächsten Tage")
        near = min((km(home_xy, (h.get("lat"), h.get("lon"))) or 999) for h in hits)
        parts.append(f"{lead} habe ich {len(hits)} {'Idee' if len(hits) == 1 else 'Ideen'} für drinnen gefunden"
                     + (f", die nächste ist ca. {near} km von {home} entfernt." if near < 999 else "."))
    elif hits:
        lead = {"am Wochenende": "Fürs Wochenende", "heute": "Für heute", "morgen": "Für morgen", "übermorgen": "Für übermorgen"}.get(label) \
            or (f"Für den {label[3:]}" if label.startswith("am ") else "Dazu")
        parts.append(f"{lead} habe ich {'einen passenden Tipp' if len(hits) == 1 else f'{len(hits)} passende Tipps'}{where} gefunden.")
    else:
        parts.append(f"Dazu habe ich in den Inhalten aus Oberfranken nichts Sicheres gefunden. Schau gern bei den offiziellen Seiten der Region nach.")
    if wx and wx["rain"] and outdoor_q and not bad_wx_q and not weather_q:  # Wetter steht schon im Badge, hier nur der Hinweis
        parts.append(f"Achtung, {where_txt(wx['region'])} ist {wx['text']} angesagt"
                     + (", darunter findest du deshalb auch Ideen für drinnen." if alts else ", plane besser eine Regenjacke ein."))
    res["answer"] = " ".join(parts)
    res["engine"] = res.get("engine_note") or ai.engine_name()
    return res
