---
name: triaging-code-reviews
description: "Triages CODE REVIEW comments in source files: discovers unprocessed comments, assigns UUIDs, tracks open items, implements fixes, and removes resolved comments. Use when asked to process code reviews, triage reviews, or address a CODE REVIEW UUID."
---

# Triaging Code Reviews

Manages a formalized code review workflow where review items are tracked as inline source comments with UUID identifiers.

## Comment Syntax

This is a TwinCAT Structured Text project. Comments use `(* ... *)` syntax inside `.TcPOU` XML files (within CDATA sections).

- **Unprocessed**: `(* CODE REVIEW <description> *)`
- **Processed**: `(* CODE REVIEW <uuid> <description> *)`

Comments may span multiple lines:

```iec
(* CODE REVIEW
   This logic seems redundant because...
*)
```

## Workflow

### Step 1 — Discover Unprocessed Comments

Use `finder` to search for `CODE REVIEW` in `.TcPOU` files. Identify comments that do **not** already have a UUID (a UUID is 8-4-4-4-12 hex pattern immediately after `CODE REVIEW`).

```
finder query: "Find all CODE REVIEW comments in TcPOU files across the codebase"
```

### Step 2 — Read Context

For each unprocessed comment, read the surrounding code (at least 30 lines above and below) to understand the issue being flagged.

### Step 3 — Assign UUIDs

Generate a UUID for each unprocessed comment using PowerShell:

```powershell
[guid]::NewGuid()
```

### Step 4 — Update Comments In-Place

Edit each comment to insert the UUID immediately after `CODE REVIEW`:

**Before:**
```iec
(* CODE REVIEW This variable is redundant *)
```

**After:**
```iec
(* CODE REVIEW a1b2c3d4-e5f6-7890-abcd-ef1234567890 This variable is redundant *)
```

For multi-line comments, insert the UUID on the first line:

**Before:**
```iec
(* CODE REVIEW
   This logic seems wrong because...
*)
```

**After:**
```iec
(* CODE REVIEW a1b2c3d4-e5f6-7890-abcd-ef1234567890
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

1. Use `finder` to locate the UUID in the codebase to find the file and line
2. Read the surrounding code for full context
3. Use `finder` to search the entire codebase for any related symbols (variable names, function block names) to check for cross-file impact
4. Implement the fix
5. Remove the `CODE REVIEW <uuid> ...` comment block from the file

### Step 7 — Verify Resolution

After removing a comment, use `finder` once more to confirm the UUID no longer appears in the codebase.

## Rules

- Never modify code that isn't related to the referenced review item
- Always check for cross-file dependencies before removing or renaming symbols
- When fixing, remove only the CODE REVIEW comment — preserve any other nearby comments
- If a fix is ambiguous, present options to the user before proceeding
