@echo off
cd /d "%~dp0.."
echo Stopping IBVAP API + UI...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*uvicorn*app.main*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | Where-Object { $_.CommandLine -like '*vite*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Done. (Postgres left running; stop it with scripts\stop_pg.bat)
