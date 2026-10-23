@echo off
title Oberfranken Prototyp - Teilen per Cloudflare
cd /d "%~dp0"

rem --- Server muss laufen ---
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if errorlevel 1 (
  echo  Der Server laeuft noch nicht. Er wird jetzt in einem eigenen Fenster gestartet ...
  start "Oberfranken Prototyp - Server" "%~dp0start.bat"
  timeout /t 8 >nul
)

rem --- cloudflared vorhanden? ---
where cloudflared >nul 2>nul
if errorlevel 1 (
  echo  [FEHLER] cloudflared ist nicht installiert.
  echo  Einmal installieren:  winget install Cloudflare.cloudflared
  echo  Danach dieses Fenster schliessen und share.bat erneut doppelklicken.
  pause
  exit /b 1
)

rem --- Warnung bei Demo-Passwort ---
findstr /c:"ADMIN_PASSWORD=demo1234" ".env" >nul 2>nul
if not errorlevel 1 (
  echo  [ACHTUNG] In .env steht noch das Demo-Passwort demo1234.
  echo  Vor dem Teilen bitte ADMIN_PASSWORD in .env aendern und den Server neu starten.
  echo.
)

echo  Link wird erstellt, bitte ca. 10 Sekunden warten ...
echo  Den Link mit https://....trycloudflare.com kopieren und teilen.
echo  Zum Beenden dieses Fenster schliessen. Der Link funktioniert dann nicht mehr.
echo.
cloudflared tunnel --url http://localhost:8000 2>&1 | findstr /i "trycloudflare.com"
pause
