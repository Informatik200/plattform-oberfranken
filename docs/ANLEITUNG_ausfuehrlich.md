# oberfranken.de – funktionierender Prototyp (HF2 Tools & Technik)

Studienprojekt Hochschule Coburg × BERGWERK. Setzt das Konzept aus der BERGWERK-Präsentation vom 1. Oktober 2026 um:
**Geprüftes regionales Wissen (Team Oberfranken, blau) + KI-Begleiter aus echten Quellen (rot) + „Mein Oberfranken“.**

Alle Inhalte kommen aus **echten, geprüften Quellen** (Behörden, Städte, Landkreise, Hochschulen, Tourismus; Liste in `app/sources.json`). Orte: amtliche Liste aller 214 Gemeinden (Destatis, `app/places.json`). Kein offizielles Angebot, kein echtes Logo.

## Starten

**Noch kein Python? Zuerst Doppelklick auf `install.bat`** (installiert Python 3.12 per winget und alle Pakete).

**Windows: Doppelklick auf `start.bat`.** Die Datei findet Python, legt beim ersten Mal `.env` an, installiert die Pakete (nur beim ersten Start oder wenn sich `requirements.txt` ändert), startet den Server und öffnet den Browser. Fenster schließen = Server aus.

**KI prüfen: Doppelklick auf `test_gemini.bat`.** Prüft `.env`, den Schlüssel und die Verbindung zu Google und sagt auf Deutsch, was zu tun ist.

**Teilen: Doppelklick auf `share.bat`.** Startet den Server, falls er noch nicht läuft, und zeigt den Cloudflare-Link (`https://….trycloudflare.com`). Einmalig nötig: `winget install Cloudflare.cloudflared`. Warnt, wenn noch das Demo-Passwort in `.env` steht.

Manuell (Mac/Linux oder ohne .bat), Voraussetzung Python 3.10 oder neuer:

```bash
pip install -r requirements.txt
python run.py
```

Dann im Browser öffnen:

- Nutzerseite: http://localhost:8000
- Redaktion: http://localhost:8000/admin (Demo-Zugang ist vorausgefüllt)

Beim ersten Start sammelt der Server automatisch alle Quellen ein (dauert wenige Sekunden). Danach läuft alle 60 Minuten ein Durchlauf, oder per Knopf „Alle jetzt abrufen“.

### Echte KI einschalten: Gemini (optional)

1. Kostenlosen Schlüssel holen: https://aistudio.google.com/apikey
2. `.env.example` kopieren und in `.env` umbenennen (Windows: `copy .env.example .env`)
3. In `.env` eintragen: `GEMINI_API_KEY=dein-schluessel` (keine Anführungszeichen nötig)
4. Server neu starten (`py run.py`). Im Fenster steht dann `KI-Begleiter: Gemini`.

Andere Anbieter (Mistral, IONOS) gehen genauso über `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`. Ohne Schlüssel arbeitet alles regelbasiert und kostenlos. Den Schlüssel nie ins Chat, in Teams oder auf GitHub kopieren, nur in `.env`.

### Datenschutz: Cookies und IP-Adressen

- **Keine IP-Speicherung:** kein Zugriffsprotokoll (`access_log=False`), keine IP in der Datenbank. Gegen Missbrauch (zu viele Fragen/Meldungen) wird nur ein Hash aus IP + täglich neuem Zufallsschlüssel im Arbeitsspeicher gehalten, max. 10 Minuten (`app/privacy.py`).
- **Einwilligung:** „Nur notwendige“, „Auswahl speichern“, „Alle akzeptieren“ gleich groß. Notwendig = Auswahl, Region, Mein Oberfranken (nur im Browser). Freiwillig = anonyme Statistik.
- **Anonyme Statistik:** nur nach Einwilligung; gespeichert wird nur `Tag + Ereignis + Anzahl` (Tabelle `stats`), sichtbar in der Redaktion → Übersicht.
- **Region vorschlagen:** Knopf „Meinen Standort verwenden“ berechnet die nächste Region im Browser, nichts wird gesendet.
- **Optional, Region aus der IP schätzen (einmalig, ohne Speichern):** kostenlose Datei „IP to City Lite“ (mmdb) von db-ip.com laden (Lizenz CC BY 4.0, Quelle nennen), `py -m pip install maxminddb`, in `.env` eintragen: `GEOIP_DB=C:\Pfad\dbip-city-lite.mmdb`. Die IP verlässt den Server dafür nicht. Lokal (localhost) gibt es keine Schätzung, nur beim Zugriff über Cloudflare.

## Was die Website kann

**Nutzerseite**
- Startseite im Oberfranken-Look: Wetter für die eigene Region (Open-Meteo), „Hallo …, wie kann ich dir heute helfen?“
- **KI-Begleiter (Chat im Hero), nur für Oberfranken** (`app/agent.py`):
  - erkennt den Tag („am Samstag“, „Wochenende“, „morgen“, „17.10.“) und holt die Wettervorhersage dafür
  - antwortet kurz und zeigt passende Karten aus unseren Inhalten (mit Entfernung und Wetter am Termin)
  - bei Regen + Draußen-Frage: „Falls es regnet: Ideen für drinnen“
  - Folgefragen als Chips („bei Regen?“, „mit Kindern?“, „in der Nähe von …“)
  - „Als Tagesplan speichern“ → erscheint in Mein Oberfranken
  - ehrlich: findet er nichts, sagt er das und verlinkt die offiziellen Seiten; Fragen zu anderen Regionen lenkt er freundlich zurück
  - 👍/👎: bei 👎 landet die Frage anonym in Redaktion → Meldungen; Kosten und Feedback stehen in der Übersicht
  - mit Gemini: festes Systemprompt (nur Oberfranken, nur mitgegebene Einträge, nichts erfinden, max. 3 Sätze, JSON); IDs, die das Modell erfindet, werden verworfen; Limit pro Minute (`CHAT_MAX_PER_MIN`)
- Blaue Blöcke (Team Oberfranken) im Wechsel mit roten KI-Blöcken; Schalter im Footer zeigt, was woher kommt
- Regionsseiten (Fichtelgebirge, Frankenwald, Obermain-Jura) mit smarter Suche und Ausflugstipps
- **Mein Oberfranken:** ohne Konto und ohne E-Mail, Profil nur im Browser, Merkliste, optionaler Sync-Code
- „Warum sehe ich das?“ an jeder Empfehlung, „Fehler melden“ an jedem Eintrag

**Redaktion**
- Übersicht: Quellen, neue Inhalte, Prüfwarteschlange, KI-Sicherheit, echte KI-Kosten, erkannte Themen
- Quellen & Durchläufe: jede Quelle einzeln oder alle sofort abrufen, Protokoll jedes Laufs
- KI-Labor: beliebigen Text verarbeiten (Zusammenfassung, Englisch, Thema, Priorität, Ort, Datum) und veröffentlichen
- Prüfung: Original neben KI-Kurzfassung, Freigeben oder Ablehnen
- Kuratierte Inhalte: die blauen Texte direkt bearbeiten (CMS-Ersatz)
- Meldungen von Nutzern, Partner-Ansicht (angezeigt, Klicks zur Quelle, gemerkt)

### Websuche nur auf geprüften Seiten (mit Gemini-Schlüssel)

Findet der KI-Begleiter in unseren Inhalten nichts, fragt er Gemini mit Google-Suche. Erlaubt sind nur die Seiten in `app/trusted.json`
(Stufe 1: Oberfranken – Regierung, Bezirk, IHK, HWK, Hochschulen, Landkreise, Städte, Tourismus, oberfrankenJOBS; Stufe 2: Bayern, Bund, EU).
Antworten ohne Quelle von diesen Seiten werden verworfen; dann sagt der Begleiter ehrlich, dass er nichts gefunden hat. Abschalten: `WEB_SEARCH=0` in `.env`.
Echte Quelle neu: Pressemitteilungen der Regierung von Oberfranken (Methode `listing`, liest die Übersicht und die einzelnen Meldungen, mit robots.txt und Pause).

### Look & Bilder

- **Fotos:** 18 freie Fotos aus Wikimedia Commons (CC BY / BY-SA / CC0) in `static/img/lib/`, Liste mit Autor, Lizenz und Quelle in `app/images.json`, sichtbar unter **Bildnachweis**. Jede Karte bekommt automatisch ein passendes Symbolbild (Schlagwort + Region + Thema), sonst eine gestaltete Karte ohne Foto. Eigene Fotos: Datei nach `static/img/lib/`, Eintrag in `images.json` ergänzen.
- **Hero je nach Wetter:** Sonne = Draußen-Foto + Ausflugs-Chips, Regen = Drinnen-Foto + Ideen für drinnen. Zum Vorführen: `http://localhost:8000/?wetter=regen` bzw. `?wetter=sonne`.
- **Oberfranken-Karte:** 9 Regionen klickbar, Wetter heute, rote Punkte = Termine am Wochenende (Grenzen © OpenStreetMap, `static/oberfranken-map.json`).
- **Innovationsort-Block** mit Filtern, **Oberfranken-Offensiv-Footer**, **App-Leiste** unten auf dem Handy, sanftes Einblenden, Lade-Skelett, Link-Vorschau (`static/og.jpg`) für Teams/WhatsApp.

## Wo steht welcher Punkt aus dem Projektauftrag (HF2)?

| Punkt | Datei |
|---|---|
| RSS-Feeds, APIs, Webcrawler, strukturierte Daten (schema.org) | `app/collect.py` |
| Open Data (Orte → Koordinaten, Wetter) | `app/collect.py` (`geocode`), `app/main.py` (`/api/weather`) |
| LLMs, Zusammenfassung/Übertragung, Kategorisierung, Priorisierung, Orte und Zeitpunkte | `app/ai.py` |
| KI-Begleiter / Chat (RAG + Wetter + Folgefragen) | `app/agent.py`, `/api/ask` in `app/main.py` |
| Themen erkennen | `app/main.py` (`trends` in der Übersicht) |
| Empfehlungssystem, personalisierte Startseite | `app/main.py` (`score`, `/api/feed`), `static/app.js` |
| Fehler erkennen, menschliche Kontrolle | `app/pipeline.py` (`checks`), Redaktion → Prüfung |
| Datenschutz | Profil nur in `localStorage`, Server speichert nichts Persönliches |
| Urheberrecht (§ 44b UrhG) | Crawler prüft `robots.txt` (`allowed_by_robots`) |

## Aufbau

```
Quellen (RSS · JSON-LD · API · Crawler)  →  collect.py  →  einheitliches Format
   →  ai.py (LLM oder Regeln)  →  pipeline.py (Duplikate, Prüfregeln)  →  SQLite (data.db)
   →  main.py (API)  →  static/ (Nutzerseite + Redaktion)
```

Neue Quelle hinzufügen: Eintrag in `app/sources.json` (Methode `rss`, `jsonld`, `api` oder `crawler`, URL), Server neu starten.

## Grenzen des Prototyps

- Noch nicht alle Landkreise mit eigener Terminquelle (Forchheim, Lichtenfels, Bamberg-Termine fehlen)
- Passkey und Zwei-Faktor sind angedeutet, nicht echt umgesetzt
- SQLite statt PostgreSQL; für den Pilot reicht das, später PostgreSQL + pgvector
