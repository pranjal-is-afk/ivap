@echo off
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*uvicorn*app.main*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
