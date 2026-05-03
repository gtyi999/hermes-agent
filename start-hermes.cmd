@echo off
setlocal

cd /d "%~dp0"
chcp 65001 >nul

rem PYTHONUTF8 only accepts 0 or 1. Values like "utf-8" crash Python
rem before the interpreter can even start.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if "%~1"=="" (
    venv\Scripts\python.exe hermes chat
) else (
    venv\Scripts\python.exe hermes %*
)
