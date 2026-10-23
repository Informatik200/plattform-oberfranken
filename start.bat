@echo off
title Oberfranken Prototyp - Server
cd /d "%~dp0"

echo.
echo  ==========================================
echo    Oberfranken Prototyp wird gestartet ...
echo  ==========================================
echo.

rem --- 1. Python finden ---
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo  [FEHLER] Python wurde nicht gefunden.
  echo  Bitte einmal installieren:  winget install Python.Python.3.12
  echo  Danach dieses Fenster schliessen und start.bat erneut doppelklicken.
  echo.
  pause
  exit /b 1
)

rem --- 2. Einstellungen anlegen, falls noch keine .env da ist ---
if not exist ".env" if exist ".env.example" (
  copy ".env.example" ".env" >nul
  echo  .env angelegt. Fuer echte KI dort GEMINI_API_KEY eintragen.
)

rem --- 3. Pakete nur installieren, wenn noetig (erster Start oder requirements.txt geaendert) ---
fc /b "requirements.txt" ".installed" >nul 2>nul
if errorlevel 1 (
  echo  Pakete werden installiert, das dauert beim ersten Mal 1-2 Minuten ...
  %PY% -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 (
    echo  [FEHLER] Installation fehlgeschlagen. Internetverbindung pruefen.
    pause
    exit /b 1
  )
  copy /y "requirements.txt" ".installed" >nul
)

rem --- 4. Laeuft schon ein (evtl. alter) Server auf Port 8000? Dann beenden, damit die neue Version startet ---
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING"') do (
  echo  Alter Server auf Port 8000 gefunden, wird beendet ...
  taskkill /PID %%p /F >nul 2>nul
)
timeout /t 1 >nul

rem --- 5. Browser nach 4 Sekunden oeffnen, Server starten ---
rem     Chrome oder Edge bevorzugen: nur dort funktioniert die Spracheingabe (Firefox hat keine Spracherkennung)
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 4; $u='http://localhost:8000'; try { Start-Process chrome $u -ErrorAction Stop } catch { try { Start-Process msedge $u -ErrorAction Stop } catch { Start-Process $u } }"

echo  Website:    http://localhost:8000   (am besten in Chrome oder Edge, fuer das Mikrofon)
echo  Redaktion:  http://localhost:8000/admin
echo.
echo  Zum Beenden dieses Fenster schliessen oder Strg+C druecken.
echo.
%PY% run.py

echo.
echo  Server wurde beendet.
pause
