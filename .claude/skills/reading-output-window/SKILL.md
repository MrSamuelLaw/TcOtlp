---
name: reading-output-window
description: "Reads the Visual Studio TwinCAT output pane via read-output-window.ps1. Use when asked to read, show, or check the TwinCAT output window contents."
---

# Reading the TwinCAT Output Window

Reads the contents of the TwinCAT output pane from a running TcXaeShell instance.

## Prerequisites

- The 64-bit TwinCAT XAE Shell (`TcXaeShell.exe`) must be **open and running**.

## How to Read the Output

Execute from the workspace root:

```powershell
powershell -ExecutionPolicy Bypass -File tools/read-output-window.ps1
```

### Optional Parameters

| Parameter | Default | Description |
|---|---|---|
| `-PaneName` | `TwinCAT` | Name of the VS output pane to read |
| `-All` | off | Read all non-empty output panes |
| `-ListPanes` | off | List available output pane names |

Example reading a different pane:

```powershell
powershell -ExecutionPolicy Bypass -File tools/read-output-window.ps1 -PaneName "Build"
```

Read all output panes at once:

```powershell
powershell -ExecutionPolicy Bypass -File tools/read-output-window.ps1 -All
```

List available pane names:

```powershell
powershell -ExecutionPolicy Bypass -File tools/read-output-window.ps1 -ListPanes
```

## What the Script Does

1. **Loads** EnvDTE interop assemblies from the TcXaeShell install directory.
2. **Attaches** to a running TcXaeShell instance via DTE COM (`TcXaeShell.DTE.17.0`).
3. **Reads** the full text content of the specified output pane.
4. **Writes** the content to stdout.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Could not attach to running TcXaeShell" | Open the TwinCAT XAE Shell first |
| "Could not read TwinCAT output pane" | Ensure the TwinCAT pane exists (TwinCAT XAE must be active) |
| Empty output | The pane may have been cleared; run a build or start TwinCAT runtime first |
