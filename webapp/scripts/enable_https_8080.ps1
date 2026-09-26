# Generate self-signed TLS cert for IP and restart bot with HTTPS on :8080.
# Run as Administrator (optional, for firewall).
# Browser will show a warning (self-signed) — click Advanced -> Continue.

param(
  [string]$Root = "C:\bot_calling",
  [string]$Ip = "91.149.133.54",
  [int]$Port = 8080,
  [int]$Days = 825
)

$ErrorActionPreference = "Stop"
Set-Location $Root

$certDir = Join-Path $Root "certs"
New-Item -ItemType Directory -Force -Path $certDir | Out-Null
$certFile = Join-Path $certDir "bot.crt"
$keyFile = Join-Path $certDir "bot.key"
$pfxFile = Join-Path $certDir "bot.pfx"

Write-Host "==> Creating self-signed cert for IP $Ip (+ 127.0.0.1, 192.168.0.115)" -ForegroundColor Cyan

# Prefer openssl if present; else use PowerShell certificate store export
$openssl = Get-Command openssl -ErrorAction SilentlyContinue
if ($openssl) {
  $cnf = Join-Path $certDir "openssl.cnf"
  @"
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = $Ip
O = BotCalling
C = BY

[v3_req]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
IP.1 = $Ip
IP.2 = 127.0.0.1
IP.3 = 192.168.0.115
DNS.1 = localhost
"@ | Set-Content -Path $cnf -Encoding ASCII

  & openssl req -x509 -nodes -newkey rsa:2048 -keyout $keyFile -out $certFile -days $Days -config $cnf
} else {
  Write-Host "openssl not found — using New-SelfSignedCertificate" -ForegroundColor Yellow
  $cert = New-SelfSignedCertificate `
    -Subject "CN=$Ip" `
    -TextExtension @("2.5.29.17={text}IPAddress=$Ip&IPAddress=127.0.0.1&IPAddress=192.168.0.115&DNSName=localhost") `
    -KeyAlgorithm RSA `
    -KeyLength 2048 `
    -NotAfter (Get-Date).AddDays($Days) `
    -CertStoreLocation "Cert:\LocalMachine\My" `
    -KeyExportPolicy Exportable `
    -FriendlyName "BotCalling-$Ip"

  $pwd = ConvertTo-SecureString -String "botcalling" -Force -AsPlainText
  Export-PfxCertificate -Cert $cert -FilePath $pfxFile -Password $pwd | Out-Null
  Export-Certificate -Cert $cert -FilePath $certFile -Type CERT | Out-Null

  # Extract PEM key via openssl-free path: use python cryptography / ssl
  $py = Join-Path $Root ".venv\Scripts\python.exe"
  & $py -c @"
from pathlib import Path
try:
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption, pkcs12
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'cryptography', '-q'])
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption, pkcs12

pfx = Path(r'$pfxFile').read_bytes()
key, cert, _ = pkcs12.load_key_and_certificates(pfx, b'botcalling')
Path(r'$keyFile').write_bytes(
    key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())
)
Path(r'$certFile').write_bytes(cert.public_bytes(Encoding.PEM))
print('PEM written')
"@
}

if (-not (Test-Path $certFile) -or -not (Test-Path $keyFile)) {
  throw "cert/key not created"
}
Write-Host "cert: $certFile"
Write-Host "key:  $keyFile"

Write-Host "==> Free port $Port" -ForegroundColor Cyan
try {
  Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
  Start-Sleep 2
} catch {}

Write-Host "==> Firewall HTTPS $Port" -ForegroundColor Cyan
New-NetFirewallRule -DisplayName "Bot Calling HTTPS $Port" -Direction Inbound -Action Allow `
  -Protocol TCP -LocalPort $Port -Profile Any -EdgeTraversalPolicy Allow -ErrorAction SilentlyContinue | Out-Null

$py = Join-Path $Root ".venv\Scripts\python.exe"
$logDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Write-Host "==> Start uvicorn HTTPS 0.0.0.0:$Port" -ForegroundColor Cyan
$env:PYTHONPATH = $Root
$env:COQUI_TOS_AGREED = "1"

Start-Process -FilePath $py `
  -ArgumentList @(
    "-m", "uvicorn", "webapp.app:app",
    "--host", "0.0.0.0",
    "--port", "$Port",
    "--ssl-certfile", $certFile,
    "--ssl-keyfile", $keyFile
  ) `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $logDir "uvicorn.out.log") `
  -RedirectStandardError (Join-Path $logDir "uvicorn.err.log")

Start-Sleep 3
netstat -ano | findstr ":$Port"

Write-Host ""
Write-Host "Open (accept browser warning):" -ForegroundColor Green
Write-Host "  https://127.0.0.1:$Port/"
Write-Host "  https://192.168.0.115:$Port/"
Write-Host "  https://${Ip}:$Port/"
Write-Host ""
Write-Host "NOTE: SSL does NOT fix port-forward. If http://IP:$Port timed out, https:// will too."
Write-Host "For real public HTTPS without port-forward use Cloudflare Tunnel."
