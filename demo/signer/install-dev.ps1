# Quick install for developers / testers WITHOUT the MSI.
# Copies the built signer to %LOCALAPPDATA%\Programs\eOfficeSigner and registers
# the eoffice-sign:// link for the current user. No admin rights needed.
#   powershell -ExecutionPolicy Bypass -File .\install-dev.ps1 [-Uninstall] [-Server http://192.168.1.10:8000]

param(
    [switch]$Uninstall,
    [string]$Server
)

$ErrorActionPreference = 'Stop'
$target = Join-Path $env:LOCALAPPDATA 'Programs\eOfficeSigner'
$classKey = 'HKCU:\Software\Classes\eoffice-sign'

if ($Uninstall) {
    Remove-Item $classKey -Recurse -ErrorAction SilentlyContinue
    Remove-Item $target -Recurse -ErrorAction SilentlyContinue
    Write-Host 'eOffice Signer removed.'
    return
}

$bin = Join-Path $PSScriptRoot 'eOfficeSigner\bin\Release\net481'
if (-not (Test-Path (Join-Path $bin 'eOfficeSigner.exe'))) {
    throw "Build first: dotnet build .\eOfficeSigner\eOfficeSigner.csproj -c Release"
}

New-Item -ItemType Directory -Force $target | Out-Null
Copy-Item (Join-Path $bin 'eOfficeSigner.exe'), (Join-Path $bin 'eOfficeSigner.exe.config') $target -Force
$exe = Join-Path $target 'eOfficeSigner.exe'

if ($Server) {
    # Add the demo server to AllowedServers in the config.
    $cfgPath = "$exe.config"
    [xml]$cfg = Get-Content $cfgPath
    $node = $cfg.configuration.appSettings.add | Where-Object { $_.key -eq 'AllowedServers' }
    $list = @($node.value -split ';' | Where-Object { $_ }) + $Server.TrimEnd('/')
    $node.value = ($list | Select-Object -Unique) -join ';'
    $cfg.Save($cfgPath)
    Write-Host "Allowed servers: $($node.value)"
}

New-Item -Force $classKey | Out-Null
Set-ItemProperty $classKey '(default)' 'URL:eOffice Signer Protocol'
Set-ItemProperty $classKey 'URL Protocol' ''
New-Item -Force "$classKey\shell\open\command" | Out-Null
Set-ItemProperty "$classKey\shell\open\command" '(default)' "`"$exe`" `"%1`""

Write-Host "Installed to $target and registered eoffice-sign://"
