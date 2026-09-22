$conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $conns) { Write-Output "NO_LISTENER"; exit 0 }
$conns | ForEach-Object {
  $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)"
  Write-Output ("PID={0} NAME={1} CMD={2}" -f $_.OwningProcess, $p.Name, $p.CommandLine)
}
