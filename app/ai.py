"""KI-Verarbeitung: Zusammenfassung, Übersetzung, Kategorie, Priorität, Ort, Datum.

Mit API-Schlüssel: echtes LLM über eine OpenAI-kompatible Schnittstelle
(Mistral, IONOS, STACKIT, OpenAI ...). Ohne Schlüssel: regelbasierte Extraktion.
"""
import json
import os
import time
import re
from datetime import date, timedelta

import httpx

from .collect import OF_TOWNS, OTHER_TOWNS

TOPICS = ["Events", "Tourismus", "Wirtschaft", "Wissenschaft", "Kultur", "Region"]
MONTHS = ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"]
WDAYS = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]
CAT_WORDS = {
    "Events": ["markt", "fest", "kirchweih", "feier", "party", "festzug", "ferienprogramm", "flohmarkt", "kinder"],
    "Tourismus": ["wanderung", "wandern", "führung", "burg", "ausflug", "radtour", "naturpark", "tour", "gäste", "schloss"],
    "Wirtschaft": ["unternehmen", "firma", "job", "karriere", "messe", "gründ", "fachkräft", "arbeitgeber", "ausbildung", "handwerk", "mittelstand", "bewerb"],
    "Wissenschaft": ["hochschule", "universität", "forschung", "studium", "studien", "labor", "professor", "wissenschaft", "studierende"],
    "Kultur": ["konzert", "ausstellung", "museum", "theater", "lesung", "kunst", "orgel", "oper", "kultur", "galerie"],
}
STOP = set("termin entlang minuten eintritt anmeldung geführte geführten dauer stunden nötig erforderlich dass diese dieser einem einer einen unter durch gegen neuen neues statt findet beginn über außerdem bereits können werden wurden sowie dabei zeigen zeigt stellen jeden ihren ihrer sich nicht oder auch noch eine einen mehr ihre".split())

# Kurzweg für Gemini: nur GEMINI_API_KEY setzen, Adresse und Modell kommen automatisch.
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
LLM_KEY = os.environ.get("LLM_API_KEY", "") or GEMINI_KEY
_DEF_BASE = "https://generativelanguage.googleapis.com/v1beta/openai" if (GEMINI_KEY and not os.environ.get("LLM_API_KEY")) else "https://api.mistral.ai/v1"
_DEF_MODEL = "gemini-flash-latest" if (GEMINI_KEY and not os.environ.get("LLM_API_KEY")) else "mistral-small-latest"
LLM_BASE = (os.environ.get("LLM_BASE_URL") or _DEF_BASE).rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL") or _DEF_MODEL
PRICE_IN = float(os.environ.get("LLM_PRICE_IN", "0.11"))    # $ pro 1 Mio. Tokens
PRICE_OUT = float(os.environ.get("LLM_PRICE_OUT", "0.33"))


def engine_name():
    return f"LLM: {LLM_MODEL}" if LLM_KEY else "Regelbasiert (kein API-Schlüssel)"


def prompt(text, today=None):
    today = today or date.today()
    return (
        f"Du bist die KI-Verarbeitung einer regionalen Content-Plattform für Oberfranken (Bayern). Heute ist der {today.isoformat()}.\n"
        "Verarbeite den Text unten und antworte NUR mit einem JSON-Objekt in genau diesem Format:\n"
        '{"title": string, "summary": "2-3 Sätze auf Deutsch, nur Fakten aus dem Text", '
        '"summary_en": "dieselbe Kurzfassung auf Englisch", '
        '"category": "Events" | "Tourismus" | "Wirtschaft" | "Wissenschaft" | "Kultur", '
        '"keywords": [bis zu 5 Schlagwörter], '
        '"priority": 1-5 (Relevanz für Menschen in Oberfranken; 1 wenn nicht in Oberfranken), '
        '"location": "Ortsname oder null", "event_date": "YYYY-MM-DD oder null", '
        '"confidence": Zahl 0-1 (wie sicher du bei Ort, Datum und Kategorie bist), '
        '"notes": "Unsicherheiten in einem Satz, sonst leer"}\n'
        "Erfinde nichts, was nicht im Text steht. Relative Angaben wie „Samstag“ beziehst du auf das heutige Datum.\n\n"
        f'Text:\n"""\n{text[:6000]}\n"""'
    )


def _parse_json(s):
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            return json.loads(m.group(0))
        raise


USAGE = {"chat_calls": 0, "tokens_in": 0, "tokens_out": 0}


def chat(messages, json_mode=True, temperature=0.2, max_tokens=None, timeout=90):
    """Ein Aufruf an die OpenAI-kompatible Schnittstelle (Gemini, Mistral, IONOS ...).
    Gibt (inhalt, tokens_in, tokens_out) zurück."""
    global LLM_MODEL
    body = {"model": LLM_MODEL, "temperature": temperature, "messages": messages}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if max_tokens:
        body["max_tokens"] = max_tokens
    if "generativelanguage" in LLM_BASE:
        # Gemini „denkt“ standardmäßig mit; die Denk-Tokens zählen zum Antwort-Limit. Wenig Denken = schneller, billiger,
        # und die JSON-Antwort wird nicht abgeschnitten.
        body["reasoning_effort"] = os.environ.get("LLM_REASONING", "low")
    headers = {"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"}
    r = httpx.post(f"{LLM_BASE}/chat/completions", headers=headers, json=body, timeout=timeout)
    if r.status_code == 400 and ("response_format" in body or "reasoning_effort" in body):
        body.pop("response_format", None)  # falls ein Anbieter JSON-Modus oder reasoning_effort nicht kennt
        body.pop("reasoning_effort", None)
        r = httpx.post(f"{LLM_BASE}/chat/completions", headers=headers, json=body, timeout=timeout)
    if r.status_code == 404 and "generativelanguage" in LLM_BASE and body["model"] != FALLBACK_MODEL:
        body["model"] = FALLBACK_MODEL  # Modellname unbekannt -> immer aktuelles Flash-Modell von Google
        r = httpx.post(f"{LLM_BASE}/chat/completions", headers=headers, json=body, timeout=timeout)
        if r.status_code < 400:
            LLM_MODEL = FALLBACK_MODEL  # ab jetzt direkt das funktionierende Modell nutzen
            print(f"[KI] Modell gewechselt auf {FALLBACK_MODEL}")
    if r.status_code in (429, 500, 503) and "generativelanguage" in LLM_BASE:
        # Modell überlastet oder Limit erreicht: kurz warten, dann andere Flash-Modelle probieren
        for alt in _alts(body["model"]):
            time.sleep(0.8)
            body["model"] = alt
            r = httpx.post(f"{LLM_BASE}/chat/completions", headers=headers, json=body, timeout=timeout)
            if r.status_code < 400:
                if alt != LLM_MODEL:
                    print(f"[KI] {LLM_MODEL} ist gerade überlastet, nutze {alt}.")
                    LLM_MODEL = alt
                break
            if r.status_code not in (429, 500, 503, 404):
                break
    if r.status_code >= 400:
        raise LLMError(r.status_code, r.text)
    js = r.json()
    u = js.get("usage", {}) or {}
    LAST_STATUS.update(ok=True, text=f"OK ({body['model']})")
    return js["choices"][0]["message"]["content"] or "", u.get("prompt_tokens", 0), u.get("completion_tokens", 0)


FALLBACK_MODEL = os.environ.get("LLM_FALLBACK_MODEL", "gemini-2.5-flash")
ALT_MODELS = [m.strip() for m in os.environ.get("LLM_ALT_MODELS", "gemini-flash-latest,gemini-2.5-flash,gemini-3-flash-preview,gemini-flash-lite-latest").split(",") if m.strip()]
AVAILABLE = []  # Modelle, die der Schlüssel laut Google nutzen darf (wird beim Start abgefragt)
WEB_ATTEMPTS = []  # letzte Versuche der Websuche (für test_gemini.bat)


def _alts(first):
    """Reihenfolge der Modelle: eingestelltes zuerst, dann Ausweichmodelle, nur solche, die der Schlüssel kennt."""
    out = [first] + [m for m in ALT_MODELS if m != first]
    if AVAILABLE:
        ok = [m for m in out if m in AVAILABLE]
        out = ok or out
    return out
LAST_STATUS = {"ok": None, "text": "noch nicht getestet"}
HINTS = {400: "Anfrage abgelehnt (Modell oder Parameter)", 401: "API-Schlüssel ungültig", 403: "Schlüssel ohne Berechtigung oder API nicht freigeschaltet",
         404: "Modell oder Adresse nicht gefunden", 429: "Limit/Kontingent erreicht, kurz warten", 500: "Fehler beim Anbieter", 503: "Anbieter überlastet, gleich nochmal versuchen"}


class LLMError(Exception):
    """Fehler vom KI-Anbieter mit verständlicher Erklärung."""
    def __init__(self, status, body):
        msg = ""
        try:
            j = json.loads(body)
            j = j[0] if isinstance(j, list) else j
            msg = (j.get("error") or {}).get("message", "") if isinstance(j.get("error"), dict) else str(j.get("error", ""))
        except Exception:
            msg = (body or "")[:200]
        self.status = status
        self.hint = HINTS.get(status, "unbekannter Fehler")
        if "api key" in msg.lower() or "api_key" in msg.lower():
            self.hint = "API-Schlüssel ungültig oder unvollständig"
        self.detail = msg[:200]
        super().__init__(f"HTTP {status}: {self.hint}. {self.detail}")
        LAST_STATUS.update(ok=False, text=str(self))
        print(f"[KI] Fehler {status}: {self.hint}. {self.detail}")


def pick_model():
    """Fragt beim Anbieter die verfügbaren Modelle ab. Gibt es das eingestellte nicht, wird ein passendes Flash-Modell gewählt."""
    global LLM_MODEL
    try:
        r = httpx.get(f"{LLM_BASE}/models", headers={"Authorization": f"Bearer {LLM_KEY}"}, timeout=15)
        if r.status_code != 200:
            return None
        ids = [m.get("id", "").replace("models/", "") for m in r.json().get("data", [])]
        AVAILABLE[:] = ids
        if ids and LLM_MODEL not in ids:
            pref = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-3-flash-preview"]
            new = next((m for m in pref if m in ids), None) or next((m for m in ids if "flash" in m and "tts" not in m and "image" not in m), None)
            if new:
                print(f"[KI] Modell {LLM_MODEL} ist für diesen Schlüssel nicht verfügbar, nutze {new}.")
                LLM_MODEL = new
        return ids
    except Exception:
        return None


def selftest():
    """Kurzer Test beim Start: zeigt im Fenster, ob der Schlüssel funktioniert."""
    if not LLM_KEY:
        return
    pick_model()
    try:
        content, _, _ = chat([{"role": "user", "content": 'Antworte nur mit JSON: {"ok": true}'}], json_mode=True, max_tokens=200, timeout=20)
        print(f"[KI] Test erfolgreich: {LLM_MODEL} antwortet.")
    except LLMError:
        print("[KI] Test fehlgeschlagen, siehe Meldung oben. Bis dahin antwortet der Begleiter regelbasiert.")
    except Exception as e:
        LAST_STATUS.update(ok=False, text=f"{type(e).__name__}: {e}")
        print(f"[KI] Test fehlgeschlagen: {type(e).__name__}: {e}")


def llm(text):
    """Verarbeitung eines Textes. Gibt (ergebnis, tokens_in, tokens_out) zurück."""
    content, tin, tout = chat([{"role": "user", "content": prompt(text)}], json_mode=True, temperature=0.1)
    return _parse_json(content), tin, tout


def _town_hits(txt):
    """Orte im Text mit Position; auch Adjektivform („Coburger“ → Coburg). Ganze Wörter, längere Namen zuerst."""
    hits = []
    for t in sorted(OF_TOWNS, key=len, reverse=True):
        m = re.search(r"(?<![\wäöüß])" + re.escape(t) + r"(?:er)?(?![\wäöüß])", txt, re.I)
        if m and not any(a <= m.start() < b for _, a, b in hits):
            hits.append((t, m.start(), m.end()))
    return sorted(hits, key=lambda h: h[1])


def pick_town(title, body):
    """Ort aus Titel, sonst erster Ort im Text (nicht mehr: längster Ortsname irgendwo im Text,
    dadurch landete die „Coburger Studienmesse“ in Lichtenfels)."""
    for part in (title, body):
        hits = _town_hits(part)
        if hits:
            # „Warum sie in Coburg studieren“: Ort nach in/im/nach/bei/zu hat Vorrang vor bloßen Erwähnungen
            prep = [h for h in hits if re.search(r"\b(in|im|nach|bei|zu|zum|zur)\s+$", part[:h[1]], re.I)]
            return (prep or hits)[0][0]
    low = body.lower()
    return next((t for t in OTHER_TOWNS if re.search(r"\b" + re.escape(t.lower()) + r"\b", low)), None)


def rules(text, today=None):
    """Regelbasierte Extraktion ohne KI: Schlüsselwörter, Ortsliste, Datumsmuster."""
    today = today or date.today()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    flat = re.sub(r"\s+", " ", text).strip()
    low = flat.lower()
    title = (lines[0] if lines else flat)[:110]
    body = " ".join(lines[1:]) if len(lines) > 1 else flat
    sents = re.findall(r"[^.!?]+[.!?]", body) or [body]
    summary = " ".join(s.strip() for s in sents[:2])[:400]
    scores = {c: sum(1 for w in ws if w in low) for c, ws in CAT_WORDS.items()}
    cat = max(scores, key=scores.get) if max(scores.values()) else "Events"
    loc = pick_town(title, " ".join(l for l in lines[1:] if not l.startswith(("Ort:", "Datum:"))))
    ev = None
    m = re.search(r"(\d{1,2})\.\s*(" + "|".join(MONTHS) + r")(\s+\d{4})?", low)
    if m:
        y = int(m.group(3)) if m.group(3) else today.year
        try:
            d = date(y, MONTHS.index(m.group(2)) + 1, int(m.group(1)))
            if not m.group(3) and d < today - timedelta(days=60):
                d = d.replace(year=y + 1)
            ev = d.isoformat()
        except ValueError:
            pass
    if not ev:
        iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", low)
        if iso:
            try:
                ev = date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))).isoformat()
            except ValueError:
                pass
    if not ev:
        n = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", low)
        if n:
            try:
                ev = date(int(n.group(3)), int(n.group(2)), int(n.group(1))).isoformat()
            except ValueError:
                pass
    if not ev:
        for i, w in enumerate(WDAYS):
            if re.search(r"\b" + w, low):
                ev = (today + timedelta(days=(i - today.weekday()) % 7 or 7)).isoformat()
                break
    kw = []
    for w in re.findall(r"[a-zäöüß]{6,}", low):
        if w not in STOP and w not in kw:
            kw.append(w)
    conf = min(0.45 + (0.15 if loc else 0) + (0.15 if ev else 0) + (0.1 if max(scores.values()) else 0), 0.85)
    prio = 3
    if ev and (date.fromisoformat(ev) - today).days <= 14:
        prio += 1
    if loc in OF_TOWNS:
        prio += 1
    if loc and loc not in OF_TOWNS:
        prio = 1
    return {"title": title, "summary": summary, "summary_en": None, "category": cat, "keywords": kw[:5],
            "priority": prio, "location": loc, "event_date": ev, "confidence": round(conf, 2),
            "notes": "Regelbasiert: Schlüsselwörter, Ortsliste, Datumsmuster"}


PROCESS = {"left": 0, "last": 0.0}  # KI-Budget pro Durchlauf (schont das Gratis-Kontingent für den Chat)
PROCESS_MAX = int(os.environ.get("LLM_PROCESS_MAX", "30"))


def process_budget_reset():
    PROCESS.update(left=PROCESS_MAX, last=0.0)


def process(text):
    """Text -> strukturiertes Ergebnis. Fällt bei Fehlern auf Regeln zurück.
    Pro Durchlauf höchstens LLM_PROCESS_MAX KI-Aufrufe (Standard 30), mit Pause dazwischen; der Rest läuft über Regeln."""
    if LLM_KEY and PROCESS["left"] > 0:
        PROCESS["left"] -= 1
        wait = 4.0 - (time.time() - PROCESS["last"])
        if wait > 0:
            time.sleep(wait)  # max. ~15 Anfragen pro Minute
        PROCESS["last"] = time.time()
        try:
            res, tin, tout = llm(text)
            res["category"] = res.get("category") if res.get("category") in TOPICS else "Events"
            try:
                res["confidence"] = max(0.0, min(1.0, float(res.get("confidence") or 0)))
            except (TypeError, ValueError):
                res["confidence"] = 0.5
            try:
                res["priority"] = max(1, min(5, int(res.get("priority") or 3)))
            except (TypeError, ValueError):
                res["priority"] = 3
            res["engine"] = engine_name()
            return res, tin, tout
        except Exception as e:
            if isinstance(e, LLMError) and e.status == 429:
                PROCESS["left"] = 0  # Kontingent erreicht: Rest dieses Durchlaufs ohne KI, damit der Chat weiter funktioniert
            res = rules(text)
            res["engine"] = f"Regelbasiert (KI-Fehler: {('HTTP ' + str(e.status) + ', ' + e.hint) if isinstance(e, LLMError) else type(e).__name__})"
            return res, 0, 0
    res = rules(text)
    res["engine"] = engine_name()
    return res, 0, 0


def answer(question, items):
    """Frag die Region: Antwort NUR aus den gefundenen Inhalten (RAG)."""
    if not items:
        return None
    if not LLM_KEY:
        return None
    ctx = "\n".join(f"[{i+1}] {it['title']} ({it.get('event_date') or ''}, {it.get('location') or ''}): {it.get('summary')} Quelle: {it.get('source')}"
                    for i, it in enumerate(items))
    p = ("Beantworte die Frage kurz auf Deutsch, NUR mit Informationen aus diesen Einträgen. "
         "Nenne bei jeder Aussage die Nummer in eckigen Klammern, z. B. [2]. Wenn die Einträge die Frage nicht beantworten, sag das.\n\n"
         f"Einträge:\n{ctx}\n\nFrage: {question}")
    try:
        return chat([{"role": "user", "content": p}], json_mode=False, timeout=60)[0]
    except Exception:
        return None


# ---------------- Websuche nur auf vertrauenswürdigen Seiten (Google-Suche über Gemini) ----------------
with open(os.path.join(os.path.dirname(__file__), "trusted.json"), encoding="utf-8") as _f:
    TRUSTED = json.load(_f)
WEB_SEARCH = os.environ.get("WEB_SEARCH", "1") == "1"


def _domain_ok(host_or_url, domains):
    h = (host_or_url or "").lower().replace("https://", "").replace("http://", "").split("/")[0].removeprefix("www.")
    full = (host_or_url or "").lower().replace("https://", "").replace("http://", "").removeprefix("www.")
    for d in domains:
        base = d.split("/")[0]
        if "/" in d:
            if full.startswith(d):
                return d
        elif h == base or h.endswith("." + base):
            return d
    return None


def _real_url(uri):
    """Google liefert bei der Websuche Umleitungs-Links (vertexaisearch…/grounding-api-redirect/…).
    Wir lösen sie einmal auf, damit der Link direkt auf die echte Seite zeigt und wir die Domain sicher prüfen können."""
    if "grounding-api-redirect" not in (uri or ""):
        return uri
    try:
        for _ in range(3):
            r = httpx.get(uri, follow_redirects=False, timeout=6, headers={"User-Agent": "Mozilla/5.0 (Oberfranken-Prototyp)"})
            loc = r.headers.get("location")
            if r.status_code in (301, 302, 303, 307, 308) and loc:
                uri = loc
                if "grounding-api-redirect" not in uri:
                    return uri
            else:
                break
    except Exception:
        pass
    return None


def _page_title(url):
    """Titel der Zielseite für die Quellenangabe (kurz, ohne Seitennamen-Anhang)."""
    try:
        r = httpx.get(url, follow_redirects=True, timeout=6, headers={"User-Agent": "Mozilla/5.0 (Oberfranken-Prototyp)"})
        m = re.search(r"<title[^>]*>(.*?)</title>", r.text[:60000], re.S | re.I)
        if m:
            import html as _h
            t = re.sub(r"\s+", " ", _h.unescape(m.group(1))).strip()
            return t[:120]
    except Exception:
        pass
    return ""


GROUNDING = {"off_until": 0, "why": ""}


def grounding_ok():
    return time.time() >= GROUNDING["off_until"]


def grounding_off(why, hours=1):
    """Google-Suche hat kein Kontingent (429) oder ist nicht freigeschaltet (403): eine Stunde lang nicht mehr versuchen."""
    GROUNDING.update(off_until=time.time() + hours * 3600, why=why)


def site_answer(question, lang="de"):
    """Antwort aus unserer eigenen Suche auf den geprüften Seiten (siehe sitesearch.py). Gibt (text, quellen) zurück."""
    from concurrent.futures import ThreadPoolExecutor
    from . import sitesearch
    if not LLM_KEY:
        return None, []
    hits = sitesearch.find(question, limit=5)
    if not hits:
        return None, []
    with ThreadPoolExecutor(5) as ex:
        texts = list(ex.map(lambda h: sitesearch.page_text(h["url"]), hits))
    docs = [(h, t, x) for h, (t, x) in zip(hits, texts) if len(x) > 200]
    if not docs:
        return None, []
    block = "\n\n".join(f"[{n}] {t or h['url']}\nAdresse: {h['url']}\n{x}" for n, (h, t, x) in enumerate(docs, 1))
    sysmsg = ("Du bist der KI-Begleiter der Plattform „oberfranken“. Beantworte die Frage auf " + ("Englisch" if lang == "en" else "Deutsch") +
              " in höchstens 4 kurzen Sätzen, NUR mit Informationen aus den nummerierten Seiten unten. Erfinde nichts. "
              'Antworte als JSON: {"antwort": "...", "quellen": [Nummern der genutzten Seiten]}. '
              'Steht die Antwort in keiner Seite, antworte genau {"antwort": "NICHTS_GEFUNDEN", "quellen": []}.')
    content, _, _ = chat([{"role": "system", "content": sysmsg}, {"role": "user", "content": f"Frage: {question}\n\nSeiten:\n{block}"}],
                         json_mode=True, max_tokens=700, timeout=40)
    try:
        j = json.loads(re.sub(r"^```(json)?|```$", "", (content or "").strip()).strip())
    except Exception:
        return None, []
    ans = (j.get("antwort") or "").strip()
    used = [int(n) for n in (j.get("quellen") or []) if str(n).isdigit() and 1 <= int(n) <= len(docs)]
    if not ans or "NICHTS_GEFUNDEN" in ans or not used:
        return None, []
    src = []
    for n in dict.fromkeys(used):
        h, t, _ = docs[n - 1]
        src.append({"title": t or h["domain"], "url": h["url"], "domain": urlparse_host(h["url"]), "stufe": h["stufe"]})
    return re.sub(r"\s*\[\d+(,\s*\d+)*\]", "", ans)[:900], src


def urlparse_host(u):
    try:
        return u.split("/")[2].removeprefix("www.")
    except Exception:
        return u


def web_answer(question, domains, stufe, lang="de"):
    """Fragt Gemini mit Google-Suche. Behalten werden nur Quellen von den erlaubten Seiten.
    Gibt (antwort, quellen) zurück oder (None, []) wenn nichts Passendes gefunden wurde."""
    if not (WEB_SEARCH and LLM_KEY and "generativelanguage" in LLM_BASE):
        return None, []
    root = LLM_BASE.split("/v1beta")[0]
    prompt = ("Du bist der KI-Begleiter der Plattform „oberfranken“ (Region Oberfranken, Bayern). Beantworte die Frage auf " + ("Englisch" if lang == "en" else "Deutsch") + " in höchstens "
              "4 kurzen Sätzen. Suche AUSSCHLIESSLICH auf diesen Webseiten (nutze site:-Suchen): " + ", ".join(domains[:30]) + ". "
              "Verwende nur Informationen, die dort stehen. Wenn diese Seiten nichts dazu enthalten, antworte genau mit: NICHTS_GEFUNDEN.\n\n"
              f"Frage: {question}")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1500}}
    if not AVAILABLE:
        pick_model()
    r, first_err = None, None
    WEB_ATTEMPTS.clear()
    for m in _alts(LLM_MODEL):
        for attempt in (1, 2):  # bei Überlastung einmal kurz warten und nochmal
            r = httpx.post(f"{root}/v1beta/models/{m}:generateContent", headers={"x-goog-api-key": LLM_KEY, "Content-Type": "application/json"},
                           json=body, timeout=45)
            WEB_ATTEMPTS.append((m, r.status_code))
            if r.status_code in (429, 500, 503) and attempt == 1:
                time.sleep(2)
                continue
            break
        if r.status_code < 400:
            break
        if r.status_code != 404 and first_err is None:
            first_err = (r.status_code, r.text)  # aussagekräftigster Fehler (nicht "Modell gibt es nicht")
        if r.status_code not in (404, 429, 500, 503):
            break
    if r is None or r.status_code >= 400:
        st, tx = first_err or ((r.status_code, r.text) if r is not None else (0, ""))
        raise LLMError(st, tx)
    js = r.json()
    cand = (js.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if isinstance(p, dict)).strip()
    u = js.get("usageMetadata") or {}
    USAGE["chat_calls"] += 1
    USAGE["tokens_in"] += u.get("promptTokenCount", 0)
    USAGE["tokens_out"] += u.get("candidatesTokenCount", 0)
    if not text or "NICHTS_GEFUNDEN" in text:
        return None, []
    sources, seen = [], set()
    for ch in ((cand.get("groundingMetadata") or {}).get("groundingChunks", []) or [])[:8]:
        web = ch.get("web") or {}
        uri, title = web.get("uri", ""), web.get("title", "")
        if not _domain_ok(title, domains) and not _domain_ok(uri, domains):
            continue
        real = _real_url(uri)  # echte Adresse der Seite statt Google-Umleitung
        if not real:
            continue
        d = _domain_ok(real, domains)
        if not d or real in seen:  # Zielseite liegt nicht auf einer erlaubten Seite -> verwerfen
            continue
        seen.add(real)
        page = _page_title(real)
        sources.append({"title": page or title or d, "url": real, "domain": real.split("/")[2].removeprefix("www."), "stufe": stufe})
    if not sources:  # Google hat keine der erlaubten Seiten genutzt -> lieber nichts sagen
        return None, []
    text = re.sub(r"\s*\[\d+(,\s*\d+)*\]", "", text)
    return text[:900], sources[:5]
