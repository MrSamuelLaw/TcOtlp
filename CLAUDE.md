<!-- BEGIN swamp managed section - DO NOT EDIT -->
# Project

This repository is managed with [swamp](https://github.com/swamp-club/swamp).

## Rules

1. **Search before you build.** When automating AWS, APIs, or any external service: (a) search community extensions with `swamp extension search <query>` — prefer `@swamp/*` official extensions first, (b) search local/installed types with `swamp model type search <query>`, (c) if a community extension exists, install it with `swamp extension pull <package>` instead of building from scratch, (d) extend an existing type if it covers the domain but lacks the method you need, (e) only create a custom extension model in `extensions/models/` as a last resort. Use the `swamp` skill for guidance. The `command/shell` model is ONLY for ad-hoc one-off shell commands, NEVER for wrapping CLI tools or building integrations.
2. **Extend, don't be clever.** When a model covers the domain but lacks the method you need, extend it with `export const extension` — don't bypass it with shell scripts, CLI tools, or multi-step hacks. One method, one purpose. Use `swamp model type describe <type> --json` to check available methods.
3. **Use the data model.** Once data exists in a model (via `lookup`, `start`, `sync`, etc.), reference it with CEL expressions. Don't re-fetch data that's already available.
4. **CEL expressions everywhere.** Wire models together with CEL expressions. Always prefer `data.latest("<name>", "<dataName>").attributes.<field>` over the deprecated `model.<name>.resource.<spec>.<instance>.attributes.<field>` pattern.
5. **Verify before destructive operations.** Always `swamp model get <name> --json` and verify resource IDs before running delete/stop/destroy methods.
6. **Prefer fan-out methods over loops.** When operating on multiple targets, use a single method that handles all targets internally (factory pattern) rather than looping N separate `swamp model method run` calls against the same model. Multiple parallel calls against the same model contend on the per-model lock, causing timeouts. A single fan-out method acquires the lock once and produces all outputs in one execution. Check `swamp model type describe` for methods that accept filters or produce multiple outputs.
7. **Extension npm deps are bundled, not lockfile-tracked.** Swamp's bundler inlines all npm packages (except zod) into extension bundles at bundle time. `deno.lock` and `package.json` do NOT cover extension model dependencies — this is by design. Always pin explicit versions in `npm:` import specifiers (e.g., `npm:lodash-es@4.17.21`).
8. **Reports for reusable data pipelines.** When the task involves building a repeatable pipeline to transform, aggregate, or analyze model output (security reports, cost analysis, compliance checks, summaries), create a report extension. Use the `swamp` skill for guidance.
9. **"Workflow" means a swamp workflow.** In this repository the word "workflow" (and "create/run/execute/validate/debug workflow", "automate", "orchestrate", "automated/nightly job") refers to a swamp workflow — a declarative YAML DAG of model-method steps authored via `swamp workflow create`. Load and follow the `swamp` skill for these requests. Do NOT interpret these as a request to build an agent task list, spin up worktrees, or schedule a cron/remote agent. Only use those orchestration mechanisms when the user explicitly names one (e.g. "task list", "subagent", "worktree", "cron", "remote agent") or explicitly asks you to do the work yourself step by step rather than author a swamp workflow.
10. **Use swamp, don't bypass it.** Always work through swamp commands — don't go around them with raw shell tools. Use `swamp data query` to find data, not `grep`/`find` on `.swamp/` files. Use model methods to interact with resources, not `curl`/`aws`/`gcloud`/`kubectl` when a model type already wraps that API — check with `swamp model type search`. Use `swamp help` for CLI discovery, not guesswork. Composing with swamp output is fine (e.g. piping `--json` through `jq`) — the anti-pattern is bypassing swamp entirely.
11. **Inspect reports after failures.** When a model method or workflow run fails, inspect its generated reports before retrying or changing definitions. Reports run even on failure and capture structured diagnostics — error messages, execution status, arguments, and data output pointers. Use `swamp report get @swamp/method-summary --model <model> --json` for method failures or `swamp report get @swamp/workflow-summary --workflow <workflow> --json` for workflow failures. Run `swamp help report get` to confirm current retrieval syntax.

## Skills

**IMPORTANT:** Always load swamp skills, even when in plan mode. The skills provide
essential context for working with this repository.

- `swamp` - Swamp CLI — models, workflows, data, vaults, extensions, publishing, repos, reports, issues, and troubleshooting
- `swamp-getting-started` - Interactive onboarding for new swamp users

## Getting Started

**IMPORTANT:** At the start of every conversation, run
`swamp model search --json`. If no models are returned (empty result), you MUST
immediately invoke the `swamp-getting-started` skill before doing anything else.
This walks new users through an interactive onboarding tutorial.

If models already exist, start by using the `swamp` skill to work with
swamp models.

## Commands

Use `swamp --help` to see available commands. For a machine-readable JSON
schema of the CLI (commands, options, arguments) intended for agent
consumption, run `swamp help [<command>...]` — e.g. `swamp help` returns
the full tree, and `swamp help model method run` scopes to a subtree.
<!-- END swamp managed section -->

# TcOtlp Domain Model

This file applies to the entire repository. Use it as the source of truth for domain ownership when planning or reviewing changes.

TcOtlp implements OpenTelemetry Protocol (OTLP) concepts in TwinCAT Structured Text. The design should make the logging pipeline natural for PLC programmers while preserving explicit memory ownership and deterministic cyclic execution.

## Domain map

The current domain model contains five conceptual domains:

```text
Value Creation -> Log Creation -> Log Processing -> Log Serialization -> Log Exporting
```

This is the flow of log data and responsibility, not a requirement that every implementation call follows a linear pipeline. Keep upstream domains unaware of downstream infrastructure.

### 1. Value Creation

**Purpose:** Create, clone, represent, and release OTLP values safely.

**Owns:**

- `ValueFactory`
- `FB_AnyValue` and concrete value function blocks
- `FB_KeyValue`, `FB_String`, and `FB_Number`
- `FB_TraceId` and `FB_SpanId`
- Value types, factory statuses, allocation, cloning, and cleanup rules

**Boundary:** This domain knows how a value is represented and owned. It does not know which log contains the value, how the log is processed, how the value is serialized, or where it is exported.

### 2. Log Creation

**Purpose:** Build valid log records through the public logging API.

**Owns:**

- `FB_LoggerProvider`
- `FB_Logger`
- `FB_LogRecord`
- Severity, flags, required fields, and optional fields
- Capturing resource and instrumentation-scope snapshots in a record
- The fluent log-building lifecycle from `startLogRecord` through `emit`

**Boundary:** This domain depends on Value Creation for owned values. It creates and emits complete records but does not queue batches, choose a wire representation, or perform destination I/O.

`FB_Resource` and `FB_InstrumentationScope` are supporting concepts of Log Creation for now. Treat them as separate domains only if they acquire behavior and use cases beyond describing telemetry records.

### 3. Log Processing

**Purpose:** Accept emitted records and prepare them for export under PLC scheduling and memory constraints.

**Owns:**

- `I_LogRecordProcessor`
- Simple and batch log processors
- Enrichment hooks
- Record cloning, queues, batching, ordering, scheduling, and drop policy
- Transfer of a completed record batch to an exporter

**Boundary:** This domain may enrich and retain record snapshots. It does not define OTLP wire formatting or destination-specific state machines.

### 4. Log Serialization

**Purpose:** Convert log-domain objects into an OTLP-compliant wire representation.

**Owns:**

- Base ProtoJSON serialization behavior
- Log-record ProtoJSON serialization
- OTLP field names, nesting, grouping, encoding, and omission rules
- Conversion of values, resources, scopes, IDs, and numeric types to their wire forms

**Boundary:** Serialization never changes what a record means. A queue serializer such as `serializeLogsData` or `serializeTracesData` takes ownership of the queue it is given and drains it: each item is released once written, and anything left is released on failure. It does not decide when to flush records, open files, issue network requests, or retry delivery.

### 5. Log Exporting

**Purpose:** Deliver serialized logs to a concrete destination.

**Owns:**

- The exporter contract and exporter implementations
- Console, file, and HTTP destination behavior
- Exporter lifecycle and busy state
- Destination I/O, failures, timeouts, retries, and backpressure
- Accepting and eventually releasing ownership of export batches

**Boundary:** Exporting coordinates destination delivery and invokes Log Serialization as needed. It must not mutate the meaning of a log record or absorb processing policies that belong in Log Processing.

## Current source map

The physical layout is still evolving. Do not move code solely to make the folders mirror this document.

| Domain | Current primary locations |
| --- | --- |
| Value Creation | `TcOtlp/otel/OTEL/VALUES/` |
| Log Creation | `TcOtlp/otel/OTEL/LOGGING/`, `TcOtlp/otel/OTEL/RESOURCE/`, `TcOtlp/otel/OTEL/SCOPE/` |
| Log Processing | `TcOtlp/otel/OTEL/LOGGING/FUNCTION_BLOCKS/Processors/`, logging processor interfaces and record collections |
| Log Serialization | `TcOtlp/otel/OTEL/SERIALIZATION/`, `TcOtlp/otel/OTEL/LOGGING/FUNCTION_BLOCKS/Serializers/` |
| Log Exporting | `TcOtlp/otel/OTEL/EXPORTING/`, `TcOtlp/otel/OTEL/LOGGING/FUNCTION_BLOCKS/Exporters/` |

`OTEL/COMMON` is a shared technical kernel, not a business domain. Put code there only when it has no natural domain owner.

## Cross-domain rules

- Put behavior in the domain that owns the decision, not merely where it is first called.
- Keep Value Creation and Log Creation independent of processors, serializers, and destination infrastructure.
- Keep processing policy out of exporters and transport behavior out of processors.
- Processors check `isBusy()` and never call `export` on a busy exporter. What happens to the record or span then is processing policy: a simple processor drops it, and a batch processor keeps it queued. The exporter's own refusal while busy is a backstop, not the mechanism.
- Serializers consume the queue they are given and never alter the content they write. A caller that still needs the items must clone them first.
- Make pointer ownership transfer explicit. A callee owns a pointer only when the contract says so and the caller's pointer is cleared.
- Clone records or values when their lifetime must outlast the caller; release every owned allocation exactly once.
- Preserve bounded PLC execution: cyclic work and loops must have explicit limits.
- Treat the domain map as provisional. Do not add a new domain or redefine a boundary without a concrete responsibility that does not fit an existing domain.
- Assume a single task. Multi-task safety is an explicit non-goal; see below.

## Non-goals

**Multi-task safety is an explicit non-goal.** Every function block in this repository may assume it is created, called, and released from one PLC task, and that no other task touches it or the memory it owns.

Write code for that assumption rather than against it:

- No locks, semaphores, critical sections, or `TestAndSet` guards.
- No atomic or interlocked access, and no volatile-style re-reads of shared state.
- No defensive copies whose only purpose is to survive preemption by another task.
- Pointer ownership rules exist for lifetime correctness, not for concurrency. A single owner at a time is enough; it does not have to be a thread-safe owner.

Cyclic state machines still have to survive being spread across scan cycles of their own task, which is a different problem and is still required. An asynchronous service such as an ADS request may complete cycles later, so state that is in flight must stay valid until the request finishes.

If a caller ever does need to reach a component from a second task, that is a design change to be raised first, not something to pre-empt with defensive code.

## Change workflow

Before changing implementation code:

1. Identify the domain that owns the behavior.
2. Check the contracts at every crossed domain boundary, especially pointer ownership and lifecycle.
3. Prefer the smallest change within the owning domain.
4. Update the TwinCAT `.plcproj` whenever source files are added, moved, or removed.
5. Run the relevant TcUnit tests after changing Structured Text behavior.

## Tooling notes

- Don't pass scripts or file content through a shell heredoc (`cat > file <<'EOF'`). It is unreliable here: quotes inside the body, such as the ST escape `$'` or a single quote in a string literal, can break the shell command even when the delimiter is quoted. Write the script with the Write tool, then run it.
