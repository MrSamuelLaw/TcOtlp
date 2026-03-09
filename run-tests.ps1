<#
.SYNOPSIS
    Automates TcUnit test execution for the TcOtlp project via DTE COM.
.DESCRIPTION
    Step 1: Creates a DTE COM instance and opens the solution.
    Step 2: Rebuilds the solution and checks for build errors.
#>
param(
    [int]$BuildTimeoutSeconds = 120,
    [int]$TestTimeoutSeconds  = 120,
    [int]$TestPollIntervalSeconds = 10
)

$ErrorActionPreference = "Stop"

$solutionPath = Join-Path $PSScriptRoot "TcOtlp\TcOtlp.sln"

if (-not (Test-Path $solutionPath)) {
    Write-Host "Solution not found: $solutionPath" -ForegroundColor Red
    exit 1
}

# -- Load EnvDTE interop assemblies --------------------------------------------
# Loading these assemblies enables PowerShell to resolve the EnvDTE80.ToolWindows
# interface so that $dte.ToolWindows.ErrorList returns a usable ErrorList object
# with ShowErrors/ShowWarnings/ShowMessages properties and ErrorItems collection.

$publicAssemblies = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\PublicAssemblies"
$interopDll = Join-Path $publicAssemblies "Microsoft.VisualStudio.Interop.dll"
foreach ($dll in @("envdte.dll", "envdte80.dll", "Microsoft.VisualStudio.Interop.dll")) {
    $dllPath = Join-Path $publicAssemblies $dll
    if (Test-Path $dllPath) {
        Add-Type -Path $dllPath
        Write-Host "  Loaded $dll" -ForegroundColor Green
    } else {
        Write-Host "  WARNING: $dllPath not found" -ForegroundColor Yellow
    }
}

# C# helper for Output Window COM interop (PowerShell can't marshal these interfaces)
Add-Type -TypeDefinition @"
using EnvDTE;
public static class OutputWindowHelper {
    public static void ActivatePane(object dte, string paneName) {
        DTE d = (DTE)dte;
        Window win = d.Windows.Item(Constants.vsWindowKindOutput);
        OutputWindow ow = (OutputWindow)win.Object;
        foreach (OutputWindowPane pane in ow.OutputWindowPanes) {
            if (pane.Name == paneName) {
                pane.Activate();
                return;
            }
        }
    }
    public static string ReadPane(object dte, string paneName) {
        DTE d = (DTE)dte;
        Window win = d.Windows.Item(Constants.vsWindowKindOutput);
        OutputWindow ow = (OutputWindow)win.Object;
        foreach (OutputWindowPane pane in ow.OutputWindowPanes) {
            if (pane.Name == paneName) {
                TextDocument doc = pane.TextDocument;
                TextSelection sel = (TextSelection)doc.Selection;
                sel.SelectAll();
                return sel.Text;
            }
        }
        return "";
    }
}
"@ -ReferencedAssemblies @(
    $interopDll
)
Write-Host "  Loaded OutputWindowHelper" -ForegroundColor Green

# -- Step 1: Attach to running VS 2022 instance and open solution -------------

Write-Host "Attaching to running VS 2022 instance..."

$dte = $null
try {
    $dte = [System.Runtime.InteropServices.Marshal]::GetActiveObject("VisualStudio.DTE.17.0")
    Write-Host "  Attached to running VS 2022 instance." -ForegroundColor Green
}
catch {
    Write-Host "  Could not attach to running VS 2022: $_" -ForegroundColor Red
    Write-Host "  Make sure Visual Studio 2022 Community is open." -ForegroundColor Yellow
    exit 1
}

$dte.SuppressUI = $false
$dte.MainWindow.Visible = $true

# Open solution if not already loaded
$currentSln = $dte.Solution.FullName
if ($currentSln -and (Test-Path $currentSln)) {
    Write-Host "Solution already open: $currentSln"
} else {
    Write-Host "Opening solution: $solutionPath"
    $dte.Solution.Open($solutionPath)
    Write-Host "Solution opened."
}

# Activate Error List window and configure filters to show ALL items.
# This is critical: without setting these flags, ErrorItems.Count returns 0
# because the DTE respects whatever filter state the UI last saved.
# try {
#     $dte.ExecuteCommand("View.ErrorList")
#     Write-Host "Error List window activated."
# }
# catch {
#     Write-Host "Could not activate Error List (non-fatal): $_" -ForegroundColor Yellow
# }

# try {
#     $errorList = $dte.ToolWindows.ErrorList
#     $errorList.ShowErrors = $true
#     $errorList.ShowWarnings = $true
#     $errorList.ShowMessages = $true
#     Write-Host "Error List filters configured (Errors + Warnings + Messages)." -ForegroundColor Green
# }
# catch {
#     Write-Host "Could not configure Error List filters (non-fatal): $_" -ForegroundColor Yellow
#     Write-Host "  Trying via ExecuteCommand fallback..."
#     # Fallback: use VS commands to toggle all three filter buttons on
#     try { $dte.ExecuteCommand("View.ErrorList", " Errors") } catch {}
#     try { $dte.ExecuteCommand("View.ErrorList", " Warnings") } catch {}
#     try { $dte.ExecuteCommand("View.ErrorList", " Messages") } catch {}
#     Write-Host "  Ensure Error List shows Messages manually if needed."
# }

# -- Switch Output window to TwinCAT pane --------------------------------------
try {
    $dte.ExecuteCommand("View.Output")
    [OutputWindowHelper]::ActivatePane($dte, "TwinCAT")
    Write-Host "Output window switched to TwinCAT pane." -ForegroundColor Green
}
catch {
    Write-Host "Could not switch Output window to TwinCAT pane: $_" -ForegroundColor Yellow
}

# -- Step 2: Rebuild solution -------------------------------------------------

Write-Host "Starting rebuild..."
$dte.ExecuteCommand("Build.RebuildSolution")

Start-Sleep -Seconds 2
$elapsed = 2
$state = $dte.Solution.SolutionBuild.BuildState
Write-Host "  Initial BuildState: $state"

# vsBuildState: 1=NotStarted, 2=InProgress, 3=Done
while ($state -ne 3) {
    if ($elapsed -ge $BuildTimeoutSeconds) {
        Write-Host "Build timed out after $BuildTimeoutSeconds seconds." -ForegroundColor Red
        $dte.Quit()
        exit 1
    }
    Start-Sleep -Seconds 2
    $elapsed += 2
    $state = $dte.Solution.SolutionBuild.BuildState
    Write-Host "  Waiting for build... ($elapsed`s / $BuildTimeoutSeconds`s) BuildState=$state"
}

$buildErrors = $dte.Solution.SolutionBuild.LastBuildInfo
Write-Host "Build finished. Error count: $buildErrors"

if ($buildErrors -gt 0) {
    Write-Host "`nBuild failed. Aborting." -ForegroundColor Red
    $dte.Quit()
    exit 1
}

Write-Host "Build succeeded." -ForegroundColor Green

# -- Step 3: Activate configuration & start TwinCAT ---------------------------

Write-Host "`nActivating configuration and starting TwinCAT..."
$systemManager = $dte.Solution.Projects.Item(1).Object

try {
    $systemManager.ActivateConfiguration()
    Write-Host "  Configuration activated." -ForegroundColor Green
}
catch {
    Write-Host "  Failed to activate configuration: $_" -ForegroundColor Red
    exit 1
}

try {
    $systemManager.StartRestartTwinCAT()
    Write-Host "  TwinCAT started." -ForegroundColor Green
}
catch {
    Write-Host "  Failed to start TwinCAT: $_" -ForegroundColor Red
    exit 1
}

# -- Step 4: Wait for TcUnit results in Output window -------------------------

Write-Host "`nWaiting for TcUnit results (timeout ${TestTimeoutSeconds}s, poll every ${TestPollIntervalSeconds}s)..."

$sentinels = @(
    "| Test suites:",
    "| Tests:",
    "| Successful tests:",
    "| Failed tests:",
    "| Duration:"
)

$elapsed = 0
$allFound = $false

while (-not $allFound) {
    if ($elapsed -ge $TestTimeoutSeconds) {
        Write-Host "TcUnit results timed out after $TestTimeoutSeconds seconds." -ForegroundColor Red
        exit 1
    }

    Start-Sleep -Seconds $TestPollIntervalSeconds
    $elapsed += $TestPollIntervalSeconds

    # Read text from the TwinCAT output pane
    $outputText = ""
    try {
        $outputText = [OutputWindowHelper]::ReadPane($dte, "TwinCAT")
    }
    catch {
        Write-Host "  Could not read TwinCAT output pane: $_" -ForegroundColor Yellow
    }

    $foundCount = 0
    foreach ($sentinel in $sentinels) {
        if ($outputText -like "*$sentinel*") {
            $foundCount++
        } else {
            Write-Host "    MISSING sentinel: '$sentinel'"
        }
    }

    Write-Host "  Polling... ($elapsed`s / $TestTimeoutSeconds`s) Found $foundCount/$($sentinels.Count) sentinels"

    if ($foundCount -eq $sentinels.Count) {
        $allFound = $true
    }
}

Start-Sleep -Seconds 5

Write-Host "TcUnit results detected." -ForegroundColor Green

# -- Step 5: Collect results from Output window --------------------------------

Write-Host "`nCollecting results from TwinCAT output pane..."

$outputText = ""
try {
    $outputText = [OutputWindowHelper]::ReadPane($dte, "TwinCAT")
}
catch {
    Write-Host "  Could not read TwinCAT output pane: $_" -ForegroundColor Yellow
}

Write-Host $outputText

# -- Step 6 placeholder -------------------------------------------------------

Write-Host "`nSteps 1-5 complete. Results collected."
# TODO: Step 6 - Write results to test-results.log, print summary, exit 0/1
