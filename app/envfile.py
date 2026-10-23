"""Liest .env robust ein (auch mit Windows-BOM, Anführungszeichen, Leerzeichen). Werte aus .env haben Vorrang."""
import os

VERSION = "2026-10-13b"


def load(path=".env"):
    found = {}
    for name in (path, path + ".txt"):  # Windows speichert manchmal als .env.txt
        if os.path.exists(name):
            with open(name, encoding="utf-8-sig", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'").strip()
                        if v:
                            os.environ[k] = v  # .env gewinnt gegen alte Systemvariablen
                            found[k] = v
            return name, found
    return None, found


def key_info():
    k = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
    if not k:
        return "kein Schlüssel"
    warn = []
    if " " in k:
        warn.append("enthält Leerzeichen")
    return f"{k[:4]}…{k[-2:]} ({len(k)} Zeichen)" + (" – ACHTUNG: " + ", ".join(warn) if warn else "")
