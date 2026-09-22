@echo off
cd /d "%~dp0.."
start "ibvap-api-cpu" /min cmd /c "scripts_dev\run_api_cpu.bat"
echo launched
