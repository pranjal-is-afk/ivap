@echo off
rem ============================================================
rem  IBVAP one-command startup (Windows, no Docker required)
rem  1. PostgreSQL (portable, port 5433)   2. FastAPI (:8000)
rem  3. Vite dev server (:5173)
rem ============================================================
cd /d "%~dp0.."

echo [1/3] Starting PostgreSQL (port 5433)...
if not exist db\data\PG_VERSION (
  echo   first run: initializing database cluster...
  echo ibvap_dev_2026> db\pwfile.tmp
  assets\pgsql\bin\initdb.exe -D db\data -U ibvap --auth=md5 --pwfile=db\pwfile.tmp -E UTF8 --locale=C
  del db\pwfile.tmp
  assets\pgsql\bin\psql.exe -U ibvap -p 5433 -h localhost -d postgres -c "SELECT 1" >nul 2>&1 || (
    assets\pgsql\bin\pg_ctl.exe -D db\data -o "-p 5433" -l db\logfile start
  )
  timeout /t 3 /nobreak >nul
  assets\pgsql\bin\psql.exe -U ibvap -p 5433 -h localhost -d postgres -c "CREATE DATABASE ibvap;" 2>nul
) else (
  assets\pgsql\bin\pg_ctl.exe -D db\data -o "-p 5433" -l db\logfile status >nul 2>&1 || (
    assets\pgsql\bin\pg_ctl.exe -D db\data -o "-p 5433" -l db\logfile start
  )
)
timeout /t 2 /nobreak >nul

echo [2/3] Starting IBVAP API on http://127.0.0.1:8000 ...
start "IBVAP API" /min cmd /c "scripts\run_api_window.bat"

echo [3/3] Starting UI on http://localhost:5173 ...
start "IBVAP UI" /min cmd /c "scripts\run_frontend_window.bat"

echo.
echo ============================================================
echo   IBVAP is starting up. Give it ~30 seconds, then open:
echo     UI  : http://localhost:5173
echo     API : http://127.0.0.1:8000/api/health
echo   Login: admin / ibvap-admin-2026
echo ============================================================
