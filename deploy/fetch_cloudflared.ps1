# Downloads cloudflared (Cloudflare tunnel client) into deploy\ if missing.
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File deploy\fetch_cloudflared.ps1
$ErrorActionPreference = "Stop"
$dest = Join-Path $PSScriptRoot "cloudflared.exe"
if (Test-Path $dest) { Write-Host "cloudflared already present: $dest"; exit 0 }
$url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
Write-Host "Downloading $url ..."
Invoke-WebRequest -Uri $url -OutFile $dest
Write-Host "Saved to $dest"
Write-Host ""
Write-Host "Next:  .\deploy\cloudflared.exe tunnel --url http://127.0.0.1:8000"
