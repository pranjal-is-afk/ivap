@echo off
rem API in cloud-simulation mode: CPU-only inference + auto-start demo cameras.
cd /d "%~dp0.."
set IBVAP_CPU_ONLY=1
set IBVAP_DEMO=1
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend > api_log_cpu.txt 2>&1
