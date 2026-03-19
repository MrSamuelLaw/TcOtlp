
# copy-generated.ps1
# Copies generated code from code-gen to the TwinCAT project
# Usage: ./copy-generated.ps1 [options]

param(
    [switch]$DryRun,
    [switch]$GenerateFirst,
    [switch]$RunTests
)

$ErrorActionPreference = "Stop"

# Get the script directory
if ($PSScriptRoot) {
    $scriptDir = $PSScriptRoot
} else {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommandPath
}
$rootDir = Split-Path -Parent $scriptDir
$codeGenDir = Join-Path $rootDir "code-gen"

Write-Host "TcOtlp Code Generator & Importer" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan

# Step 1: Generate (optional)
if ($GenerateFirst) {
    Write-Host "`nStep 1: Generating code..." -ForegroundColor Green
    Push-Location $codeGenDir
    try {
        uv run python generate.py
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Generation failed!" -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
}

# Step 2: Import to TwinCAT project
Write-Host "`nStep 2: Importing generated code to TwinCAT project..." -ForegroundColor Green
Push-Location $codeGenDir
try {
    $importArgs = @("run", "python", "import_to_plcproj.py")
    if ($DryRun) {
        Write-Host "Running in DRY-RUN mode (no files will be modified)" -ForegroundColor Yellow
        $importArgs += "--dry-run"
    }
    
    uv $importArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Import failed!" -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host "`nStep 2: Complete! " -ForegroundColor Green

# Step 3: Run tests (optional)
if ($RunTests) {
    Write-Host "`nStep 3: Running tests..." -ForegroundColor Green
    Push-Location $rootDir
    try {
        & (Join-Path $scriptDir "run-tests.ps1")
    } finally {
        Pop-Location
    }
}

Write-Host "`nDone!" -ForegroundColor Cyan
