<#
.SYNOPSIS
    Automates TcUnit test execution for the TcOtlp project via DTE COM.
.DESCRIPTION
    Attaches to a running TcXaeShell instance, reloads the solution from disk,
    builds, activates TwinCAT, and polls the TwinCAT output pane for TcUnit
    results.

    Every wait is condition-based rather than a fixed sleep: each phase polls a
    cheap DTE property on a short interval and continues the moment the
    condition is met, bounded by a stopwatch-measured timeout.
#>
param(
    [int]$BuildTimeoutSeconds = 120,
    [int]$TestTimeoutSeconds  = 120,
    # How often to poll DTE while waiting. The polled calls are cheap, so this
    # can be short without loading the IDE.
    [int]$PollIntervalMs      = 250,
    # Once the TcUnit sentinels appear, wait for the pane to stop growing for
    # this long before reading final results.
    [int]$SettleMs            = 1000,
    # Lines read from the end of the output pane while polling. The TcUnit
    # summary block is the last thing printed, so the tail always contains it.
    [int]$TailLines           = 400,
    # Use an incremental build instead of a full rebuild.
    [switch]$IncrementalBuild,
    # Check the otel PLC project, save it as bin/otel.library and install it into
    # the library repository before testing. The test project references the
    # installed TcOtlp library rather than the otel sources, so library changes
    # are only exercised by the tests after this step.
    [switch]$InstallLibrary
)

$ErrorActionPreference = "Stop"

$solutionPath = Join-Path $PSScriptRoot "..\TcOtlp\TcOtlp.sln"

if (-not (Test-Path $solutionPath)) {
    Write-Host "Solution not found: $solutionPath" -ForegroundColor Red
    exit 1
}

# -- Load EnvDTE interop assemblies --------------------------------------------
# Loading these assemblies enables PowerShell to resolve the EnvDTE80.ToolWindows
# interface so that $dte.ToolWindows.ErrorList returns a usable ErrorList object
# with ShowErrors/ShowWarnings/ShowMessages properties and ErrorItems collection.

$publicAssemblies = "C:\Program Files\Beckhoff\TcXaeShell\Common7\IDE\PublicAssemblies"
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

# C# helper for Output Window COM interop (PowerShell can't marshal these interfaces).
#
# Pane reads use EditPoint.GetText rather than TextSelection.SelectAll for two
# reasons: SelectAll transfers the whole pane across the COM boundary on every
# poll, so its cost grows with output size, and it clobbers whatever the user had
# selected in the output window. GetLineCount is the cheap change-detector the
# poll loop uses so pane text is only transferred when something was printed.
Add-Type -TypeDefinition @"
using EnvDTE;
using EnvDTE80;
using System;
using System.Runtime.InteropServices;
using System.Text;

// VS rejects incoming COM calls while it is busy (RPC_E_CALL_REJECTED /
// RPC_E_SERVERCALL_RETRYLATER). Without a message filter registered, those
// rejections surface as exceptions to us and can raise a modal "component busy"
// dialog in the IDE. With one, the COM layer retries transparently.
// CoRegisterMessageFilter requires an STA thread; powershell.exe is STA by
// default, and Register() reports failure rather than throwing if it is not.
[ComImport, Guid("00000016-0000-0000-C000-000000000046"),
 InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IOleMessageFilter {
    [PreserveSig] int HandleInComingCall(int dwCallType, IntPtr hTaskCaller, int dwTickCount, IntPtr lpInterfaceInfo);
    [PreserveSig] int RetryRejectedCall(IntPtr hTaskCallee, int dwTickCount, int dwRejectType);
    [PreserveSig] int MessagePending(IntPtr hTaskCallee, int dwTickCount, int dwPendingType);
}
public class MessageFilter : IOleMessageFilter {
    // Give up on a rejected call after this long so a genuinely stuck IDE
    // surfaces an error instead of blocking forever.
    private const int RetryTimeoutMs = 30000;
    private const int RetryDelayMs = 200;

    [DllImport("Ole32.dll")]
    private static extern int CoRegisterMessageFilter(IOleMessageFilter newFilter, out IOleMessageFilter oldFilter);

    public static bool Register() {
        IOleMessageFilter old = null;
        return CoRegisterMessageFilter(new MessageFilter(), out old) == 0;
    }
    public static void Revoke() {
        IOleMessageFilter old = null;
        try { CoRegisterMessageFilter(null, out old); } catch { }
    }
    int IOleMessageFilter.HandleInComingCall(int dwCallType, IntPtr hTaskCaller, int dwTickCount, IntPtr lpInterfaceInfo) {
        return 0;   // SERVERCALL_ISHANDLED
    }
    int IOleMessageFilter.RetryRejectedCall(IntPtr hTaskCallee, int dwTickCount, int dwRejectType) {
        // 0 = SERVERCALL_REJECTED, 2 = SERVERCALL_RETRYLATER. VS reports both
        // while busy, so retry either until the budget runs out; -1 cancels.
        if ((dwRejectType == 0 || dwRejectType == 2) && dwTickCount < RetryTimeoutMs) {
            return RetryDelayMs;
        }
        return -1;
    }
    int IOleMessageFilter.MessagePending(IntPtr hTaskCallee, int dwTickCount, int dwPendingType) {
        return 2;   // PENDINGMSG_WAITDEFPROCESS
    }
}
public static class ErrorListHelper {
    public static string GetErrors(object dte) {
        DTE2 d = (DTE2)dte;
        var errorList = d.ToolWindows.ErrorList;
        errorList.ShowErrors = true;
        errorList.ShowWarnings = true;
        errorList.ShowMessages = false;
        var items = errorList.ErrorItems;
        var sb = new StringBuilder();
        for (int i = 1; i <= items.Count; i++) {
            var item = items.Item(i);
            string severity = item.ErrorLevel == vsBuildErrorLevel.vsBuildErrorLevelHigh ? "Error"
                            : item.ErrorLevel == vsBuildErrorLevel.vsBuildErrorLevelMedium ? "Warning"
                            : "Message";
            sb.AppendLine(string.Format("[{0}] {1} ({2}, Line {3}): {4}",
                severity, item.FileName, item.Project, item.Line, item.Description));
        }
        return sb.ToString();
    }
}
public static class OutputWindowHelper {
    private static OutputWindowPane FindPane(object dte, string paneName) {
        DTE d = (DTE)dte;
        Window win = d.Windows.Item(Constants.vsWindowKindOutput);
        OutputWindow ow = (OutputWindow)win.Object;
        foreach (OutputWindowPane pane in ow.OutputWindowPanes) {
            if (pane.Name == paneName) { return pane; }
        }
        return null;
    }
    public static void ActivatePane(object dte, string paneName) {
        OutputWindowPane pane = FindPane(dte, paneName);
        if (pane != null) { pane.Activate(); }
    }
    public static void ClearPane(object dte, string paneName) {
        OutputWindowPane pane = FindPane(dte, paneName);
        if (pane != null) { pane.Clear(); }
    }
    // Cheap: a few COM calls, no text transfer. -1 means the pane does not exist yet.
    public static int GetLineCount(object dte, string paneName) {
        OutputWindowPane pane = FindPane(dte, paneName);
        if (pane == null) { return -1; }
        return pane.TextDocument.EndPoint.Line;
    }
    public static string ReadTail(object dte, string paneName, int tailLines) {
        OutputWindowPane pane = FindPane(dte, paneName);
        if (pane == null) { return ""; }
        TextDocument doc = pane.TextDocument;
        int start = doc.EndPoint.Line - tailLines;
        if (start < 1) { start = 1; }
        EditPoint ep = doc.StartPoint.CreateEditPoint();
        ep.MoveToLineAndOffset(start, 1);
        return ep.GetText(doc.EndPoint);
    }
    public static string ReadPane(object dte, string paneName) {
        OutputWindowPane pane = FindPane(dte, paneName);
        if (pane == null) { return ""; }
        TextDocument doc = pane.TextDocument;
        EditPoint ep = doc.StartPoint.CreateEditPoint();
        return ep.GetText(doc.EndPoint);
    }
}
"@ -ReferencedAssemblies @(
    $interopDll
)
Write-Host "  Loaded OutputWindowHelper" -ForegroundColor Green

# The PLC project node's IDispatch only exposes its default interface, so
# SaveAsLibrary and CheckAllObjects have to be reached through a typed cast.
$sysManagerLib = "C:\Windows\Microsoft.NET\assembly\GAC_MSIL\TCatSysManagerLib\v4.0_3.4.0.0__180016cd49e5e8c3\TCatSysManagerLib.dll"
if ($InstallLibrary) {
    Add-Type -TypeDefinition @"
using TCatSysManagerLib;
public static class PlcLibraryHelper {
    private static ITcPlcIECProject2 Project(object sysManager, string treePath) {
        return (ITcPlcIECProject2)((ITcSysManager)sysManager).LookupTreeItem(treePath);
    }
    public static bool CheckAllObjects(object sysManager, string treePath) {
        return Project(sysManager, treePath).CheckAllObjects();
    }
    public static void SaveAndInstall(object sysManager, string treePath, string libraryPath) {
        Project(sysManager, treePath).SaveAsLibrary(libraryPath, true);
    }
}
"@ -ReferencedAssemblies @($sysManagerLib)
    Write-Host "  Loaded PlcLibraryHelper" -ForegroundColor Green
}

if ([MessageFilter]::Register()) {
    Write-Host "  Registered COM message filter." -ForegroundColor Green
} else {
    Write-Host "  Could not register COM message filter; relying on call retries." -ForegroundColor Yellow
}

# -- Helpers ------------------------------------------------------------------

# True when the failure is VS rejecting the call because it is busy, rather than
# a real error. PowerShell wraps a COMException thrown from a static .NET method
# in a MethodInvocationException, so match on the inner exception chain and not
# on the type of the outer error.
function Test-DteBusyError {
    param([Parameter(Mandatory)]$ErrorRecord)
    $ex = $ErrorRecord.Exception
    while ($ex) {
        if ($ex -is [System.Runtime.InteropServices.COMException]) {
            $hr = $ex.HResult -band 0xFFFFFFFF
            # RPC_E_CALL_REJECTED / RPC_E_SERVERCALL_RETRYLATER
            if ($hr -eq 0x80010001 -or $hr -eq 0x8001010A) { return $true }
        }
        $ex = $ex.InnerException
    }
    return $false
}

# The message filter handles most rejections at the COM layer; this is the
# backstop for the ones it cancels after its own retry budget.
function Invoke-Dte {
    param(
        [Parameter(Mandatory)][scriptblock]$Action,
        [int]$TimeoutSeconds = 20,
        [int]$RetryMs = 200
    )
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        try {
            return & $Action
        }
        catch {
            if (-not (Test-DteBusyError $_)) { throw }
            if ($sw.Elapsed.TotalSeconds -ge $TimeoutSeconds) { throw }
            Start-Sleep -Milliseconds $RetryMs
        }
    }
}

# Poll $Condition until it returns true or the timeout expires.
# Returns $true on success, $false on timeout.
function Wait-For {
    param(
        [Parameter(Mandatory)][scriptblock]$Condition,
        [Parameter(Mandatory)][int]$TimeoutSeconds,
        [int]$IntervalMs = 250,
        [string]$Label = "condition",
        # Emit a progress line at most this often so a fast poll interval does
        # not flood the console.
        [int]$ReportEveryMs = 5000
    )
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $lastReport = 0
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        if (& $Condition) {
            Write-Host ("  {0}: ready after {1:N1}s" -f $Label, $sw.Elapsed.TotalSeconds) -ForegroundColor DarkGray
            return $true
        }
        if ($sw.ElapsedMilliseconds - $lastReport -ge $ReportEveryMs) {
            $lastReport = $sw.ElapsedMilliseconds
            Write-Host ("  waiting for {0}... ({1:N0}s / {2}s)" -f $Label, $sw.Elapsed.TotalSeconds, $TimeoutSeconds)
        }
        Start-Sleep -Milliseconds $IntervalMs
    }
    return $false
}

# Editing .TcPOU files on disk while the solution is open makes VS raise a modal
# "Reload the new file?" message box per changed file. Those are modal to the IDE,
# so every DTE call blocks until they are gone -- including the attach below. They
# have to be cleared through the UI, before DTE is touched at all.
function Clear-VsDialogs {
    $dismisser = Join-Path $PSScriptRoot "dismiss-vs-dialogs.ps1"
    if (-not (Test-Path $dismisser)) { return }
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $dismisser -Quiet | Out-Null
    }
    catch {
        Write-Host "  Could not sweep VS dialogs (non-fatal): $_" -ForegroundColor Yellow
    }
}

# -- Step 1: Attach to running TcXaeShell instance and open solution -------------

Clear-VsDialogs

Write-Host "Attaching to running TcXaeShell instance..."

$dte = $null
try {
    $dte = [System.Runtime.InteropServices.Marshal]::GetActiveObject("TcXaeShell.DTE.17.0")
    Write-Host "  Attached to running TcXaeShell instance." -ForegroundColor Green
}
catch {
    Write-Host "  Could not attach to running TcXaeShell: $_" -ForegroundColor Red
    Write-Host "  Make sure the 64-bit TwinCAT XAE Shell (TcXaeShell) is open." -ForegroundColor Yellow
    exit 1
}

# Suppress modal dialogs (reload prompts, save prompts, "component busy") for the
# duration of the run, then hand the IDE back to the user as we found it.
$originalSuppressUI = $null
$originalAutoload   = $null
try { $originalSuppressUI = $dte.SuppressUI; $dte.SuppressUI = $true } catch {}
try {
    Invoke-Dte {
        $docProps = $dte.Properties("Environment", "Documents")
        $script:originalAutoload = $docProps.Item("AutoloadExternalChanges").Value
        $docProps.Item("AutoloadExternalChanges").Value = $true
    }
}
catch {
    Write-Host "  Could not set AutoloadExternalChanges (non-fatal): $_" -ForegroundColor Yellow
}

function Restore-VsSettings {
    try { [MessageFilter]::Revoke() } catch {}
    if ($null -ne $originalSuppressUI) {
        try { $dte.SuppressUI = $originalSuppressUI } catch {}
    }
    if ($null -ne $originalAutoload) {
        try { $dte.Properties("Environment", "Documents").Item("AutoloadExternalChanges").Value = $originalAutoload } catch {}
    }
}

function Stop-Script {
    param([int]$Code)
    Restore-VsSettings
    exit $Code
}

# Close open editor windows before touching the solution. A file that is not open
# in an editor cannot raise a "modified outside the environment" prompt, and this
# also makes Solution.Close faster.
try {
    Invoke-Dte { $dte.Documents.CloseAll([EnvDTE.vsSaveChanges]::vsSaveChangesNo) }
    Write-Host "  Closed open documents." -ForegroundColor Green
}
catch {
    Write-Host "  Could not close open documents (non-fatal): $_" -ForegroundColor Yellow
}

# Close and re-open the solution so VS picks up any files changed on disk.
# Without this, VS may use stale cached versions of .TcPOU files and ignore
# edits made outside the IDE (e.g. by code-gen scripts or an agent).
$currentSln = Invoke-Dte { $dte.Solution.FullName }
if ($currentSln -and (Test-Path $currentSln)) {
    Write-Host "Closing solution to force file refresh..."
    Invoke-Dte { $dte.Solution.Close($false) }   # $false = don't save pending changes
    $closed = Wait-For -Condition { -not (Invoke-Dte { $dte.Solution.IsOpen }) } `
                       -TimeoutSeconds 60 -IntervalMs $PollIntervalMs -Label "solution close"
    if (-not $closed) {
        Write-Host "Solution did not close within 60s." -ForegroundColor Red
        Stop-Script 1
    }
}

function Open-Solution {
    Write-Host "Opening solution: $solutionPath"
    Invoke-Dte { $dte.Solution.Open($solutionPath) }
    $opened = Wait-For -Condition { Invoke-Dte { $dte.Solution.IsOpen -and $dte.Solution.Projects.Count -gt 0 } } `
                       -TimeoutSeconds 120 -IntervalMs $PollIntervalMs -Label "solution open"
    if (-not $opened) {
        Write-Host "Solution did not finish opening within 120s." -ForegroundColor Red
        Stop-Script 1
    }
    Write-Host "Solution opened." -ForegroundColor Green
}

# The TwinCAT project is the one whose automation object is the system manager.
function Get-SystemManager {
    $projectCount = Invoke-Dte { $dte.Solution.Projects.Count }
    for ($i = 1; $i -le $projectCount; $i++) {
        $proj = Invoke-Dte { $dte.Solution.Projects.Item($i) }
        Write-Host "  Project $i`: $($proj.Name) Kind=$($proj.Kind)"
        if ($proj.Object -and ($proj.Object | Get-Member -Name "StartRestartTwinCAT" -ErrorAction SilentlyContinue)) {
            Write-Host "  Found TwinCAT system manager in project '$($proj.Name)'" -ForegroundColor Green
            return $proj.Object
        }
    }
    return $null
}

Open-Solution

# -- Optional: rebuild and install the TcOtlp library -------------------------

if ($InstallLibrary) {
    $libraryTreePath = "TIPC^otel^otel Project"
    $libraryPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\bin\otel.library"))

    Write-Host "`nChecking library project '$libraryTreePath'..."
    $libSystemManager = Get-SystemManager
    if (-not $libSystemManager) {
        Write-Host "  Could not find TwinCAT system manager in any project." -ForegroundColor Red
        Stop-Script 1
    }
    $checked = Invoke-Dte -TimeoutSeconds 300 -Action { [PlcLibraryHelper]::CheckAllObjects($libSystemManager, $libraryTreePath) }
    if (-not $checked) {
        Write-Host "  The library project has errors; not installing it." -ForegroundColor Red
        try { Write-Host ([ErrorListHelper]::GetErrors($dte)) -ForegroundColor Red } catch { }
        Stop-Script 1
    }
    Write-Host "  Library project checked without errors." -ForegroundColor Green

    Write-Host "Saving and installing $libraryPath..."
    # SaveAsLibrary refuses to overwrite, so drop the previous build output first.
    if (Test-Path $libraryPath) { Remove-Item $libraryPath -Force }
    Invoke-Dte -TimeoutSeconds 300 -Action { [PlcLibraryHelper]::SaveAndInstall($libSystemManager, $libraryTreePath, $libraryPath) }
    Write-Host "  Library installed." -ForegroundColor Green

    # Reopen so the test project resolves its TcOtlp placeholder against the
    # freshly installed library instead of the one loaded with the solution.
    Write-Host "Reopening solution to pick up the installed library..."
    Invoke-Dte { $dte.Solution.Close($false) }
    $closed = Wait-For -Condition { -not (Invoke-Dte { $dte.Solution.IsOpen }) } `
                       -TimeoutSeconds 60 -IntervalMs $PollIntervalMs -Label "solution close"
    if (-not $closed) {
        Write-Host "Solution did not close within 60s." -ForegroundColor Red
        Stop-Script 1
    }
    Open-Solution
}

# -- Switch Output window to TwinCAT pane --------------------------------------
try {
    Invoke-Dte { $dte.ExecuteCommand("View.Output") }
    [OutputWindowHelper]::ActivatePane($dte, "TwinCAT")
    Write-Host "Output window switched to TwinCAT pane." -ForegroundColor Green
}
catch {
    Write-Host "Could not switch Output window to TwinCAT pane: $_" -ForegroundColor Yellow
}

# Clear the TwinCAT output pane before building. This also resets the line count
# the poll loop uses to detect new output.
try {
    [OutputWindowHelper]::ClearPane($dte, "TwinCAT")
    Write-Host "TwinCAT output pane cleared." -ForegroundColor Green
}
catch {
    Write-Host "Could not clear TwinCAT output pane: $_" -ForegroundColor Yellow
}

# -- Step 2: Build solution ---------------------------------------------------

# Re-opening the solution can surface a second round of reload prompts for files
# the IDE only noticed once they were loaded again.
Clear-VsDialogs

$buildCommand = if ($IncrementalBuild) { "Build.BuildSolution" } else { "Build.RebuildSolution" }
Write-Host "Starting build ($buildCommand)..."
Invoke-Dte -TimeoutSeconds 30 -Action { $dte.ExecuteCommand($buildCommand) }

# ExecuteCommand returns before the build starts, so wait for InProgress first --
# otherwise the stale Done left by the previous build reads as instant success.
# This exits as soon as the build starts (~2s typically), so the timeout is only
# reached if the build was so fast we missed the InProgress window entirely,
# which is not an error worth failing on.
Wait-For -Condition {
    (Invoke-Dte { $dte.Solution.SolutionBuild.BuildState }) -eq [EnvDTE.vsBuildState]::vsBuildStateInProgress
} -TimeoutSeconds 15 -IntervalMs $PollIntervalMs -Label "build start" -ReportEveryMs 60000 | Out-Null

$buildSw = [System.Diagnostics.Stopwatch]::StartNew()
$built = Wait-For -Condition {
    (Invoke-Dte { $dte.Solution.SolutionBuild.BuildState }) -eq [EnvDTE.vsBuildState]::vsBuildStateDone
} -TimeoutSeconds $BuildTimeoutSeconds -IntervalMs $PollIntervalMs -Label "build"
if (-not $built) {
    Write-Host "Build timed out after $BuildTimeoutSeconds seconds." -ForegroundColor Red
    Stop-Script 1
}

$buildErrors = Invoke-Dte { $dte.Solution.SolutionBuild.LastBuildInfo }
Write-Host ("Build finished in {0:N1}s. Error count: {1}" -f $buildSw.Elapsed.TotalSeconds, $buildErrors)

if ($buildErrors -gt 0) {
    Write-Host "`nBuild failed with $buildErrors error(s):" -ForegroundColor Red
    try {
        $errorDetails = [ErrorListHelper]::GetErrors($dte)
        if ($errorDetails) {
            Write-Host $errorDetails -ForegroundColor Red
        } else {
            # TcXaeShell often leaves the Error List empty; the Build pane still has the compiler lines.
            $buildErrorLines = [OutputWindowHelper]::ReadPane($dte, "Build") -split "`r?`n" |
                Where-Object { $_ -match ': error' }
            if ($buildErrorLines) {
                $buildErrorLines | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
            } else {
                Write-Host "  (No error details available from Error List or Build pane)" -ForegroundColor Yellow
            }
        }
    }
    catch {
        Write-Host "  Could not read Error List: $_" -ForegroundColor Yellow
    }
    Stop-Script 1
}

Write-Host "Build succeeded." -ForegroundColor Green

# -- Step 3: Start TwinCAT ----------------------------------------------------

Write-Host "`nStarting TwinCAT..."
$systemManager = Get-SystemManager

if (-not $systemManager) {
    Write-Host "  Could not find TwinCAT system manager in any project." -ForegroundColor Red
    Stop-Script 1
}

try {
    Write-Host "  Activating rebuilt TwinCAT configuration..."
    Invoke-Dte -TimeoutSeconds 60 -Action { $systemManager.ActivateConfiguration() }
    Write-Host "  TwinCAT configuration activated." -ForegroundColor Green
}
catch {
    Write-Host "  Failed to activate the rebuilt TwinCAT configuration: $_" -ForegroundColor Red
    Stop-Script 1
}

# Record the pane size after activation so the poll loop below only reacts to
# output produced by the run that follows.
$baselineLines = 0
try { $baselineLines = Invoke-Dte { [OutputWindowHelper]::GetLineCount($dte, "TwinCAT") } } catch { }

try {
    Invoke-Dte -TimeoutSeconds 60 -Action { $systemManager.StartRestartTwinCAT() }
    Write-Host "  TwinCAT started." -ForegroundColor Green
}
catch {
    Write-Host "  Failed to start TwinCAT: $_" -ForegroundColor Red
    Stop-Script 1
}

# -- Step 4: Wait for TcUnit results in Output window -------------------------

Write-Host "`nWaiting for TcUnit results (timeout ${TestTimeoutSeconds}s, poll every ${PollIntervalMs}ms)..."

$sentinels = @(
    "| Test suites:",
    "| Tests:",
    "| Successful tests:",
    "| Failed tests:",
    "| Duration:"
)

$testSw      = [System.Diagnostics.Stopwatch]::StartNew()
$lastLines   = $baselineLines
$lastReport  = 0
$allFound    = $false
$foundCount  = 0
$settleSw    = $null
$lastTail    = $null
$probeFailed = $false

while ($testSw.Elapsed.TotalSeconds -lt $TestTimeoutSeconds) {
    Start-Sleep -Milliseconds $PollIntervalMs

    # Cheap change detection so the pane text is only transferred when something
    # was actually printed. -1 means the probe itself failed (pane missing, or
    # VS still rejecting calls) -- that must NOT be read as "no new output", or
    # the loop waits out the full timeout while the tests are running fine.
    $lines = -1
    try {
        $lines = Invoke-Dte -TimeoutSeconds 5 -Action { [OutputWindowHelper]::GetLineCount($dte, "TwinCAT") }
    }
    catch {
        if (-not $probeFailed) {
            $probeFailed = $true
            Write-Host "  Line-count probe unavailable ($($_.Exception.Message.Trim())); falling back to tail reads." -ForegroundColor Yellow
        }
    }

    if ($lines -ge 0 -and $lines -le $lastLines) {
        # Pane is genuinely quiet. If the sentinels are already present, that
        # quiet is exactly what we were waiting for.
        if ($allFound -and $settleSw -and $settleSw.ElapsedMilliseconds -ge $SettleMs) { break }
        if ($testSw.ElapsedMilliseconds - $lastReport -ge 5000) {
            $lastReport = $testSw.ElapsedMilliseconds
            Write-Host ("  waiting for TcUnit output... ({0:N0}s / {1}s) {2} lines" -f `
                $testSw.Elapsed.TotalSeconds, $TestTimeoutSeconds, $lines)
        }
        continue
    }

    $tail = $null
    try {
        $tail = Invoke-Dte -TimeoutSeconds 5 -Action { [OutputWindowHelper]::ReadTail($dte, "TwinCAT", $TailLines) }
    }
    catch {
        continue    # transient; try again next tick rather than treating it as settled
    }

    # With the line count available, growth is the change signal. Without it,
    # fall back to comparing the tail text itself.
    $changed = if ($lines -ge 0) { $lines -gt $lastLines } else { $tail -ne $lastTail }
    if ($lines -ge 0) { $lastLines = $lines }
    $lastTail = $tail
    if ($changed) { $settleSw = [System.Diagnostics.Stopwatch]::StartNew() }

    $foundCount = 0
    foreach ($sentinel in $sentinels) {
        if ($tail.Contains($sentinel)) { $foundCount++ }
    }
    $allFound = ($foundCount -eq $sentinels.Count)

    if ($allFound -and -not $changed -and $settleSw -and $settleSw.ElapsedMilliseconds -ge $SettleMs) { break }

    if ($testSw.ElapsedMilliseconds - $lastReport -ge 5000) {
        $lastReport = $testSw.ElapsedMilliseconds
        Write-Host ("  polling... ({0:N0}s / {1}s) {2} lines, {3}/{4} sentinels" -f `
            $testSw.Elapsed.TotalSeconds, $TestTimeoutSeconds, $lines, $foundCount, $sentinels.Count)
    }
}

if (-not $allFound) {
    Write-Host "TcUnit results timed out after $TestTimeoutSeconds seconds." -ForegroundColor Red
    Write-Host "  Missing sentinels:" -ForegroundColor Yellow
    $tail = ""
    try { $tail = [OutputWindowHelper]::ReadTail($dte, "TwinCAT", $TailLines) } catch { }
    foreach ($sentinel in $sentinels) {
        if (-not $tail.Contains($sentinel)) { Write-Host "    '$sentinel'" -ForegroundColor Yellow }
    }
    Stop-Script 1
}

Write-Host ("TcUnit results detected after {0:N1}s." -f $testSw.Elapsed.TotalSeconds) -ForegroundColor Green

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

# -- Step 6: Report & Cleanup -------------------------------------------------

# Write results to log file
$logPath = Join-Path $PSScriptRoot "test-results.log"
$outputText | Out-File -FilePath $logPath -Encoding UTF8
Write-Host "Results written to $logPath" -ForegroundColor Green

# Parse failed test count from output
$failedCount = 0
if ($outputText -match '\|\s*Failed tests:\s*(\d+)') {
    $failedCount = [int]$Matches[1]
}

# Print summary
Write-Host "`n========== Test Summary ==========" -ForegroundColor Cyan
$summaryLines = $outputText -split "`r?`n" | Where-Object { $_ -match '\|\s*(Test suites|Tests|Successful tests|Failed tests|Duration):' }
foreach ($line in $summaryLines) {
    Write-Host $line
}
Write-Host "==================================" -ForegroundColor Cyan

# Exit with appropriate code
if ($failedCount -gt 0) {
    Write-Host "`n$failedCount test(s) failed." -ForegroundColor Red
    Stop-Script 1
} else {
    Write-Host "`nAll tests passed." -ForegroundColor Green
    Stop-Script 0
}
