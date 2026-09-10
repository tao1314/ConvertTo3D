<#
Run on Windows with a licensed SOLIDWORKS installation.
Imports a generated STEP as a solid and saves a native SLDPRT.
This does not recover the source CAD feature history.
#>
param(
    [Parameter(Mandatory = $true)][string]$StepPath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$stepFile = (Resolve-Path -LiteralPath $StepPath).Path
$partFile = [System.IO.Path]::GetFullPath($OutputPath)
if ([System.IO.Path]::GetExtension($stepFile).ToLowerInvariant() -notin @('.step', '.stp')) {
    throw 'Input must be STEP or STP.'
}
if ([System.IO.Path]::GetExtension($partFile).ToLowerInvariant() -ne '.sldprt') {
    throw 'Output must have the .sldprt extension.'
}
if (Test-Path -LiteralPath $partFile) { throw 'Output already exists. Choose a new filename.' }
if (!(Test-Path -LiteralPath (Split-Path $partFile -Parent))) { throw 'Output directory does not exist.' }
$sw = New-Object -ComObject SldWorks.Application
[int]$importErrors = 0
$importData = $sw.GetImportFileData($stepFile)
$model = $sw.LoadFile4($stepFile, 'r', $importData, [ref]$importErrors)
if ($null -eq $model -or $importErrors -ne 0) { throw "SOLIDWORKS import failed: $importErrors" }
[int]$saveErrors = 0
[int]$saveWarnings = 0
$saved = $model.Extension.SaveAs($partFile, 0, 1, $null, [ref]$saveErrors, [ref]$saveWarnings)
if (!$saved -or $saveErrors -ne 0 -or !(Test-Path -LiteralPath $partFile)) {
    throw "SOLIDWORKS save failed: $saveErrors"
}
Write-Host "Saved: $partFile (warnings: $saveWarnings)"
