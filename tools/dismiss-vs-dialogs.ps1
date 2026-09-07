<#
.SYNOPSIS
    Dismisses Visual Studio's "File has been changed outside the environment" modal dialogs.

.DESCRIPTION
    Editing .TcPOU / .plcproj files on disk while the solution is open makes Visual Studio
    raise a modal "Reload the new file?" dialog per changed file. Those dialogs block the
    DTE automation object, so run-tests.ps1 cannot drive a build until they are gone.

    The dialogs are WPF windows (AutomationId "Microsoft.VisualStudio.MessageBox"), not Win32
    common dialogs, so they are located and clicked through UI Automation rather than through
    window messages. Only a dialog whose message text matches a known-safe pattern is clicked;
    every other Visual Studio dialog is reported and left alone.

.PARAMETER Button
    Which button to press. 'Yes' reloads the on-disk version, which is what you want after an
    external edit. 'No' keeps the in-memory version.

.PARAMETER TimeoutSeconds
    0 (default) sweeps until no further dialog is dismissed, then returns. A positive value
    keeps watching for that long, dismissing dialogs as they appear, which is useful while a
    build is starting and VS is still noticing changed files.

.PARAMETER Quiet
    Suppress per-dialog output.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools/dismiss-vs-dialogs.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools/dismiss-vs-dialogs.ps1 -TimeoutSeconds 20
#>
[CmdletBinding()]
param(
    [ValidateSet('Yes', 'No', 'Cancel')]
    [string]$Button = 'Yes',
    [int]$TimeoutSeconds = 0,
    [int]$PollIntervalMs = 250,
    [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

# Message text of the dialogs this script is allowed to click. Anything else is left for a human.
$KnownDialogPatterns = @(
    'has been changed outside the environment',
    'has been modified outside of the environment',
    'have been modified outside the environment',
    'been modified outside the source editor'
)

if (-not ('TcOtlp.Win' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

namespace TcOtlp {
    public static class Win {
        public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern bool EnumWindows(EnumProc cb, IntPtr param);
        [DllImport("user32.dll")]
        private static extern bool IsWindowVisible(IntPtr hWnd);
        [DllImport("user32.dll")]
        private static extern bool IsWindow(IntPtr hWnd);
        [DllImport("user32.dll")]
        private static extern int GetWindowThreadProcessId(IntPtr hWnd, out int pid);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetClassNameW(IntPtr hWnd, StringBuilder buf, int max);

        public static string ClassOf(IntPtr hWnd) {
            StringBuilder sb = new StringBuilder(256);
            GetClassNameW(hWnd, sb, sb.Capacity);
            return sb.ToString();
        }

        public static bool Alive(IntPtr hWnd) {
            return IsWindow(hWnd) && IsWindowVisible(hWnd);
        }

        // Visible top level WPF windows owned by one of the given processes. Visual Studio hosts
        // its message boxes in HwndWrapper windows, so the Win32 dialog class never appears.
        public static IntPtr[] CandidateWindows(int[] pids) {
            List<IntPtr> found = new List<IntPtr>();
            HashSet<int> wanted = new HashSet<int>(pids);
            EnumWindows(delegate(IntPtr hWnd, IntPtr param) {
                if (!IsWindowVisible(hWnd)) { return true; }
                int pid;
                GetWindowThreadProcessId(hWnd, out pid);
                if (!wanted.Contains(pid)) { return true; }
                if (!ClassOf(hWnd).StartsWith("HwndWrapper")) { return true; }
                found.Add(hWnd);
                return true;
            }, IntPtr.Zero);
            return found.ToArray();
        }
    }
}
'@
}

$AE = [System.Windows.Automation.AutomationElement]
$SCOPE_CHILDREN = [System.Windows.Automation.TreeScope]::Children
$SCOPE_DESC = [System.Windows.Automation.TreeScope]::Descendants

function New-IdCondition {
    param([string]$AutomationId)
    return New-Object System.Windows.Automation.PropertyCondition ($AE::AutomationIdProperty), $AutomationId
}

# The message body lives in a read-only TextBox with AutomationId "Text". Fall back to joining
# every descendant label so a differently shaped dialog is still reported rather than silently
# treated as unrecognised.
function Get-DialogMessage {
    param($Element)

    $body = $Element.FindFirst($SCOPE_DESC, (New-IdCondition -AutomationId 'Text'))
    if ($null -ne $body -and $body.Current.Name) { return $body.Current.Name }

    $textCond = New-Object System.Windows.Automation.PropertyCondition ($AE::ControlTypeProperty), ([System.Windows.Automation.ControlType]::Text)
    $parts = @()
    foreach ($t in $Element.FindAll($SCOPE_DESC, $textCond)) {
        if ($t.Current.Name) { $parts += $t.Current.Name }
    }
    return ($parts -join ' ')
}

function Get-DialogButton {
    param($Element, [string]$Label)

    $byId = $Element.FindFirst($SCOPE_CHILDREN, (New-IdCondition -AutomationId ($Label + 'Button')))
    if ($null -ne $byId) { return $byId }

    $btnCond = New-Object System.Windows.Automation.PropertyCondition ($AE::ControlTypeProperty), ([System.Windows.Automation.ControlType]::Button)
    foreach ($b in $Element.FindAll($SCOPE_CHILDREN, $btnCond)) {
        if ($b.Current.Name.Replace('_', '').Trim() -eq $Label) { return $b }
    }
    return $null
}

function Get-DevenvPids {
    $procs = @(Get-Process -Name devenv -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) { return @() }
    return @($procs | ForEach-Object { $_.Id })
}

function Invoke-DialogSweep {
    param([int[]]$Pids, [string]$ClickLabel)

    $dismissed = 0
    foreach ($hWnd in [TcOtlp.Win]::CandidateWindows($Pids)) {
        $element = $null
        try { $element = $AE::FromHandle($hWnd) } catch { continue }
        if ($null -eq $element) { continue }

        # Only Visual Studio's own message boxes; the main window and the glow border frames
        # share the same window class.
        if ($element.Current.AutomationId -ne 'Microsoft.VisualStudio.MessageBox') { continue }

        $message = Get-DialogMessage -Element $element
        $matched = $false
        foreach ($pattern in $KnownDialogPatterns) {
            if ($message -like "*$pattern*") { $matched = $true; break }
        }

        if (-not $matched) {
            if (-not $Quiet) {
                $summary = ($message -replace '\s+', ' ').Trim()
                if ($summary.Length -gt 160) { $summary = $summary.Substring(0, 160) + '...' }
                Write-Host "SKIP  unrecognised dialog: $summary" -ForegroundColor Yellow
            }
            continue
        }

        $button = Get-DialogButton -Element $element -Label $ClickLabel
        if ($null -eq $button) {
            Write-Host "SKIP  no '$ClickLabel' button on the reload dialog" -ForegroundColor Yellow
            continue
        }

        # The first line of the message is the document path.
        $file = ($message -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 } | Select-Object -First 1)
        if (-not $file) { $file = '(unnamed document)' }

        $pattern = $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $pattern.Invoke()

        $waited = 0
        while ([TcOtlp.Win]::Alive($hWnd) -and $waited -lt 3000) {
            Start-Sleep -Milliseconds 100
            $waited += 100
        }

        if ([TcOtlp.Win]::Alive($hWnd)) {
            Write-Host "FAIL  could not close reload dialog for $file" -ForegroundColor Red
        }
        else {
            $dismissed++
            if (-not $Quiet) { Write-Host "$ClickLabel   $file" -ForegroundColor Green }
        }
    }
    return $dismissed
}

$devenvPids = @(Get-DevenvPids)
if ($devenvPids.Count -eq 0) {
    Write-Host 'No devenv.exe process is running; nothing to dismiss.'
    exit 0
}

$total = 0
if ($TimeoutSeconds -le 0) {
    # Dialogs stack one per changed file, and the next one only becomes reachable once the
    # current one closes, so sweep until a pass finds nothing left to do.
    do {
        $round = Invoke-DialogSweep -Pids $devenvPids -ClickLabel $Button
        $total += $round
    } while ($round -gt 0)
}
else {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $total += Invoke-DialogSweep -Pids $devenvPids -ClickLabel $Button
        Start-Sleep -Milliseconds $PollIntervalMs
    }
}

Write-Host "Dismissed $total dialog(s)."
exit 0
