#Requires -Version 5.1
<#
.SYNOPSIS
  Pasang RAPIIN Desktop Agent di PC Windows dalam 1 klik.

.DESCRIPTION
  Karyawan cukup klik kanan file ini -> "Run with PowerShell" (atau jalankan
  perintah di bawah), jawab 3 pertanyaan, sisanya otomatis:
  cek/pasang Python, cek/pasang uv, cek Tailscale, cek server, verifikasi
  checksum wheel, pasang agent, daftar device, aktifkan autostart, verifikasi.

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
  [string]$WheelDir = ''
)

$ErrorActionPreference = 'Stop'

# $PSScriptRoot tidak selalu terisi saat script dipanggil dari shell lain,
# jadi tentukan folder script di badan script dengan beberapa cadangan.
if ([string]::IsNullOrWhiteSpace($WheelDir)) {
  if ($PSScriptRoot) { $WheelDir = $PSScriptRoot }
  elseif ($PSCommandPath) { $WheelDir = Split-Path -Parent $PSCommandPath }
  else { $WheelDir = (Get-Location).Path }
}

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

# --- 6. Cari wheel + cek checksum ---
Write-Step 'Cari file agent...'
$wheel = Get-ChildItem -Path $WheelDir -Filter 'rapiin_agent-*.whl' | Sort-Object Name -Descending | Select-Object -First 1
if (-not $wheel) {
  Write-Fail "File rapiin_agent-*.whl tidak ketemu di $WheelDir. Taruh wheel di folder yang sama dengan script ini."
  exit 1
}
$sumFile = Join-Path $WheelDir 'SHA256SUMS'
if (Test-Path $sumFile) {
  $expected = (Select-String -Path $sumFile -Pattern ([regex]::Escape($wheel.Name)) | Select-Object -First 1).Line
  $actual = (Get-FileHash -Algorithm SHA256 $wheel.FullName).Hash.ToLower()
  if (-not $expected) {
    Write-Host '(info) Nama wheel tidak ada di SHA256SUMS, lewati cek checksum.'
  } elseif ($expected.ToLower() -notmatch $actual) {
    Write-Fail 'Checksum wheel TIDAK COCOK. Jangan lanjut, minta file yang benar ke IT.'
    exit 1
  } else {
    Write-Ok 'Checksum cocok.'
  }
} else {
  Write-Host '(info) SHA256SUMS tidak ada, lewati cek checksum.'
}

# --- 7. Pasang agent ---
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

# --- 8. Daftar device (password diketik di program, bukan di script) ---
Write-Step 'Daftarkan device ini...'
if (-not (Test-Path $Workspace)) {
  New-Item -ItemType Directory -Path $Workspace -Force | Out-Null
}
& $rapiinExe setup --server $ServerUrl --workspace $Workspace --autostart --email $Email
if ($LASTEXITCODE -ne 0) {
  Write-Fail 'Setup gagal. Periksa email/password, lalu ulangi: rapiin setup'
  exit 1
}

# --- 9. Verifikasi ---
Write-Step 'Verifikasi...'
& $rapiinExe verify
if ($LASTEXITCODE -ne 0) {
  Write-Fail 'Verifikasi gagal. Jalankan "rapiin verify" manual dan kirim hasilnya ke IT.'
  exit 1
}

Write-Host ""
Write-Host "SELESAI. RAPIIN hidup dan ikut nyala tiap PC dinyalakan." -ForegroundColor Green
Write-Host "Kerja lewat browser seperti biasa. Perintah berguna: rapiin status | rapiin verify"
