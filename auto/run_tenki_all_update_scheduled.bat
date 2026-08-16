@echo off
cd /d "%~dp0"
if not exist logs mkdir logs
"Z:\Users\suehara\Documents\python\analysis\.venv\Scripts\python.exe" run_tenki_all_update.py > "logs\run_tenki_all_update.log" 2>&1
