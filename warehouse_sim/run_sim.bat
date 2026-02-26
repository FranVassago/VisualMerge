@echo off
setlocal

cd /d %~dp0

if not exist .venv (
  py -3.12 -m venv .venv
)

call .venv\Scripts\activate

python -m pip show pip >nul 2>&1
if errorlevel 1 (
  python -m pip install -U pip
) else (
  echo pip ya instalado, se omite instalacion/upgrade.
)

python -m pip show pygame >nul 2>&1
if errorlevel 1 (
  python -m pip install pygame
) else (
  echo pygame ya instalado, se omite instalacion.
)

py main.py

endlocal
