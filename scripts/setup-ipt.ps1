# Install the portable open-source IPT engine inside this project only.
param([string]$PackageIndex = 'https://pypi.org/simple')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
New-Item -ItemType Directory -Force tools | Out-Null

# Verify cached and downloaded archives before extracting executable components.
function Get-VerifiedArchive([string]$Url, [string]$Path, [string]$Hash) {
    if (!(Test-Path -LiteralPath $Path)) {
        Invoke-WebRequest $Url -OutFile $Path -TimeoutSec 900
    }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Hash) {
        throw "Archive checksum mismatch: $Path. Remove this archive and rerun setup."
    }
}

if (!(Test-Path tools/freecad/bin/python.exe)) {
    Get-VerifiedArchive `
        'https://github.com/FreeCAD/FreeCAD/releases/download/0.21.2/FreeCAD-0.21.2-Windows-x86_64.7z' `
        'tools/FreeCAD.7z' `
        '06A8F162E3FA9BD8CC98C0CF117D1B3507B9A6564D3DA0D16BC5E5C11D7E7880'
    New-Item -ItemType Directory -Force tools/freecad | Out-Null
    tar -xf tools/FreeCAD.7z -C tools/freecad --strip-components 1
    if ($LASTEXITCODE -ne 0) { throw 'FreeCAD extraction failed.' }
}

if (!(Test-Path tools/InventorLoader-master/Import_IPT.py)) {
    Get-VerifiedArchive `
        'https://codeload.github.com/jmplonka/InventorLoader/zip/e94bdf5e29052a0dc7ce6fdf755e956ae507caec' `
        'tools/InventorLoader-pinned.zip' `
        '4EC53D930187235EF0CC4E88F52EC986C5FCD35E45F4165BF620D164A54D820C'
    New-Item -ItemType Directory -Force tools/InventorLoader-master | Out-Null
    tar -xf tools/InventorLoader-pinned.zip -C tools/InventorLoader-master --strip-components 1
    if ($LASTEXITCODE -ne 0) { throw 'InventorLoader extraction failed.' }
}

& .venv/Scripts/python.exe -m pip install --target tools/ipt-python --upgrade `
    olefile==0.47 xlrd==2.0.2 xlutils==2.0.0 xlwt==1.3.0 --index-url $PackageIndex
if ($LASTEXITCODE -ne 0) { throw 'IPT Python dependencies failed to install.' }
& tools/freecad/bin/python.exe -c "import FreeCAD, Part; print('FreeCAD runtime:', FreeCAD.Version()[:3])"
if ($LASTEXITCODE -ne 0) { throw 'FreeCAD runtime verification failed.' }
Write-Host 'IPT engine ready. Restart the backend; Autodesk Inventor is not required.'
