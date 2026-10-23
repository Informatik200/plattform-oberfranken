"""Prüft den Gemini-Schlüssel Schritt für Schritt und sagt auf Deutsch, was nicht stimmt.
Start: Doppelklick auf test_gemini.bat (oder: py check_gemini.py)"""
import json
import os
import sys

from app import envfile

print(f"\n Gemini-Test · Version {envfile.VERSION}\n")
src, vals = envfile.load(".env")
print(f" 1. Einstellungsdatei: {src or 'NICHT GEFUNDEN'}")
if not src:
    print("    -> .env muss im selben Ordner wie start.bat liegen (nicht env.txt, nicht in Unterordner).")
    sys.exit(1)
key = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
print(f" 2. Schlüssel: {envfile.key_info()}")
if not key:
    print("    -> In .env die Zeile GEMINI_API_KEY=... ausfüllen und speichern.")
    sys.exit(1)
try:
    import httpx
except ImportError:
    print("    -> Pakete fehlen. Erst start.bat einmal ausführen.")
    sys.exit(1)
from app import ai  # liest Adresse und Modell wie der Server
print(f" 3. Adresse: {ai.LLM_BASE}\n    Modell:  {ai.LLM_MODEL}")
h = {"Authorization": f"Bearer {key}"}
try:
    r = httpx.get(f"{ai.LLM_BASE}/models", headers=h, timeout=20)
    if r.status_code == 200:
        ids = [m.get("id", "").replace("models/", "") for m in r.json().get("data", [])]
        flash = [i for i in ids if "flash" in i][:8]
        print(f" 4. Verbindung + Schlüssel: OK ({len(ids)} Modelle verfügbar)")
        print(f"    Flash-Modelle: {', '.join(flash) or '-'}")
        if ids and ai.LLM_MODEL not in ids:
            old = ai.LLM_MODEL
            ai.pick_model()
            print(f"    {old} gibt es für diesen Schlüssel nicht. Der Server nimmt automatisch: {ai.LLM_MODEL}")
    else:
        e = ai.LLMError(r.status_code, r.text)
        print(f" 4. Verbindung: FEHLER {e.status} – {e.hint}\n    Google sagt: {e.detail}")
except Exception as ex:
    print(f" 4. Verbindung: keine Antwort von Google ({type(ex).__name__}). Internet/Firewall/VPN prüfen.")
try:
    content, tin, tout = ai.chat([{"role": "user", "content": 'Antworte nur mit JSON: {"ok": true, "gruss": "Hallo Oberfranken"}'}],
                                 json_mode=True, max_tokens=300, timeout=30)
    print(f" 5. Testfrage: OK – Antwort: {(content or '').strip()[:80]}  (Modell: {ai.LLM_MODEL})")
    try:
        txt, src = ai.web_answer("Wo hat die Regierung von Oberfranken ihren Sitz?", ai.TRUSTED["stufe1_oberfranken"], "Stufe 1")
        print(f" 6. Websuche (geprüfte Seiten): {'OK – ' + txt[:70] + ' | Quelle: ' + src[0]['domain'] if txt else 'keine Antwort mit erlaubter Quelle (der Begleiter sagt dann ehrlich: nichts gefunden)'}")
    except ai.LLMError as e:
        print(f" 6. Websuche: FEHLER {e.status} – {e.hint}. Der Chat funktioniert trotzdem, nur ohne Websuche.\n    Google sagt: {e.detail}")
        print("    Versuche: " + ", ".join(f"{m} → {s}" for m, s in ai.WEB_ATTEMPTS))
        if e.status == 429:
            print("    Tipp: Das Gratis-Kontingent für die Google-Suche ist für heute/diese Minute aufgebraucht. Später nochmal testen.")
    try:
        from app import sitesearch
        sitesearch.build(ai.TRUSTED)  # nutzt das mitgelieferte Verzeichnis (data/site_index.json)
        q = "Welche Förderprogramme gibt es für Gründer in Oberfranken?"
        txt, src = ai.site_answer(q)
        print(f" 7. Eigene Suche auf geprüften Seiten ({sitesearch.STATUS['pages']} Seiten): " +
              (f"OK – {txt[:70]}…\n    Quelle: {src[0]['url'][:90]}" if txt else "keine passende Seite gefunden"))
        print("    (Springt automatisch ein, wenn die Google-Suche kein Kontingent hat.)")
    except ai.LLMError as e:
        print(f" 7. Eigene Suche: FEHLER {e.status} – {e.hint}")
    except Exception as e:
        print(f" 7. Eigene Suche: nicht möglich ({type(e).__name__}: {e})")
    print("\n ERGEBNIS: Gemini funktioniert. start.bat neu starten (altes Fenster vorher schließen).\n")
except ai.LLMError as e:
    print(f" 5. Testfrage: FEHLER {e.status} – {e.hint}\n    Google sagt: {e.detail}")
    tips = {400: "Schlüssel neu aus https://aistudio.google.com/apikey kopieren (komplett, ohne Leerzeichen).",
            401: "Schlüssel ungültig: neu kopieren oder neuen Schlüssel erstellen.",
            403: "Neuen Schlüssel in AI Studio erstellen; bei Uni-/Firmenkonto evtl. privates Google-Konto nutzen.",
            404: "In .env LLM_MODEL=gemini-flash-latest (oder ein Modell aus Schritt 4) ergänzen.",
            429: "Gratis-Kontingent erschöpft: 1 Minute warten oder Limits in AI Studio prüfen.",
            503: "Google ist gerade bei allen Flash-Modellen überlastet. In 1–2 Minuten nochmal testen; der Server probiert automatisch andere Modelle."}
    print("\n ERGEBNIS: " + tips.get(e.status, "Meldung oben an Claude schicken (ohne den Schlüssel).") + "\n")
except Exception as ex:
    print(f" 5. Testfrage: {type(ex).__name__}: {ex}\n")
