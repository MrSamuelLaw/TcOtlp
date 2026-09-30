<#
.SYNOPSIS
    Reads and prints the contents of the TwinCAT output pane from a running TcXaeShell instance.
#>
param(
    [string]$PaneName = "TwinCAT",
    [switch]$All,
    [switch]$ListPanes
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
using System.Text;
public static class OutputWindowHelper {
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
    public static string[] ListPanes(object dte) {
        DTE d = (DTE)dte;
        Window win = d.Windows.Item(Constants.vsWindowKindOutput);
        OutputWindow ow = (OutputWindow)win.Object;
        string[] names = new string[ow.OutputWindowPanes.Count];
        for (int i = 0; i < ow.OutputWindowPanes.Count; i++) {
            names[i] = ow.OutputWindowPanes.Item(i + 1).Name;
        }
        return names;
    }
    public static string ReadAllPanes(object dte) {
        DTE d = (DTE)dte;
        Window win = d.Windows.Item(Constants.vsWindowKindOutput);
        OutputWindow ow = (OutputWindow)win.Object;
        StringBuilder sb = new StringBuilder();
        foreach (OutputWindowPane pane in ow.OutputWindowPanes) {
            try {
                TextDocument doc = pane.TextDocument;
                TextSelection sel = (TextSelection)doc.Selection;
                sel.SelectAll();
                string text = sel.Text;
                if (!string.IsNullOrWhiteSpace(text)) {
                    sb.AppendLine("===== " + pane.Name + " =====");
                    sb.AppendLine(text);
                    sb.AppendLine();
                }
            } catch {
                // Skip panes that don't support text reading
            }
        }
        return sb.ToString();
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

# -- Read the pane(s) ----------------------------------------------------------
try {
    if ($ListPanes) {
        $panes = [OutputWindowHelper]::ListPanes($dte)
        Write-Host "Available output panes:" -ForegroundColor Cyan
        foreach ($p in $panes) { Write-Host "  - $p" }
    } elseif ($All) {
        $outputText = [OutputWindowHelper]::ReadAllPanes($dte)
        Write-Output $outputText
    } else {
        $outputText = [OutputWindowHelper]::ReadPane($dte, $PaneName)
        Write-Output $outputText
    }
} catch {
    Write-Host "Could not read output pane: $_" -ForegroundColor Red
    exit 1
}
