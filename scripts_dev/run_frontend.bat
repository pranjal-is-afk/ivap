@echo off
cd /d "%~dp0..\frontend"
npm run dev > ..\frontend_log.txt 2>&1
