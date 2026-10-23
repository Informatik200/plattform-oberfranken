"""Datenschutz-Bausteine: IP nur kurz im Arbeitsspeicher, nie in Datenbank oder Logdatei.

- client_ip(): IP der Anfrage (hinter Cloudflare: Header CF-Connecting-IP)
- rate_ok(): Schutz vor Missbrauch. Merkt sich nur einen Hash (IP + Tagesschlüssel) im RAM,
  max. 10 Minuten; der Tagesschlüssel wechselt täglich, ein Neustart löscht alles.
- region_from_ip(): ungefähre Region aus der IP, NUR wenn eine lokale GeoIP-Datei vorhanden ist
  (z. B. DB-IP „IP to City Lite“, CC BY 4.0). Die IP verlässt den Server dafür nicht und wird verworfen.
"""
import hashlib
import ipaddress
import os
import secrets
import threading
import time
from datetime import date

from .agent import km
from .collect import COORDS

GEOIP_DB = os.environ.get("GEOIP_DB", "")
_reader = None
_reader_err = None
if GEOIP_DB:
    try:
        import maxminddb  # optional: pip install maxminddb
        _reader = maxminddb.open_database(GEOIP_DB)
    except Exception as e:  # Datei fehlt oder Paket nicht installiert -> Funktion aus
        _reader_err = f"{type(e).__name__}: {e}"


def client_ip(request):
    """IP der Anfrage. Die Kopfzeilen von Cloudflare (CF-Connecting-IP / X-Forwarded-For) gelten NUR, wenn die
    Anfrage vom eigenen Rechner kommt (der Cloudflare-Tunnel läuft lokal). Sonst könnte jeder sie fälschen
    und den Missbrauchsschutz umgehen."""
    peer = request.client.host if request.client else ""
    try:
        local = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        local = False
    if local:
        h = request.headers
        fwd = h.get("cf-connecting-ip") or (h.get("x-forwarded-for") or "").split(",")[0].strip()
        if fwd:
            return fwd
    return peer


def is_public(ip):
    try:
        a = ipaddress.ip_address(ip)
        return not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved)
    except ValueError:
        return False


# ---------- Missbrauchsschutz ohne Speicherung ----------
_salt = {"day": None, "key": b""}
_hits = {}
_lock = threading.Lock()


def _anon(ip):
    today = date.today().isoformat()
    if _salt["day"] != today:  # täglich neuer Zufallsschlüssel -> Hashes von gestern sind wertlos
        _salt.update(day=today, key=secrets.token_bytes(16))
        _hits.clear()
    return hashlib.sha256(_salt["key"] + ip.encode()).hexdigest()[:16]


def rate_ok(ip, bucket, limit, window=600):
    """True, wenn diese Verbindung im Zeitfenster noch unter dem Limit liegt."""
    now = time.time()
    with _lock:
        k = (bucket, _anon(ip))
        ts = [t for t in _hits.get(k, []) if now - t < window]
        if len(ts) >= limit:
            _hits[k] = ts
            return False
        ts.append(now)
        _hits[k] = ts
        # aufräumen
        if len(_hits) > 5000:
            for kk in [kk for kk, v in _hits.items() if not v or now - v[-1] > window]:
                _hits.pop(kk, None)
        return True


# ---------- Region aus IP (einmalig, nicht gespeichert) ----------
def nearest_region(lat, lon, max_km=40):
    best = min(COORDS, key=lambda r: km((lat, lon), COORDS[r]))
    d = km((lat, lon), COORDS[best])
    return (best, d) if d is not None and d <= max_km else (None, d)


def region_from_ip(ip):
    if not _reader:
        return None, ("keine GeoIP-Datei eingerichtet" if not _reader_err else "GeoIP nicht verfügbar")
    if not is_public(ip):
        return None, "lokale Verbindung, keine Schätzung möglich"
    try:
        rec = _reader.get(ip) or {}
        loc = rec.get("location") or {}
        lat, lon = loc.get("latitude"), loc.get("longitude")
        if lat is None or lon is None:
            return None, "Ort unbekannt"
        reg, _ = nearest_region(lat, lon)
        return reg, ("ungefähr aus der Verbindung geschätzt" if reg else "außerhalb Oberfrankens")
    except Exception:
        return None, "Schätzung fehlgeschlagen"


# ---------- Speicherdauer: was nicht mehr gebraucht wird, wird gelöscht (läuft beim Start und mit jedem Abruf) ----------
RETENTION = [
    # (Tabelle, Bedingung zum Löschen, Klartext für die Datenschutz-Seite)
    ("sync_codes", "created < datetime('now','localtime','-30 days')", "Sync-Codes: nach 30 Tagen gelöscht"),
    ("accounts", "coalesce(updated, created) < datetime('now','localtime','-12 months')", "Konten: 12 Monate nach der letzten Nutzung gelöscht"),
    ("reports", "created < datetime('now','localtime','-12 months')", "Hinweise und Partner-Anfragen: nach 12 Monaten gelöscht"),
    ("stats", "day < date('now','localtime','-13 months')", "Statistik-Summen: nach 13 Monaten gelöscht"),
    ("runs", "started < datetime('now','localtime','-90 days')", "Abruf-Protokoll: nach 90 Tagen gelöscht"),
]


def cleanup():
    from . import db
    n = 0
    for table, cond, _ in RETENTION:
        try:
            before = db.one(f"select count(*) c from {table}")["c"]
            db.exec_(f"delete from {table} where {cond}")
            n += before - db.one(f"select count(*) c from {table}")["c"]
        except Exception:
            pass
    return n
