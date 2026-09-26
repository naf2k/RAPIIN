#Requires -Version 5.1
<#
.SYNOPSIS
  Pasang RAPIIN Desktop Agent di PC Windows dalam 1 klik.

.DESCRIPTION
  Karyawan cukup klik kanan file ini -> "Run with PowerShell" (atau jalankan
  perintah di bawah), jawab 3 pertanyaan, sisanya otomatis:
  cek/pasang Python, cek/pasang uv, cek Tailscale, cek server, unduh rilis resmi,
  verifikasi checksum, pasang agent, daftar device, aktifkan autostart, verifikasi.

  Script mengunduh wheel resmi dari GitHub Releases (repositori publik, tanpa
  perlu login/gh). Bila ada wheel di folder yang sama, wheel itu yang dipakai
  (berguna untuk pemasangan offline).

  Cara jalanin (pilih salah satu):
    powershell -ExecutionPolicy Bypass -File .\Install-Rapiin.ps1
    powershell -ExecutionPolicy Bypass -File .\Install-Rapiin.ps1 -ServerUrl https://NAMA-SERVER.ts.net

  Syarat yang TIDAK bisa otomatis: login Tailscale (jendela login muncul sekali)
  dan klik "Yes" saat Windows minta izin admin untuk pemasangan.
#>
[CmdletBinding()]
param(
  [string]$ServerUrl = 'https://haimacs-macbook-pro-84.tail9cf4bc.ts.net',
  [string]$Workspace = "$HOME\Downloads",
  # Folder berisi wheel untuk pemasangan offline. Kosong = unduh dari rilis.
  [string]$WheelDir = '',
  # Rilis tertentu, mis. 'rapiin-v1.1.1'. Kosong = rilis terbaru.
  [string]$Tag = '',
  [string]$Repository = 'naf2k/RAPIIN'
)

$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 default ke TLS 1.0, yang ditolak github.com. Naikkan
# ke TLS 1.2 sebelum panggilan HTTPS apa pun.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

function Write-Step([string]$Message) {
  Write-Host ""
  Write-Host "== $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
  Write-Host "[ok] $Message" -ForegroundColor Green
}

function Write-Fail([string]$Message) {
  Write-Host "[gagal] $Message" -ForegroundColor Red
}

function Refresh-Path {
  $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
  $env:Path = "$machinePath;$userPath"
}

function Test-PythonOk {
  foreach ($candidate in @('py', 'python')) {
    try {
      $out = & $candidate --version 2>$null
      if ($out -match 'Python\s+3\.(\d+)') {
        if ([int]$Matches[1] -ge 10) { return $true }
      }
    } catch { }
  }
  return $false
}

Write-Host "==========================================="
Write-Host "  PASANG RAPIIN - tinggal jawab 3 hal"
Write-Host "==========================================="

# --- 1. Tanya 3 hal dulu (biar sisanya jalan tanpa henti) ---
$Email = Read-Host -Prompt '[1/3] Email RAPIIN kamu'
$ServerInput = Read-Host -Prompt "[2/3] Alamat server (Enter = $ServerUrl)"
if ($ServerInput.Trim() -ne '') { $ServerUrl = $ServerInput.Trim() }
Write-Host '[3/3] Kata sandi diminta nanti oleh program (aman, tidak tercatat di script ini).'

# --- 2. Python 3.10+ ---
Write-Step 'Cek Python...'
if (-not (Test-PythonOk)) {
  Write-Host 'Python belum ada, pasang otomatis via winget (mungkin muncul izin admin, klik Yes)...'
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Fail 'winget tidak ditemukan. Pasang manual Python 3.12+ dari python.org (centang Add to PATH), lalu ulangi script ini.'
    exit 1
  }
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  Refresh-Path
}
if (-not (Test-PythonOk)) {
  Write-Fail 'Python masih tidak ketemu. Tutup jendela ini, buka baru, ulangi script ini.'
  exit 1
}
Write-Ok 'Python siap.'

# --- 3. uv ---
Write-Step 'Cek uv...'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host 'uv belum ada, pasang otomatis...'
  & powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  Refresh-Path
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Fail 'uv masih tidak ketemu. Tutup jendela ini, buka baru, ulangi script ini.'
  exit 1
}
Write-Ok 'uv siap.'

# --- 4. Tailscale ---
Write-Step 'Cek Tailscale...'
if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
  Write-Host 'Tailscale belum ada, pasang otomatis via winget...'
  winget install -e --id Tailscale.Tailscale --accept-source-agreements --accept-package-agreements
  Refresh-Path
}
try {
  $tsStatus = tailscale status 2>&1 | Out-String
} catch {
  $tsStatus = ''
}
if ($tsStatus -notmatch '100\.') {
  Write-Host 'Tailscale belum login. Jendela login akan dibuka, selesaikan login lalu kembali ke sini.'
  tailscale login
  Read-Host -Prompt 'Tekan Enter setelah login Tailscale selesai'
}
Write-Ok 'Tailscale siap.'

# --- 5. Server bisa dihubungi? ---
Write-Step "Cek server ($ServerUrl)..."
try {
  $ready = Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 "$ServerUrl/ready"
  if ($ready.Content -notmatch 'ready') { throw 'jawaban server tidak dikenal' }
} catch {
  Write-Fail "Server tidak bisa dihubungi: $($_.Exception.Message)"
  Write-Host 'Pastikan Tailscale satu tailnet dengan server, lalu ulangi script ini.'
  exit 1
}
Write-Ok 'Server bisa dihubungi.'

# --- 6. Siapkan wheel: pakai lokal bila ada, selain itu unduh dari rilis ---
Write-Step 'Siapkan file agent...'
if ([string]::IsNullOrWhiteSpace($WheelDir)) {
  if ($PSScriptRoot) { $WheelDir = $PSScriptRoot }
  elseif ($PSCommandPath) { $WheelDir = Split-Path -Parent $PSCommandPath }
  else { $WheelDir = (Get-Location).Path }
}

$wheel = Get-ChildItem -Path $WheelDir -Filter 'rapiin_agent-*.whl' -ErrorAction SilentlyContinue |
  Sort-Object Name -Descending | Select-Object -First 1
$sumFile = Join-Path $WheelDir 'SHA256SUMS'

if ($wheel) {
  Write-Ok "Memakai wheel yang sudah ada: $($wheel.Name)"
} else {
  # Tidak ada wheel lokal, jadi unduh rilis resmi dari GitHub.
  $owner = ($Repository -split '/')[0]
  $repoName = ($Repository -split '/')[1]
  $headers = @{ 'User-Agent' = 'RAPIIN-Installer'; 'Accept' = 'application/vnd.github+json' }

  if ([string]::IsNullOrWhiteSpace($Tag)) {
    Write-Host "Mencari rilis terbaru di $Repository..."
    try {
      $release = Invoke-RestMethod -Headers $headers -TimeoutSec 30 `
        "https://api.github.com/repos/$owner/$repoName/releases/latest"
      $Tag = $release.tag_name
    } catch {
      Write-Fail "Tidak bisa mengambil daftar rilis: $($_.Exception.Message)"
      exit 1
    }
  }
  if ([string]::IsNullOrWhiteSpace($Tag)) {
    Write-Fail "Tidak menemukan rilis di $Repository."
    exit 1
  }

  # Nama aset mengikuti versi pada tag: rapiin-v1.1.0 -> rapiin_agent-1.1.0-*.whl
  $version = $Tag -replace '^rapiin-v', ''
  $wheelName = "rapiin_agent-$version-py3-none-any.whl"
  $baseUrl = "https://github.com/$Repository/releases/download/$Tag"

  $downloadDir = Join-Path $env:TEMP "rapiin-agent-$version"
  New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null
  $wheelPath = Join-Path $downloadDir $wheelName
  $sumPath = Join-Path $downloadDir 'SHA256SUMS'

  Write-Host "Mengunduh rilis $Tag..."
  try {
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 300 -Uri "$baseUrl/$wheelName" -OutFile $wheelPath
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 -Uri "$baseUrl/SHA256SUMS" -OutFile $sumPath
  } catch {
    Write-Fail "Unduhan gagal: $($_.Exception.Message)"
    Write-Host "Cek koneksi internet. Bila PC tanpa internet, minta wheel ke IT lalu jalankan ulang dengan -WheelDir <folder>."
    exit 1
  }
  Write-Ok "Rilis $Tag terunduh."

  $wheel = Get-Item $wheelPath
  $sumFile = $sumPath
}

# --- 7. Verifikasi checksum ---
if (Test-Path $sumFile) {
  $expected = (Select-String -Path $sumFile -Pattern ([regex]::Escape($wheel.Name)) | Select-Object -First 1).Line
  $actual = (Get-FileHash -Algorithm SHA256 $wheel.FullName).Hash.ToLower()
  if (-not $expected) {
    Write-Fail "Nama wheel tidak ada di SHA256SUMS, tidak bisa memverifikasi."
    exit 1
  } elseif ($expected.ToLower() -notmatch $actual) {
    Write-Fail 'Checksum wheel TIDAK COCOK. Jangan lanjut, minta file yang benar ke IT.'
    exit 1
  } else {
    Write-Ok 'Checksum cocok.'
  }
} else {
  Write-Fail 'SHA256SUMS tidak ada, tidak bisa memverifikasi unduhan.'
  exit 1
}

# --- 8. Pasang agent ---
Write-Step 'Pasang agent...'
$alreadyInstalled = $false
try {
  $toolList = uv tool list 2>$null | Out-String
  if ($toolList -match 'rapiin-agent') { $alreadyInstalled = $true }
} catch { }
if ($alreadyInstalled) {
  uv tool install --force $wheel.FullName
} else {
  uv tool install $wheel.FullName
}
$rapiinExe = Join-Path $HOME '.local\bin\rapiin.exe'
if (-not (Test-Path $rapiinExe)) {
  Write-Fail 'rapiin.exe tidak ketemu setelah install. Ulangi script ini di jendela baru.'
  exit 1
}
Write-Ok 'Agent terpasang.'
# Pastikan jendela PowerShell baru mengenal perintah rapiin tanpa path lengkap.
$binDir = Split-Path -Parent $rapiinExe
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -notlike "*$binDir*") {
  [Environment]::SetEnvironmentVariable('Path', "$binDir;$userPath", 'User')
  Write-Ok 'Perintah rapiin didaftarkan ke PATH (berlaku untuk jendela baru).'
}
$env:Path = "$binDir;$env:Path"

# --- 9. Daftar device (password diketik di program, bukan di script) ---
Write-Step 'Daftarkan device ini...'
if (-not (Test-Path $Workspace)) {
  New-Item -ItemType Directory -Path $Workspace -Force | Out-Null
}
& $rapiinExe setup --server $ServerUrl --workspace $Workspace --autostart --email $Email
if ($LASTEXITCODE -ne 0) {
  Write-Fail 'Setup gagal. Periksa email/password, lalu ulangi: rapiin setup'
  exit 1
}

# --- 10. Verifikasi ---
Write-Step 'Verifikasi...'
& $rapiinExe verify
if ($LASTEXITCODE -ne 0) {
  Write-Fail 'Verifikasi gagal. Jalankan "rapiin verify" manual dan kirim hasilnya ke IT.'
  exit 1
}

Write-Host ""
Write-Host "SELESAI. RAPIIN hidup dan ikut nyala tiap PC dinyalakan." -ForegroundColor Green
Write-Host "Kerja lewat browser seperti biasa. Perintah berguna: rapiin status | rapiin verify"
