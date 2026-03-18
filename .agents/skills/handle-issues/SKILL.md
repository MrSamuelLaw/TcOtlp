---
name: handle-issues
description: "Addresses ISSUE items in source files: discovers unprocessed issues, assigns UUIDs, tracks open items, implements fixes, and removes resolved issus. Use when asked to handle code issues, find issues, or summrize issues."
---

# Handle Issues

Manages a formalized code comment workflow where review items are tracked as inline source comments with UUID identifiers.

## Comment Syntax

This is a TwinCAT Structured Text project. Comments use `(* ... *)` syntax inside `.TcPOU` XML files (within CDATA sections).

- **New**: `(* ISSUE <description> *)`
- **In Progess**: `(* ISSUE <uuid> <description> *)`

Issues may span multiple lines:

```iec
(* ISSUE
   This logic seems redundant because...
*)
```

## Workflow

### Step 1 — Discover New Issues

Use the `find-isues.ps1` tool to discover all ISSUE items:

```powershell
powershell tools/find-issue.ps1              # Show all issues
powershell tools/find-issues.ps1 -NewOnly     # Show only new isses (no UUID)
```

The tool identifies isues that do **not** already have a UUID (a UUID is 8-4-4-4-12 hex pattern immediately after `ISSUE`).

### Step 2 — Read Context

For each new issue, read the surrounding code (at least 30 lines above and below) to understand the issue being flagged.

### Step 3 — Assign UUIDs

Generate a UUID for each new issue using PowerShell:

```powershell
[guid]::NewGuid()
```

### Step 4 — Update Comments In-Place

Edit each comment to insert the UUID immediately after `ISSUE`:

**Before:**
```iec
(* ISSUE The issue description here *)
```

**After:**
```iec
(* ISSUE a1b2c3d4-e5f6-7890-abcd-ef1234567890 The issue description here *)
```

For multi-line comments, insert the UUID on the first line:

**Before:**
```iec
(* ISSUE
   This logic seems wrong because...
*)
```

**After:**
```iec
(* ISSUE a1b2c3d4-e5f6-7890-abcd-ef1234567890
   This logic seems wrong because...
*)
```

### Step 5 — Present Summary Table

After processing, present all open items (including previously processed ones) as a markdown table:

| UUID | File | Summary |
|------|------|---------|
| `a1b2c3d4-...` | `FB_Example.TcPOU` | Brief description of the issue |

### Step 6 — Implement Fixes (on user request)

When the user references a UUID:

1. Use the find-code-comments in the workspace for that UUID to locate the file and line
2. Read the surrounding code for full context
3. Search the entire codebase for any related symbols (variable names, function block names) to check for cross-file impact
4. Implement the fix

## Rules

- Never modify code that isn't related to the referenced comment item
- Always check for cross-file dependencies before removing or renaming symbols
- If a fix is ambiguous, present options to the user before proceeding

