---
name: importing-generated-code
description: "Imports generated TwinCAT Structured Text files into the TcOtlp PLC project. Copies files from generated/ into TcOtlp/otel/OTEL/ and updates the .plcproj XML. Use when asked to import generated code, update the TwinCAT project, sync generated files, or refresh the PLC project after code generation."
---

# Importing Generated Code into the TwinCAT Project

Copies generated TwinCAT files from `generated/` into `TcOtlp/otel/OTEL/` and updates `otel.plcproj` to register them as Compile items.

## How to Import

Run from the workspace root:

```powershell
cd code-gen
uv run python import_to_plcproj.py
```

### Optional Parameters

| Parameter | Description |
|---|---|
| `--generated-dir DIR` | Path to generated output directory (default: `generated`) |
| `--dry-run` | Preview changes without modifying any files |

### Dry Run Example

```powershell
cd code-gen
uv run python import_to_plcproj.py --dry-run
```

## What the Script Does

1. **Scans** `generated/ENUMS/`, `generated/INTERFACES/`, and `generated/FUNCTION_BLOCKS/` for generated files.
2. **Copies** each file into `TcOtlp/otel/OTEL/{ENUMS,INTERFACES,FUNCTION_BLOCKS}/`, overwriting any existing files (including old hand-written ones that have been superseded by generated versions).
3. **Updates** `otel.plcproj`:
   - Removes all existing `OTEL\` Compile entries (they are regenerated each run).
   - Adds sorted Compile entries for every generated file.
   - Ensures required OTEL Folder entries exist.
4. **Preserves** everything outside `OTEL\`:
   - `MAIN.TcPOU`, `PlcTask.TcTTO`, `test.tmc`
   - `TEST_OTEL\` Compile and Folder entries
   - `PlaceholderReference` entries (library references)
   - `ProjectExtensions` (TwinCAT project options)

## Typical Workflow

The full regenerate-and-import cycle:

```powershell
cd code-gen
uv run python generate.py
uv run python import_to_plcproj.py
```

Then optionally run tests to verify:

```powershell
cd ..
powershell -ExecutionPolicy Bypass -File run-tests.ps1
```

## Idempotency

The script is idempotent — running it multiple times produces the same result. It always replaces all `OTEL\` Compile entries with a fresh set derived from the `generated/` directory contents.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Generated directory not found" | Run `generate.py` first to produce the `generated/` output |
| ".plcproj not found" | Ensure the TwinCAT project exists at `TcOtlp/otel/otel.plcproj` |
| Missing files in TwinCAT after import | Check that `generated/` contains the expected subdirectories and files |
| TwinCAT won't load project after import | Run with `--dry-run` first to verify; check `.plcproj` XML is well-formed |
