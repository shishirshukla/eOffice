# Builds the eOffice Signer and its MSI installer. Run on Windows from this folder:
#   powershell -ExecutionPolicy Bypass -File .\build.ps1
# Needs the .NET SDK (8 or later) on the BUILD machine only - not on user PCs.

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host '== Building eOfficeSigner.exe (.NET Framework 4.8.1)'
dotnet build .\eOfficeSigner\eOfficeSigner.csproj -c Release -nologo
if ($LASTEXITCODE -ne 0) { throw 'Signer build failed' }

Write-Host '== Building MSI (WiX v5)'
dotnet build .\installer\eOfficeSigner.Installer.wixproj -c Release -nologo
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }

$msi = Get-ChildItem .\installer\bin\Release -Recurse -Filter *.msi | Select-Object -First 1
Write-Host ''
Write-Host "MSI ready: $($msi.FullName)"
Write-Host 'Install:   msiexec /i "<msi>"        (silent: add /qn)'
Write-Host 'Optional:  sign the exe and MSI with the bank code-signing certificate (signtool) before distribution.'
