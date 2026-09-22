$procs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -like '*vite*' }
if ($procs) { ($procs | Select-Object -First 1).ProcessId } else { Write-Output "NOT_FOUND" }
