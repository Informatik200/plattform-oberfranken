"""Startet die Plattform: python run.py  →  http://localhost:8000"""
import os
import uvicorn

from app import envfile

if __name__ == "__main__":
    src, _ = envfile.load(".env")
    ki = "LLM (" + os.environ.get("LLM_MODEL", "eigener Anbieter") + ")" if os.environ.get("LLM_API_KEY") else \
        "Gemini" if os.environ.get("GEMINI_API_KEY") else "regelbasiert (kein Schlüssel in .env)"
    print(f"\n  Version:      {envfile.VERSION}")
    print(f"  Einstellungen: {src or 'keine .env gefunden'}")
    print(f"  KI-Begleiter: {ki}")
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY"):
        print(f"  Schlüssel:    {envfile.key_info()}")
    print("\n  Nutzerseite:  http://localhost:8000\n  Redaktion:    http://localhost:8000/admin\n")
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8000")),
                access_log=False)  # kein Zugriffsprotokoll: IP-Adressen landen nirgends
