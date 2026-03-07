param(
    [string]$Config = "Debug|TwinCAT OS (x64)",
    [string]$LogFile = "build.log",
    [string]$ErrorLogFile = "build-errors.log",
    [string]$SolutionPath = "TcOtlp\TcOtlp.sln",
    [string]$ProjectName,
    [string]$TwinCatShellShortcut = "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Beckhoff\TwinCAT XAE Shell 64-bit.lnk"
)

$ErrorActionPreference = "Stop"

function Resolve-PathFromRoot {
    param([string]$Path)

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    return [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $Path))
}

function Get-TwinCatBuildHost {
    $appEnvCommand = Get-Command appenv -ErrorAction SilentlyContinue
    if ($appEnvCommand) {
        return @{ Type = "appenv"; Path = $appEnvCommand.Source }
    }

    if (Test-Path $TwinCatShellShortcut) {
        return @{ Type = "shortcut"; Path = $TwinCatShellShortcut }
    }

    throw "Unable to find TwinCAT build host. Run this from TwinCAT x64 shell (where appenv is available) or ensure the TwinCAT XAE Shell 64-bit shortcut exists."
}

function Invoke-TwinCatBuild {
    param(
        [hashtable]$BuildHost,
        [string[]]$Arguments
    )

    if ($BuildHost.Type -eq "appenv") {
        & $BuildHost.Path @Arguments
        return $LASTEXITCODE
    }

    if ($BuildHost.Type -eq "shortcut") {
        $process = Start-Process -FilePath $BuildHost.Path -ArgumentList $Arguments -Wait -PassThru
        return $process.ExitCode
    }

    throw "Unsupported build host type: $($BuildHost.Type)"
}

$resolvedSolution = Resolve-PathFromRoot -Path $SolutionPath
$resolvedLog = Resolve-PathFromRoot -Path $LogFile
$resolvedErrorLog = Resolve-PathFromRoot -Path $ErrorLogFile

if (-not (Test-Path $resolvedSolution)) {
    throw "Solution file not found: $resolvedSolution"
}

$buildHost = Get-TwinCatBuildHost

if (Test-Path $resolvedLog) {
    Remove-Item $resolvedLog -Force
}

if (Test-Path $resolvedErrorLog) {
    Remove-Item $resolvedErrorLog -Force
}

$buildArgs = @(
    $resolvedSolution,
    "/build",
    $Config,
    "/out",
    $resolvedLog
)

if ($ProjectName) {
    $buildArgs += @("/project", $ProjectName)
}

Write-Host "Using build host type: $($buildHost.Type)" -ForegroundColor Cyan
Write-Host "Building: $resolvedSolution" -ForegroundColor Cyan
Write-Host "Configuration: $Config" -ForegroundColor Cyan

Write-Host "Host path: $($buildHost.Path)" -ForegroundColor Cyan

$shellExitCode = Invoke-TwinCatBuild -BuildHost $buildHost -Arguments $buildArgs

if ($null -eq $shellExitCode) {
    $shellExitCode = 0
}

if (-not (Test-Path $resolvedLog)) {
    $runningInstances = Get-Process TcXaeShell -ErrorAction SilentlyContinue
    if ($runningInstances) {
        throw "Build log was not created. A running TcXaeShell instance may have intercepted the command. Close running TcXaeShell windows and try again."
    }

    throw "Build log was not created at $resolvedLog"
}

$logLines = Get-Content $resolvedLog
$logContent = $logLines -join [Environment]::NewLine

$summaryPattern = "Build:\s+(\d+)\s+succeeded(?:\s+or\s+up-to-date)?,\s+(\d+)\s+failed,\s+(\d+)\s+skipped"
$succeededCount = $null
$failedCount = $null

if ($logContent -match $summaryPattern) {
    $succeededCount = [int]$matches[1]
    $failedCount = [int]$matches[2]
}

$errorLines = $logLines | Where-Object { $_ -match "(?i)(:\s*error\b|\bfatal error\b)" }

if ($errorLines.Count -gt 0) {
    $errorLines | Set-Content $resolvedErrorLog
}

if ($succeededCount -eq 0 -and $failedCount -eq 0) {
    Write-Host "`nBuild did not execute any projects (0 succeeded, 0 failed)." -ForegroundColor Yellow
    Write-Host "This usually means the wrong build host was used, or the command was redirected to an already running IDE instance." -ForegroundColor Yellow
    Write-Host "Build log: $resolvedLog" -ForegroundColor Yellow
    exit 2
}

if ($failedCount -gt 0 -or $errorLines.Count -gt 0 -or $shellExitCode -ne 0) {
    Write-Host "`nBuild FAILED" -ForegroundColor Red
    Write-Host "Build log: $resolvedLog" -ForegroundColor Red

    if ($errorLines.Count -gt 0) {
        Write-Host "Error-only log: $resolvedErrorLog" -ForegroundColor Red
    }

    exit 1
}

Write-Host "`nBuild SUCCEEDED" -ForegroundColor Green
Write-Host "Build log: $resolvedLog" -ForegroundColor Green
exit 0
