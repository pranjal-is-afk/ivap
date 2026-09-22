@echo off
rem Launches the API and Vite in separate minimized windows (no quoting pain
rem through bash->cmd). Safe to re-run: windowed servers die with their window.
cd /d "%~dp0.."
start "ibvap-api" /min cmd /c "scripts_dev\run_api.bat"
start "ibvap-ui"  /min cmd /c "scripts_dev\run_frontend.bat"
echo launched
