<#
Open one native Inventor part and export its complete solid model as STEP.
Requires a locally installed and activated Autodesk Inventor.
#>
param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'

# Resolve and validate the fixed input/output paths before starting Inventor.
function Get-ConversionPaths {
    $inputFile = (Resolve-Path -LiteralPath $InputPath).Path
    $outputFile = [System.IO.Path]::GetFullPath($OutputPath)
    if ([System.IO.Path]::GetExtension($inputFile).ToLowerInvariant() -ne '.ipt') {
        throw 'Input must be an IPT part.'
    }
    if ([System.IO.Path]::GetExtension($outputFile).ToLowerInvariant() -notin @('.step', '.stp')) {
        throw 'Output must be STEP or STP.'
    }
    if (Test-Path -LiteralPath $outputFile) {
        throw 'Output already exists.'
    }
    return $inputFile, $outputFile
}

$inputFile, $outputFile = Get-ConversionPaths
$inventor = $null
$document = $null
try {
    $inventor = New-Object -ComObject Inventor.Application
    $inventor.Visible = $false
    $document = $inventor.Documents.Open($inputFile, $false)
    if ($null -eq $document) {
        throw 'Inventor did not open the part.'
    }
    $document.SaveAs($outputFile, $true)
    if (!(Test-Path -LiteralPath $outputFile)) {
        throw 'Inventor did not create the STEP file.'
    }
    Write-Output "Converted: $outputFile"
}
finally {
    if ($null -ne $document) { $document.Close($true) }
    if ($null -ne $inventor) { $inventor.Quit() }
}
