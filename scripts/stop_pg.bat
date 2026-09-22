@echo off
cd /d "%~dp0.."
assets\pgsql\bin\pg_ctl.exe -D db\data -o "-p 5433" -l db\logfile stop
