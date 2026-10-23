"""Englische Ansicht ohne KI: feste Übersetzung der Texte, die unser Server selbst formuliert
(Antworten des Assistenten, „Was passiert im Hintergrund?“, Folgefragen, Tagesplan, „Warum sehe ich das?“).
Inhalte der Quellen (Titel, Beschreibungen) bleiben im Original, außer Gemini liefert eine englische Kurzfassung."""
import re

DAYS = {"Montag": "Monday", "Dienstag": "Tuesday", "Mittwoch": "Wednesday", "Donnerstag": "Thursday", "Freitag": "Friday",
        "Samstag": "Saturday", "Sonntag": "Sunday", "Heute": "Today", "Morgen": "Tomorrow"}
WEATHER = {"überwiegend sonnig": "mostly sunny", "sonnig": "sunny", "teils bewölkt": "partly cloudy", "bewölkt": "cloudy", "Nebel": "fog",
           "Nieselregen": "drizzle", "leichter Regen": "light rain", "starker Regen": "heavy rain", "Regenschauer": "showers", "Regen": "rain",
           "Schneefall": "snow", "Schnee": "snow", "Gewitter": "thunderstorm"}
LABELS = {"am Wochenende": "at the weekend", "heute": "today", "morgen": "tomorrow", "übermorgen": "the day after tomorrow"}
CATS = {"Events": "Events", "Tourismus": "Tourism", "Wirtschaft": "Business", "Wissenschaft": "Science", "Kultur": "Culture", "Region": "Region",
        "Natur": "Nature", "Familie": "Family", "Sport": "Sport"}
RANKS = {"Behörde": "Authority", "Amtliche Stelle": "Official body", "Stadt / Landkreis": "City / district", "Kommune": "City / district",
         "Hochschule": "University", "Hochschule / Kammer": "University / chamber", "Tourismusverband": "Tourism board", "Tourismus": "Tourism",
         "Partner": "Partner", "Partner / Unternehmen": "Partner / company", "Kammer / Verband": "Chamber / association"}


def _w(s):
    for de, en in sorted(WEATHER.items(), key=lambda x: -len(x[0])):
        s = re.sub(r"\b" + re.escape(de) + r"\b", en, s)
    return s


def _where(s):
    s = s.strip()
    return {"in der Fränkischen Schweiz": "in Franconian Switzerland", "im Fichtelgebirge": "in the Fichtelgebirge",
            "im Frankenwald": "in the Franconian Forest", "in Oberfranken": "in Upper Franconia"}.get(s, s)


def _label(s):
    s = s.strip()
    if s in LABELS:
        return LABELS[s]
    m = re.match(r"am (\w+)", s)
    return "on " + DAYS.get(m.group(1), m.group(1)) if m else s


RULES = [
    (r"^Allgemeine KI-Chatbots wissen viel über die Welt, ich weiß genau, was in Oberfranken los ist\..*$",
     "General AI chatbots know a lot about the world; I know exactly what's going on in Upper Franconia. My events and news come fresh every hour from the region's official websites, every answer has a source with a link, and if nothing is in the sources I say so instead of making something up. I know all 214 places with their own weather. You don't need an account and your questions are not stored. For writing texts or programming, general chatbots are stronger."),
    (r"^Regel: Vergleich$", "Rule: comparison"),
    (r"^Wie wird das Wetter in (.+?)\?$", r"What's the weather like in \1?"),
    (r"^Ich will nach Oberfranken ziehen\. Wo fange ich an\?$", "I want to move to Upper Franconia. Where do I start?"),
    (r"^Welche Förderprogramme gibt es für Gründer\?$", "What funding is there for founders?"),
    (r"^Vergleich: Plattform Oberfranken und allgemeine KI-Chatbots$", "Comparison: Platform Upper Franconia and general AI chatbots"),
    (r"Dazu habe ich in den Inhalten aus Oberfranken nichts Sicheres gefunden\. Schau gern bei den offiziellen Seiten der Region nach\.",
     "I couldn't find anything reliable about that in the content from Upper Franconia. Please check the official websites of the region."),
    # --- Antworten ---
    (r"^Wetter (in .+?|im .+?|in der .+?): (.+? %)\.", lambda m: f"Weather {_where(m.group(1))}: " + _forecast(m.group(2))),
    (r"Bei Regen passt das hier gut, drinnen:", "If it rains, these indoor ideas fit well:"),
    (r"Das ist in der Nähe los:", "Here's what's on nearby:"),
    (r"Die Wettervorhersage \(Open-Meteo\) ist gerade nicht erreichbar\. Versuch es in einer Minute noch einmal\.",
     "The weather forecast (Open-Meteo) is not reachable right now. Please try again in a minute."),
    (r"^Fürs Wochenende habe ich ", "For the weekend I found "), (r"^Für heute habe ich ", "For today I found "),
    (r"^Für morgen habe ich ", "For tomorrow I found "), (r"^Für übermorgen habe ich ", "For the day after tomorrow I found "),
    (r"^Für die nächsten Tage habe ich ", "For the next few days I found "), (r"^Für den (\w+) habe ich ", lambda m: f"For {DAYS.get(m.group(1), m.group(1))} I found "),
    (r"^Dazu habe ich ", "I found "),
    (r"einen passenden Tipp(.*?) gefunden\.", lambda m: f"one matching tip{(' ' + _where(m.group(1))) if m.group(1).strip() else ''}."),
    (r"(\d+) passende Tipps(.*?) gefunden\.", lambda m: f"{m.group(1)} matching tips {_where(m.group(2))}.".replace("  ", " ")),
    (r"(\d+) (Idee|Ideen) für drinnen gefunden, die nächste ist ca\. (\d+) km von (.+?) entfernt\.",
     lambda m: f"{m.group(1)} indoor {'idea' if m.group(2) == 'Idee' else 'ideas'}, the nearest is about {m.group(3)} km from {m.group(4)}."),
    (r"(\d+) (Idee|Ideen) für drinnen gefunden\.", lambda m: f"{m.group(1)} indoor {'idea' if m.group(2) == 'Idee' else 'ideas'}."),
    (r"^(Heute|Morgen|Übermorgen|Am \w+|Dann) ist(.*?) noch nichts eingetragen\. Das ist der nächste Termin:",
     lambda m: f"Nothing is listed {_lead(m.group(1))}{_where(m.group(2)) and ' ' + _where(m.group(2))} yet. This is the next event:"),
    (r"^(Heute|Morgen|Übermorgen|Am \w+|Dann) ist(.*?) noch nichts eingetragen\. Das sind die nächsten (\d+) Termine:",
     lambda m: f"Nothing is listed {_lead(m.group(1))}{_where(m.group(2)) and ' ' + _where(m.group(2))} yet. These are the next {m.group(3)} events:"),
    (r"Achtung, (.+?) ist (.+?) angesagt, darunter findest du deshalb auch Ideen für drinnen\.",
     lambda m: f"Heads-up: {_w(m.group(2))} is forecast {_where(m.group(1))}, so below you'll also find indoor ideas."),
    (r"Achtung, (.+?) ist (.+?) angesagt, plane besser eine Regenjacke ein\.",
     lambda m: f"Heads-up: {_w(m.group(2))} is forecast {_where(m.group(1))}, better bring a rain jacket."),
    (r"Ich bin dein Begleiter für Oberfranken, zu (.+?) kann ich dir leider nichts sagen\. Wie wäre es stattdessen mit einem Ausflug ins Fichtelgebirge oder in den Frankenwald\?",
     lambda m: f"I'm your guide for Upper Franconia, so I can't tell you anything about {m.group(1)}. How about a trip to the Fichtelgebirge or the Franconian Forest instead?"),
    # --- Folgefragen ---
    (r"^Was kann ich (am Wochenende|heute|morgen|übermorgen|am \w+)(.*?) bei Regen drinnen machen\?$",
     lambda m: f"What can I do indoors {_label(m.group(1))}{(' ' + _where(m.group(2))) if m.group(2).strip() else ''} if it rains?"),
    (r"^Was kann ich (am Wochenende|heute|morgen|übermorgen|am \w+)(.*?) mit Kindern machen\?$",
     lambda m: f"What can I do with kids {_label(m.group(1))}{(' ' + _where(m.group(2))) if m.group(2).strip() else ''}?"),
    (r"^Was ist (am Wochenende|heute|morgen|übermorgen|am \w+) in der Nähe von (.+?) los\?$", lambda m: f"What's on near {m.group(2)} {_label(m.group(1))}?"),
    (r"^Was ist (am Wochenende|heute|morgen|übermorgen|am \w+) sonst in Oberfranken los\?$", lambda m: f"What else is on in Upper Franconia {_label(m.group(1))}?"),
    (r"^Was ist (am Wochenende|heute|morgen|übermorgen|am \w+)(.*?) los\?$", lambda m: f"What's on {_label(m.group(1))}{(' ' + _where(m.group(2))) if m.group(2).strip() else ''}?"),
    (r"^Ich möchte am Samstag Fahrrad fahren$", "I'd like to go cycling on Saturday"),
    (r"^Welche Karriere-Termine gibt es in der Nähe von (.+?)\?$", lambda m: f"Which career events are there near {m.group(1)}?"),
    (r"^Wo kann ich in Oberfranken studieren\?$", "Where can I study in Upper Franconia?"),
    (r"^Gibt es Hilfe beim Bewerben\?$", "Is there help with job applications?"),
    (r"^Was kann ich am Wochenende im Frankenwald machen\?$", "What can I do in the Franconian Forest at the weekend?"),
    (r"^Welche Radtouren gibt es in Oberfranken\?$", "Which cycling tours are there in Upper Franconia?"),
    (r"^Was ist heute in Oberfranken los\?$", "What's on in Upper Franconia today?"),
    # --- Was passiert im Hintergrund? ---
    (r"^Frage verstanden: (.+?)\. Sie wird nicht gespeichert\.$", lambda m: f"Question understood: {_label(m.group(1))}. It is not stored."),
    (r"^Frage verstanden\. Sie wird nicht gespeichert\.$", "Question understood. It is not stored."),
    (r"^Gesucht in (\d+) aktuellen Einträgen aus (\d+) geprüften Quellen \(Behörden, Städte, Hochschulen, Tourismus\)\.$",
     r"Searched \1 current entries from \2 verified sources (authorities, cities, universities, tourism)."),
    (r"^(\d+) Treffer ausgewählt nach Datum, Ort, Interesse und Wetter\. Absender: (.+)\.$",
     lambda m: f"{m.group(1)} results picked by date, place, interest and weather. Senders: {', '.join(RANKS.get(x.strip(), x.strip()) for x in m.group(2).split(','))}."),
    (r"^Wettervorhersage live von Open-Meteo \(Deutscher Wetterdienst u\. a\.\) abgerufen\.$", "Weather forecast fetched live from Open-Meteo (German Weather Service and others)."),
    (r"^Antwort formuliert von unseren Regeln \(ohne KI\)\.$", "Answer written by our rules (no AI)."),
    (r"^Antwort formuliert von Gemini \(KI\) nur aus diesen Treffern\.$", "Answer written by Gemini (AI) from these results only."),
    (r"^Keine passenden Einträge gefunden\.$", "No matching entries found."),
    (r"^In unseren Einträgen stand nichts Passendes, darum wurde nur auf geprüften Seiten gesucht \((eigene Suche|Google-Suche über Gemini)\)\.$",
     lambda m: "Nothing matching in our entries, so only verified websites were searched (" + ("our own search" if m.group(1) == "eigene Suche" else "Google search via Gemini") + ")."),
    (r"^(\d+) Seite\(n\) als Quelle genutzt: (.+)$", r"\1 page(s) used as source: \2"),
    (r"(.+?) \+ eigene Suche auf geprüften Seiten$", r"\1 + own search on verified websites"),
    (r"(.+?) \+ Google-Suche nur auf geprüften Seiten \((.+)\)$", r"\1 + Google search on verified websites only (\2)"),
    # --- Engine-Angaben ---
    (r"^Regelbasiert \(kein API-Schlüssel\)$", "Rule-based (no API key)"),
    (r"^Regel: außerhalb Oberfrankens$", "Rule: outside Upper Franconia"),
    (r"KI-Fehler \((.+?)\), Antwort regelbasiert", r"AI error (\1), rule-based answer"),
    # --- Tagesplan ---
    (r"^Für dich: (.+)$", lambda m: "For you: " + " & ".join(_plan_topic(x) for x in m.group(1).split(" & "))),
    (r"^Zeitbudget · halber Tag$", "Time · half a day"), (r"^Zeitbudget · ein ganzer Tag$", "Time · a full day"),
    (r"^Anreise · Bus und Bahn$", "Travel · bus and train"), (r"^Anreise · flexibel$", "Travel · flexible"),
    (r"^Für deinen (halben|ganzen) Tag passt (.+?): (.+)$", lambda m: f"For your {'half' if m.group(1) == 'halben' else 'full'} day, {m.group(2)} fits: {m.group(3).replace(' und ', ' and ')}"),
    (r"^Plane eine längere Mittagspause in (.+?) ein\. Ein Café oder Gasthaus kannst du nach deinen Vorlieben auswählen\.$",
     r"Plan a longer lunch break in \1. Pick a café or inn you like."),
    (r"^(\d\d) · Pause & genießen$", r"\1 · Break & enjoy"),
    (r"^(\d\d) · Ankommen & entdecken$", r"\1 · Arrive & explore"), (r"^(\d\d) · Den Tag ausklingen lassen$", r"\1 · Wind down the day"),
    (r"^(\d\d) · Zum Abschluss$", r"\1 · To finish"),
    (r"^Lass den Tag mit einem Spaziergang durch (.+?) ausklingen\. Tipps dafür findest du bei den offiziellen Infos der Region\.$",
     r"End the day with a walk through \1. You'll find tips on the region's official information pages."),
    (r"^Noch nichts Passendes$", "Nothing matching yet"),
    (r"^Für diese Auswahl gibt es in den nächsten zwei Wochen keine Einträge\. Probier ein anderes Interesse oder eine andere Region\.$",
     "There are no entries for this choice in the next two weeks. Try another interest or region."),
    (r"^Wetter in (.+?): (-?\d+) °C, (.+)\.$", lambda m: f"Weather in {m.group(1)}: {m.group(2)} °C, {_w(m.group(3))}."),
    (r"^Wetter vorab prüfen \(im Prototyp gerade nicht abrufbar\)\.$", "Check the weather beforehand (not available in the prototype right now)."),
    (r"^Termin „(.+)“: (\d\d)\.(\d\d)\. – Uhrzeit und Anmeldung beim Anbieter prüfen\.$", r"Event “\1”: \2.\3. – check the time and registration with the provider."),
    (r"^Öffnungszeiten und Eintritt beim Anbieter prüfen, die Links führen zur Originalquelle\.$", "Check opening hours and admission with the provider; the links lead to the original source."),
    (r"^Anreise mit Bus und Bahn: Verbindung nach (.+?) und die Rückfahrt in der Fahrplanauskunft prüfen\.$", r"Travelling by bus and train: check the connection to \1 and the return trip in the journey planner."),
    (r"^(\d\d) · (Am Vormittag|Am Nachmittag|Zum Abschluss|Start)$", lambda m: f"{m.group(1)} · " + {"Am Vormittag": "Morning", "Am Nachmittag": "Afternoon", "Zum Abschluss": "To finish", "Start": "Start"}[m.group(2)]),
    # --- Warum sehe ich das? ---
    (r"^\+(\d) dein Thema „(.+?)“$", lambda m: f"+{m.group(1)} your topic “{CATS.get(m.group(2), m.group(2))}”"),
    (r"^\+(\d) in deiner Region (.+)$", r"+\1 in your region \2"),
    (r"^\+(\d) in den nächsten 7 Tagen$", r"+\1 in the next 7 days"),
    (r"^\+(\d) am Wochenende$", r"+\1 at the weekend"),
    (r"^außerhalb deiner Themen, gegen die Filterblase$", "outside your topics, against the filter bubble"),
]
RULES = [(re.compile(p), r) for p, r in RULES]


def _lead(s):
    return {"Heute": "today", "Morgen": "tomorrow", "Übermorgen": "the day after tomorrow", "Dann": "then"}.get(s, "on " + DAYS.get(s[3:], s[3:]) if s.startswith("Am ") else s)


def _plan_topic(s):
    return {"Kultur & Stadt": "Culture & city", "Natur & Ruhe": "Nature & quiet", "Familienzeit": "Family time", "Aktiv & Rad": "Active & cycling", "Natur": "Nature", "Kultur": "Culture", "Stadt": "City", "Familie": "Family", "Genuss": "Food & drink",
            "Sport": "Sport", "Events": "Events", "Tourismus": "Tourism"}.get(s, CATS.get(s, s))


def _forecast(s):
    out = []
    for part in s.rstrip(".").split("; "):
        m = re.match(r"(\w+) (.+?), bis (-?\d+) °C, Regenrisiko (\d+) %", part)
        out.append(f"{DAYS.get(m.group(1), m.group(1))} {_w(m.group(2))}, up to {m.group(3)} °C, {m.group(4)} % chance of rain" if m else part)
    return "; ".join(out) + "."


def sentence_split(text):
    return re.split(r"(?<=[.?!])\s+(?=[A-ZÄÖÜ])", text)


def _apply(sent):
    for rx, rep in RULES:
        sent = rx.sub(rep, sent)
    return sent


def tr(text):
    """Einen von uns formulierten Text übersetzen. Erst als Ganzes, sonst Satz für Satz. Unbekanntes bleibt unverändert."""
    if not text or not isinstance(text, str):
        return text
    whole = _apply(text)
    if whole != text:
        return whole
    return " ".join(_apply(x) for x in sentence_split(text))


def ask_response(res):
    for k in ("answer", "engine", "engine_note"):
        if isinstance(res.get(k), str):
            res[k] = tr(res[k])
    for l in res.get("links") or []:
        if isinstance(l, dict) and isinstance(l.get("title"), str):
            l["title"] = tr(l["title"])
    for k in ("followups", "trace"):
        if isinstance(res.get(k), list):
            res[k] = [tr(x) for x in res[k]]
    for w in [res.get("weather")] + list(res.get("forecast") or []):
        if isinstance(w, dict) and isinstance(w.get("text"), str):
            w["text"] = _w(w["text"])
    for it in list(res.get("items") or []) + list(res.get("alternatives") or []):
        _item(it)
    return res


def _item(it):
    if not isinstance(it, dict):
        return it
    if it.get("summary_en"):
        it["summary"] = it["summary_en"]
    if isinstance(it.get("why"), list):
        it["why"] = [tr(x) for x in it["why"]]
    if it.get("rank_label"):
        it["rank_label"] = RANKS.get(it["rank_label"], it["rank_label"])
    return it


def weather(w):
    if isinstance(w, dict):
        if isinstance(w.get("text"), str):
            w["text"] = _w(w["text"])
        for v in w.values():
            if isinstance(v, dict) and isinstance(v.get("text"), str):
                v["text"] = _w(v["text"])
    return w


def items(lst):
    for it in lst or []:
        _item(it)
    return lst


def plan(p):
    if not isinstance(p, dict):
        return p
    for k in ("title", "intro", "note"):
        if isinstance(p.get(k), str):
            p[k] = tr(p[k])
    if isinstance(p.get("checklist"), list):
        p["checklist"] = [tr(x) for x in p["checklist"]]
    if isinstance(p.get("meta"), list):
        p["meta"] = [tr(x) for x in p["meta"]]
    for st in p.get("steps") or []:
        for k in ("t", "text"):
            if isinstance(st.get(k), str):
                st[k] = tr(st[k])
        _item(st.get("item"))
    return p
