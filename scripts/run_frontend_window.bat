@echo off
cd /d "%~dp0..\frontend"
call npm run dev > ..\frontend_log.txt 2>&1
