$solutionPath = Join-Path $PSScriptRoot "TcOtlp\TcOtlp.sln"
$logPath = Join-Path $PSScriptRoot "build.log"
# $config = "Release|TwinCAT RT (x64)"
$devenv = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.com"

Write-Host "Rebuilding: $config"
# & $devenv $solutionPath /rebuild $config 2>&1 | Tee-Object -FilePath $logPath
& $devenv $solutionPath /rebuild 2>&1 | Tee-Object -FilePath $logPath
$exitCode = $LASTEXITCODE

$errors = Select-String -Path $logPath -Pattern "error:" -SimpleMatch
if ($errors) {
    Write-Host "`n===== BUILD ERRORS =====" -ForegroundColor Red
    $errors | ForEach-Object { Write-Host $_.Line -ForegroundColor Red }
}

Write-Host "`nBuild log: $logPath"
exit $exitCode
