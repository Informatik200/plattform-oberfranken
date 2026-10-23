"""Eigene Suche auf den geprüften Seiten (ohne Google-Suche, ohne Zusatzkosten).

So funktioniert es:
1. Beim Start lesen wir im Hintergrund die Sitemaps der geprüften Seiten (Liste in trusted.json).
   Daraus entsteht ein kleines Verzeichnis: Adresse + Wörter aus der Adresse. Es wird in data/site_index.json
   gespeichert und alle 7 Tage erneuert. robots.txt wird beachtet.
2. Bei einer Frage suchen wir passende Seiten in diesem Verzeichnis, laden die besten 4 und geben deren Text
   an Gemini. Gemini darf nur daraus antworten und muss die Quelle nennen. Steht dort nichts: „nichts gefunden“.
"""
import json, os, re, threading, time, gzip
from urllib.parse import urlparse, urljoin
from urllib import robotparser
from xml.etree import ElementTree as ET
import httpx
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
INDEX_FILE = os.path.join(DATA, "site_index.json")
UA = "Mozilla/5.0 (compatible; Oberfranken-Prototyp/1.0; Studienprojekt Hochschule Coburg)"
MAX_PER_SITE, MAX_SUBMAPS, MAX_AGE = 4000, 8, 7 * 86400
SKIP = re.compile(r"\.(pdf|jpe?g|png|gif|svg|zip|docx?|xlsx?|pptx?|mp4|mp3)$|/(impressum|datenschutz|barrierefreiheit|login|suche|search|sitemap|kontakt|newsletter|cookie)", re.I)
STOP = set("der die das und oder ein eine einer eines einem einen in im am an auf aus bei mit nach von vom zu zum zur für fuer ist sind was wie wo wann welche welcher welches gibt es ich du wir ihr sie man kann können kannst mein meine dein deine oberfranken bitte mir mich uns auch noch nur mehr sehr über ueber de html htm php index aspx www seite seiten startseite hat haben hatte viele viel wer wieso warum weshalb geben bekomme brauche muss möchte moechte gerne heute details artikel news aktuelles".split())

INDEX = {"built": 0, "pages": []}   # pages: [url, domain, stufe, "wörter aus adresse"]
STATUS = {"state": "leer", "sites": 0, "pages": 0, "errors": []}
_lock = threading.Lock()


def _norm(s):
    s = s.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return s


def _words(s):
    return [w for w in re.findall(r"[a-z0-9]{3,}", _norm(s)) if w not in STOP]


def _get(client, url):
    r = client.get(url, timeout=15)
    if r.status_code != 200:
        return None
    body = r.content
    if url.endswith(".gz") or body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except Exception:
            pass
    return body


def _locs(xml):
    try:
        root = ET.fromstring(xml)
    except Exception:
        return [], []
    tag = root.tag.split("}")[-1]
    locs = [e.text.strip() for e in root.iter() if e.tag.split("}")[-1] == "loc" and e.text]
    return (locs, []) if tag == "sitemapindex" else ([], locs)


def _site(client, entry, stufe):
    """Liest die Sitemap(s) einer Seite. entry kann eine Domain oder Domain/Pfad sein (z. B. ihk.de/coburg)."""
    host = entry.split("/")[0]
    prefix = entry[len(host):]  # z. B. "/coburg"
    base = None
    for cand in (f"https://www.{host}", f"https://{host}"):
        try:
            r = client.get(cand + "/robots.txt", timeout=10)
            if r.status_code < 500:
                fu = urlparse(str(r.url))
                base = f"{fu.scheme}://{fu.netloc}"
                robots_txt = r.text if r.status_code == 200 else ""
                break
        except Exception:
            continue
    if not base:
        return []
    rp = robotparser.RobotFileParser()
    rp.parse(robots_txt.splitlines())
    maps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots_txt) or [base + "/sitemap.xml", base + "/sitemap_index.xml", base + "/wp-sitemap.xml"]
    if prefix:
        maps = [base + prefix + "/sitemap.xml"] + maps
    pages, seen_maps, todo = [], set(), list(maps)
    while todo and len(seen_maps) < MAX_SUBMAPS + 3 and len(pages) < MAX_PER_SITE:
        m = todo.pop(0)
        if m in seen_maps:
            continue
        seen_maps.add(m)
        try:
            xml = _get(client, m)
        except Exception:
            continue
        if not xml:
            continue
        subs, urls = _locs(xml)
        todo.extend(subs[:MAX_SUBMAPS])
        for u in urls:
            p = urlparse(u)
            h = p.netloc.lower().removeprefix("www.")
            if h != host.removeprefix("www.") and not h.endswith("." + host):
                continue
            if prefix and not p.path.startswith(prefix):
                continue
            if SKIP.search(p.path) or not rp.can_fetch(UA, u):
                continue
            pages.append([u, entry, stufe, " ".join(_words(p.path))])
            if len(pages) >= MAX_PER_SITE:
                break
    if not pages:
        pages = _crawl(client, base, entry, host, prefix, stufe, rp)
    return pages


def _crawl(client, base, entry, host, prefix, stufe, rp, max_pages=600, max_fetch=25):
    """Seite ohne Sitemap: Links der Startseite und der wichtigsten Unterseiten einsammeln (Linktext zählt mit)."""
    start = base + (prefix or "/")
    found, queue, fetched = {}, [start], 0
    while queue and fetched < max_fetch and len(found) < max_pages:
        url = queue.pop(0)
        try:
            r = client.get(url, timeout=12)
        except Exception:
            continue
        fetched += 1
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            u = urljoin(str(r.url), a["href"]).split("#")[0]
            p = urlparse(u)
            h = p.netloc.lower().removeprefix("www.")
            if p.scheme not in ("http", "https") or (h != host.removeprefix("www.") and not h.endswith("." + host)):
                continue
            if (prefix and not p.path.startswith(prefix)) or SKIP.search(p.path) or u in found or not rp.can_fetch(UA, u):
                continue
            label = re.sub(r"\s+", " ", a.get_text(" ")).strip()[:80]
            found[u] = " ".join(dict.fromkeys(_words(p.path) + _words(label)))
            if fetched < max_fetch and len(queue) < 60 and p.path.count("/") <= 3:
                queue.append(u)
        time.sleep(0.4)
    return [[u, entry, stufe, w] for u, w in found.items() if w]


def build(trusted, force=False):
    """Baut das Verzeichnis (im Hintergrund aufrufen). Nutzt die gespeicherte Version, wenn sie jünger als 7 Tage ist."""
    with _lock:
        if STATUS["state"] == "baut":
            return
        STATUS["state"] = "baut"
    try:
        if not force and os.path.exists(INDEX_FILE):
            try:
                old = json.load(open(INDEX_FILE, encoding="utf-8"))
                if old.get("pages"):
                    INDEX.update(old)  # alte Version sofort nutzen, auch während der Erneuerung
                    STATUS.update(pages=len(old["pages"]), sites=len({p[1] for p in old["pages"]}))
                    if time.time() - old.get("built", 0) < MAX_AGE:
                        STATUS["state"] = "bereit"
                        return
            except Exception:
                pass
        pages, errors = [], []
        with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as client:
            for key, stufe in (("stufe1_oberfranken", "Stufe 1: Oberfranken"), ("stufe2_bayern_bund_eu", "Stufe 2: Bayern, Bund, EU")):
                for entry in trusted.get(key, []):
                    try:
                        got = _site(client, entry, stufe)
                        pages += got
                        if not got:
                            errors.append(entry)
                    except Exception:
                        errors.append(entry)
                    time.sleep(0.3)
        INDEX.update(built=time.time(), pages=pages)
        os.makedirs(DATA, exist_ok=True)
        json.dump(INDEX, open(INDEX_FILE, "w", encoding="utf-8"))
        STATUS.update(state="bereit", pages=len(pages), sites=len({p[1] for p in pages}), errors=errors)
        print(f"[Suche] Verzeichnis der geprüften Seiten: {len(pages)} Seiten von {STATUS['sites']} Websites.")
    finally:
        if STATUS["state"] == "baut":
            STATUS["state"] = "fehler"


def start(trusted):
    threading.Thread(target=build, args=(trusted,), daemon=True).start()


_DF = {"n": 0, "df": {}}
TOWNS = {"bamberg", "bayreuth", "coburg", "hof", "forchheim", "kronach", "kulmbach", "lichtenfels", "wunsiedel"}


def _idf(word):
    """Seltene Wörter zählen mehr („Müllabfuhr“ statt „Bayreuth“)."""
    import math
    if _DF["n"] != len(INDEX["pages"]):
        df = {}
        for p in INDEX["pages"]:
            for w in set(p[3].split()):
                df[w] = df.get(w, 0) + 1
        _DF.update(n=len(INDEX["pages"]), df=df)
    n = _DF["n"] or 1
    d = _DF["df"].get(word)
    if d is None:  # Wortstamm: Summe ähnlicher Wörter grob schätzen
        d = 50
    return math.log(1 + n / (1 + d))


def find(question, limit=4):
    """Beste Seiten zur Frage (Wörter in Adresse/Linktext, seltene Wörter zählen mehr). Stufe 1 zählt etwas mehr."""
    q = list(dict.fromkeys(_words(question)))
    if not q or not INDEX["pages"]:
        return []
    weights = {t: _idf(t) for t in q}
    places = set(q) & TOWNS
    scored = []
    for url, dom, stufe, words in INDEX["pages"]:
        ws = words.split()
        s, hits = 0.0, 0
        for t in q:
            stem = t[:max(4, len(t) - 2)]
            if t in ws:
                s += weights[t]; hits += 1
            elif any(w.startswith(stem) or (len(w) > 5 and w in t) for w in ws):
                s += weights[t] * 0.7; hits += 1
            elif len(t) >= 6 and any(len(w) >= 6 and w[:5] == t[:5] for w in ws):  # Wanderwege ~ wandern
                s += weights[t] * 0.35
        if s:
            s *= 1 + 0.25 * (hits - 1)          # mehrere Fragewörter getroffen -> besser
            s += 0.8 if stufe.startswith("Stufe 1") else 0
            if places:  # Frage nennt einen Ort: Websites dieses Ortes vor, Websites anderer Orte zurück
                dparts = set(dom.replace(".", " ").replace("-", " ").replace("/", " ").split())
                if dparts & places:
                    s *= 1.4
                elif dparts & TOWNS and not (places & set(ws)):
                    s *= 0.45
            s -= len(ws) * 0.04              # kurze, genaue Adressen bevorzugen
            scored.append((s, url, dom, stufe))
    scored.sort(key=lambda x: -x[0])
    out, per = [], {}
    for s, url, dom, stufe in scored:
        if per.get(dom, 0) >= 2:
            continue
        per[dom] = per.get(dom, 0) + 1
        out.append({"url": url, "domain": dom, "stufe": stufe, "score": s})
        if len(out) >= limit:
            break
    return out


def page_text(url, max_chars=3500):
    """Lädt eine Seite und gibt Titel + Haupttext zurück."""
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, follow_redirects=True, timeout=12)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", "html"):
            return "", ""
        soup = BeautifulSoup(r.text, "html.parser")
        title = re.sub(r"\s+", " ", soup.title.get_text()).strip()[:120] if soup.title else ""
        for t in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"]):
            t.decompose()
        main = soup.find("main") or soup.find("article") or soup.body or soup
        text = re.sub(r"\s+", " ", main.get_text(" ")).strip()
        return title, text[:max_chars]
    except Exception:
        return "", ""
