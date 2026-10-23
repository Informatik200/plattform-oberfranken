@echo off
title Oberfranken Prototyp - Installation
cd /d "%~dp0"
echo.
echo  Oberfranken Prototyp - Python und Pakete installieren
echo  =====================================================
echo.

rem 1) Python schon da?
set PY=
where py >nul 2>nul && set PY=py
if not defined PY ( where python >nul 2>nul && python --version >nul 2>nul && set PY=python )

if defined PY (
  echo  [OK] Python gefunden:
  %PY% --version
) else (
  echo  Python fehlt. Installiere Python 3.12 mit winget ...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo.
    echo  [!] winget gibt es auf diesem PC nicht.
    echo      Bitte Python 3.12 von https://www.python.org/downloads/ laden
    echo      und beim Installieren "Add python.exe to PATH" anhaken.
    start "" https://www.python.org/downloads/
    pause
    exit /b 1
  )
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo  [!] Installation hat nicht geklappt. Bitte Python von python.org installieren.
    pause
    exit /b 1
  )
  rem Neuer PATH ist erst in einem neuen Fenster aktiv -> Standardpfad direkt probieren
  set PY=py
  where py >nul 2>nul || set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)

echo.
echo  Installiere die Pakete aus requirements.txt ...
"%PY%" -m pip install --upgrade pip >nul 2>nul
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo  [!] Pakete konnten nicht installiert werden. Internet pruefen und nochmal starten.
  echo      Falls Python eben erst installiert wurde: Fenster schliessen und install.bat noch einmal starten.
  pause
  exit /b 1
)
copy /y requirements.txt .installed >nul

if not exist .env (
  if exist .env.example copy .env.example .env >nul
)

echo.
echo  [OK] Fertig. Jetzt start.bat doppelklicken.
echo       Fuer Gemini: den Schluessel in die Datei .env eintragen (GEMINI_API_KEY=...).
echo.
pause
