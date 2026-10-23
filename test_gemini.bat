@echo off
title Oberfranken Prototyp - Gemini-Test
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo  Python wurde nicht gefunden. Erst start.bat ausfuehren.
  pause
  exit /b 1
)
%PY% check_gemini.py
echo.
pause
