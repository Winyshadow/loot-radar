# Builds LootRadarSetup.exe:
#   1. PyInstaller packs Loot Radar and Python into <out>\dist\LootRadar (LootRadar.exe + _internal)
#   2. Inno Setup wraps that folder into <out>\dist\LootRadarSetup.exe.
# Used on this PC and by GitHub Actions (.github/workflows/release.yml).
#
#   powershell -ExecutionPolicy Bypass -File build\build.ps1                 (uses build\.venv)
#   powershell -ExecutionPolicy Bypass -File build\build.ps1 -Python python  (any Python with the packages)
#
# <out> is %LOCALAPPDATA%\LootRadarBuild unless -Out says otherwise: outside OneDrive, which
# locks files while it syncs them and breaks the build.
param(
  [string]$Python = "",
  [string]$Iscc = "",
  [string]$Out = ""
)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$root = Split-Path $here -Parent
$version = (Get-Content "$root\VERSION" -Raw).Trim()
if (-not $Out) { $Out = "$env:LOCALAPPDATA\LootRadarBuild" }
$work = "$Out\work"
$dist = "$Out\dist"
Write-Host "Building Loot Radar $version in $Out"

# --- tools ---------------------------------------------------------------------------------
if (-not $Python) {
  $Python = "$here\.venv\Scripts\python.exe"
  if (-not (Test-Path $Python)) {
    throw "No build\.venv yet. Make it with:  python -m venv build\.venv  then  build\.venv\Scripts\python -m pip install -r app\requirements.txt -r build\requirements-build.txt"
  }
}
if (-not $Iscc) {
  $candidates = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")
  $Iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $Iscc) { $Iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source }
  if (-not $Iscc) { throw "Inno Setup 6 (ISCC.exe) not found. Install it: winget install JRSoftware.InnoSetup" }
}
New-Item -ItemType Directory -Force $work, $dist | Out-Null
$utf8 = New-Object Text.UTF8Encoding $false  # no BOM: Python can't read files that start with one

# --- version info for LootRadar.exe (shows in its Properties > Details) -----------------------
$parts = ($version.Split(".") + @("0", "0", "0", "0"))[0..3] | ForEach-Object { [int]($_ -replace "\D", "0") }
$tuple = ($parts -join ", ")
$info = @"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($tuple), prodvers=($tuple), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'solitary_samurai'),
      StringStruct('FileDescription', 'Loot Radar'),
      StringStruct('FileVersion', '$version'),
      StringStruct('InternalName', 'LootRadar'),
      StringStruct('LegalCopyright', '(c) 2026 solitary_samurai. All rights reserved.'),
      StringStruct('OriginalFilename', 'LootRadar.exe'),
      StringStruct('ProductName', 'Loot Radar'),
      StringStruct('ProductVersion', '$version')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
[IO.File]::WriteAllText("$work\version_info.txt", $info, $utf8)

# --- installer pictures: the radar icon on Loot Radar's dark blue (Inno Setup wants BMP) ---------
$pics = @"
from PIL import Image
icon = Image.open(r"$root\art\app-icon.png").convert("RGBA")
def make(w, h, size, out, bg):
    img = Image.new("RGB", (w, h), bg)
    i = icon.resize((size, size), Image.LANCZOS)
    img.paste(i, ((w - size) // 2, (h - size) // 2 if h < 2 * w else h // 3 - size // 2), i)
    img.save(out)
for s in (1, 2):
    make(164 * s, 314 * s, 120 * s, rf"$work\wizard-large-{s}.bmp", (7, 27, 39))
    make(55 * s, 55 * s, 49 * s, rf"$work\wizard-small-{s}.bmp", (255, 255, 255))
"@
[IO.File]::WriteAllText("$work\pictures.py", $pics, $utf8)
& $Python "$work\pictures.py"
if ($LASTEXITCODE -ne 0) { throw "Making the installer pictures failed" }

# --- 1. PyInstaller -----------------------------------------------------------------------
$env:LR_WORK = $work  # lootradar.spec finds version_info.txt here
& $Python -m PyInstaller --noconfirm --clean --log-level WARN --distpath $dist --workpath "$work\pyinstaller" "$here\lootradar.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
if (-not (Test-Path "$dist\LootRadar\LootRadar.exe")) { throw "PyInstaller didn't make LootRadar.exe" }

# --- 2. Inno Setup ------------------------------------------------------------------------
& $Iscc "/Q" "/DAppVersion=$version" "/DDistDir=$dist" "/DWorkDir=$work" "/O$dist" "$here\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed ($LASTEXITCODE)" }

$setup = Get-Item "$dist\LootRadarSetup.exe"
Write-Host ("Done: {0} ({1:N1} MB)" -f $setup.FullName, ($setup.Length / 1MB))
