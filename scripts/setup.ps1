param([string]$PackageIndex = 'https://pypi.org/simple')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path .venv/Scripts/python.exe)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment setup failed.' }
}
& .venv/Scripts/python.exe -m pip install -r backend/requirements.txt --index-url $PackageIndex --timeout 120
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
if (!(Test-Path tools/libredwg/dwg2dxf.exe)) {
    New-Item -ItemType Directory -Force tools/libredwg | Out-Null
    Invoke-WebRequest 'https://github.com/LibreDWG/libredwg/releases/download/0.14/libredwg-0.14-win64.zip' -OutFile tools/libredwg-0.14-win64.zip
    Expand-Archive -LiteralPath tools/libredwg-0.14-win64.zip -DestinationPath tools/libredwg -Force
}
npm install
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
Write-Host 'Ready. Run npm run server and npm run dev in separate terminals.'
