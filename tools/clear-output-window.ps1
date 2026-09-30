<#
.SYNOPSIS
    Clears the TwinCAT output pane in a running TcXaeShell instance.
#>
param(
    [string]$PaneName = "TwinCAT"
)

$ErrorActionPreference = "Stop"

# -- Load EnvDTE interop assemblies --------------------------------------------
$publicAssemblies = "C:\Program Files\Beckhoff\TcXaeShell\Common7\IDE\PublicAssemblies"
$interopDll = Join-Path $publicAssemblies "Microsoft.VisualStudio.Interop.dll"
foreach ($dll in @("envdte.dll", "envdte80.dll", "Microsoft.VisualStudio.Interop.dll")) {
    $dllPath = Join-Path $publicAssemblies $dll
    if (Test-Path $dllPath) {
        Add-Type -Path $dllPath
    } else {
        Write-Host "WARNING: $dllPath not found" -ForegroundColor Yellow
    }
}

Add-Type -TypeDefinition @"
using EnvDTE;
public static class OutputWindowHelper {
    public static void ClearPane(object dte, string paneName) {
        DTE d = (DTE)dte;
        Window win = d.Windows.Item(Constants.vsWindowKindOutput);
        OutputWindow ow = (OutputWindow)win.Object;
        foreach (OutputWindowPane pane in ow.OutputWindowPanes) {
            if (pane.Name == paneName) {
                pane.Clear();
                return;
            }
        }
    }
}
"@ -ReferencedAssemblies @($interopDll)

# -- Attach to running TcXaeShell instance ---------------------------------------
$dte = $null
try {
    $dte = [System.Runtime.InteropServices.Marshal]::GetActiveObject("TcXaeShell.DTE.17.0")
} catch {
    Write-Host "Could not attach to running TcXaeShell: $_" -ForegroundColor Red
    Write-Host "Make sure the 64-bit TwinCAT XAE Shell (TcXaeShell) is open." -ForegroundColor Yellow
    exit 1
}

# -- Clear the pane ------------------------------------------------------------
try {
    [OutputWindowHelper]::ClearPane($dte, $PaneName)
    Write-Host "$PaneName output pane cleared." -ForegroundColor Green
} catch {
    Write-Host "Could not clear $PaneName output pane: $_" -ForegroundColor Red
    exit 1
}
