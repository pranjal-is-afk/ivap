@echo off
cd /d "%~dp0.."
if exist pg_unzip.marker del pg_unzip.marker
echo [%date% %time%] expanding postgresql zip via PowerShell >> pg_unzip_log.txt
powershell -NoProfile -Command "Expand-Archive -Path 'assets\postgresql.zip' -DestinationPath 'assets' -Force" >> pg_unzip_log.txt 2>&1
if errorlevel 1 (
  echo [%date% %time%] PG UNZIP FAILED >> pg_unzip_log.txt
  exit /b 1
)
echo [%date% %time%] pg unzip DONE >> pg_unzip_log.txt
echo DONE > pg_unzip.marker
