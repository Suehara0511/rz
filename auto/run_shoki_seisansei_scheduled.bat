@echo off
cd /d "%~dp0"
if not exist logs mkdir logs
"Z:\Users\suehara\Documents\python\analysis\.venv\Scripts\python.exe" run_shoki_seisansei.py > "logs\run_shoki_seisansei.log" 2>&1
