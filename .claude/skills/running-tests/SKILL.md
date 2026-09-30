---
name: running-tests
description: "Runs TcUnit tests for the TcOtlp TwinCAT project via run-tests.ps1. Use when asked to run tests, execute tests, or verify test results."
---

# Running TcUnit Tests

Runs the TcOtlp TcUnit test suite by invoking `run-tests.ps1` from the workspace root.

## Prerequisites

- The 64-bit TwinCAT XAE Shell (`TcXaeShell.exe`) must be **open and running** before executing tests.
- The TwinCAT XAE shell and TcUnit must be installed.

## How to Run Tests

Execute from the workspace root:

```powershell
powershell -ExecutionPolicy Bypass -File tools/run-tests.ps1
```

### Optional Parameters

| Parameter | Default | Description |
|---|---|---|
| `-BuildTimeoutSeconds` | 120 | Max seconds to wait for the build |
| `-TestTimeoutSeconds` | 120 | Max seconds to wait for TcUnit results |
| `-PollIntervalMs` | 250 | Milliseconds between DTE polls |
| `-SettleMs` | 1000 | Quiet period required after the TcUnit summary appears |
| `-TailLines` | 400 | Lines read from the end of the output pane per poll |
| `-IncrementalBuild` | off | Use `Build.BuildSolution` instead of a full rebuild |
| `-InstallLibrary` | off | Check the `otel` project, save it as `bin/otel.library`, install it, and reopen the solution before building |

The `test` PLC project references the **installed** `TcOtlp` library (`TcOtlp, *`), not the `otel` sources. After changing anything under `TcOtlp/otel/`, run with `-InstallLibrary` or the tests still exercise the old library:

```powershell
powershell -ExecutionPolicy Bypass -File tools/run-tests.ps1 -InstallLibrary
```

Example with custom timeouts:

```powershell
powershell -ExecutionPolicy Bypass -File tools/run-tests.ps1 -BuildTimeoutSeconds 180 -TestTimeoutSeconds 180
```

Faster iteration when only a few POUs changed:

```powershell
powershell -ExecutionPolicy Bypass -File tools/run-tests.ps1 -IncrementalBuild
```

## What the Script Does

1. **Attaches** to a running TcXaeShell instance via DTE COM (`TcXaeShell.DTE.17.0`).
2. **Opens** the solution `TcOtlp/TcOtlp.sln` if not already loaded.
3. **Rebuilds** the solution; exits with code 1 on build errors, printing Error List details.
4. **Starts TwinCAT** runtime via `StartRestartTwinCAT()`.
5. **Polls** the TwinCAT output pane for TcUnit sentinel lines (test suites, tests, pass/fail counts, duration).
6. **Writes** full output to `tools/test-results.log`.
7. **Exits** with code 0 if all tests pass, code 1 if any fail.

## Interpreting Results

- **Build failures**: The script prints error details from the VS Error List and exits 1.
- **Test results**: Check the summary printed at the end or read `test-results.log`.
- Key lines in the output:
  - `FAILED TEST '...'` — individual test failure with expected/actual values.
  - `| Failed tests: N` — total failed count.
  - `| Successful tests: N` — total passed count.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Could not attach to running TcXaeShell" | Open the TwinCAT XAE Shell first |
| "Build timed out" | Increase `-BuildTimeoutSeconds` |
| "TcUnit results timed out" | Increase `-TestTimeoutSeconds`; check TwinCAT is licensed and runtime can start |
| Build errors | Read the Error List output or fix the reported source files |
