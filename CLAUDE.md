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
