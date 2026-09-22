@echo off
cd /d "%~dp0.."
set PGROOT=assets\pgsql\bin
set PGPASSWORD=ibvap_dev_2026
if exist db\data\PG_VERSION (
  echo [pg] already initialized, starting if needed >> pg_setup_log.txt
  %PGROOT%\pg_ctl.exe -D db\data -o "-p 5433" -l db\logfile start >> pg_setup_log.txt 2>&1
) else (
  echo ibvap_dev_2026> db\pwfile.tmp
  echo [pg] running initdb >> pg_setup_log.txt
  %PGROOT%\initdb.exe -D db\data -U ibvap --auth=md5 --pwfile=db\pwfile.tmp -E UTF8 --locale=C >> pg_setup_log.txt 2>&1
  del db\pwfile.tmp
  echo [pg] starting server >> pg_setup_log.txt
  %PGROOT%\pg_ctl.exe -D db\data -o "-p 5433" -l db\logfile start >> pg_setup_log.txt 2>&1
)
timeout /t 3 /nobreak >nul
echo [pg] creating database if missing >> pg_setup_log.txt
%PGROOT%\psql.exe -U ibvap -p 5433 -h localhost -d postgres -c "CREATE DATABASE ibvap;" >> pg_setup_log.txt 2>&1
echo [pg] setup done >> pg_setup_log.txt
