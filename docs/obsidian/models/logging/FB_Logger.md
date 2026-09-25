---
type: model
domain: logging
status: implemented
implements:
  - FB_Logger
  - FB_LogRecord
source: TcOtlp/test/OTEL/LOGGING/LOGGER/FUNCTION_BLOCKS/FB_Logger.TcPOU
---

`FB_Logger` is the public API of the logging domain. Application code uses it to build one `FB_LogRecord` at a time through a fluent chain, and then emits that record to its [[FB_LoggerProvider]]. The logger decides what the record contains. It does not queue, process, serialize or export records.

## Construction

```iec
resource: FB_Resource(schemaUrl := '');
provider: FB_LoggerProvider(resource := resource);
scope: FB_InstrumentationScope(name := 'motor1', version := '1.0.0', schemaUrl := '');
logger: FB_Logger(scope := scope, provider := provider);
```

`FB_Init` takes two borrowed references: the `FB_InstrumentationScope` that names the code doing the logging, and the provider that receives its records. The logger's `resource` property returns the provider's resource. The scope, the provider and the resource must all stay valid while the logger can start records.

A program usually declares one logger per instrumentation scope, such as one per machine module, and they all share one provider.

## The fluent chain

A record is built in one chain that starts with `startLogRecord`, sets optional fields, and ends with `emit`:

```iec
IF NOT logger
    .startLogRecord(severityNumber := E_SeverityNumber.WARN)
    .setBody('process cycle amps warning, motor fault imminent')
    .setEventName('motor.amps.warning')
    .setTraceContextFromSpan(pSpan)  // a no-op when pSpan is 0
    .setNumberAttribute('motor.amps.max', maxAmps)
    .setStringAttribute('motor.id', 'M1')
    .emit(failureResult => failureResult) THEN
    // CASE failureResult OF ...
END_IF
```

Every setter returns `REFERENCE TO FB_Logger`, so the chain can list any setters in any order. Only `emit` returns a result.

### Failures are deferred to emit

A setter never returns an error. When one fails, the logger records the failure reason, and every later setter in the chain does nothing. `emit` then:

- reports the **first** failure in the chain as `failureResult`, so the caller sees the root cause rather than a knock-on error;
- releases the incomplete record, so a failed chain never leaks and never emits a partial record.

This keeps the chain readable in a PLC program: one `IF NOT ... .emit(...)` handles every failure.

Each setter that replaces a field builds the new value first and releases the old one only after that succeeds. Setting the same field twice keeps the last value; if the second set fails, the chain still fails.

### Lifecycle

```text
startLogRecord ──► building ──► emit ──► (provider owns the record)
                  (logger owns          │
                   pLogRecord)          └─ on failure: record released, first failure reported
```

1. **`startLogRecord(severityNumber)`** allocates the record, sets its severity, stamps `timestamp` with the current time in Unix-epoch nanoseconds, and copies the logger's resource and scope into it. It clears any failure left from the previous chain.
2. **Building.** The logger owns the record through its `pLogRecord` output while the setters fill it in.
3. **`emit(failureResult)`** hands the record to the provider's `onEmit` and clears `pLogRecord`. From then on the provider owns it (see [[FB_LoggerProvider#Ownership]]). No processor runs at emit time, so the cost of logging does not depend on the processors or exporters configured.

A logger holds one record at a time. Calling `startLogRecord` while a record is being built fails the pending chain with `LOG_RECORD_ALREADY_STARTED`. Calling `emit` or a setter with no record started fails with `LOG_RECORD_NOT_STARTED`.

### Snapshots

`startLogRecord` copies the resource and scope, including their attributes, into the record. A processor that clones the record can keep it after the logger, provider, resource or scope is gone. A change to the resource or scope after `startLogRecord` does not reach records already started.

## Methods

| Method | Sets | Notes |
| --- | --- | --- |
| `startLogRecord(severityNumber)` | severity, timestamp, resource, scope | Starts the chain. |
| `setTimestamp(timestamp)` | `timestamp` | Unix-epoch nanoseconds. Overrides the time stamped by `startLogRecord`. |
| `setBody(str)` | `body` | A string body. |
| `setBody_AnyValue(pVal)` | `body` | Any `FB_AnyValue`. The value is cloned, so the caller keeps ownership of `pVal`. |
| `setEventName(str)` | `eventName` | |
| `setStringAttribute(key, value)` | an attribute | Replaces the value of an existing key. |
| `setNumberAttribute(key, value)` | an attribute | `value` is `ANY_NUM`. Replaces the value of an existing key. |
| `setTraceContextFromSpan(pSpan)` | `traceId`, `spanId`, `flags` | See [Correlating with a span](#correlating-with-a-span). |
| `emit(failureResult)` | — | Ends the chain. |
| `free()` | — | Releases a record still being built. |
| `reset()` | — | `free`, then clears the failure state. |

Attributes are bounded by the record's `FB_Attributes`, which holds at most `TcOtlp_GVL.DEFAULT_MAX_ATTRIBUTE_COUNT` attributes (and never more than `MAX_LOOP_COUNT`). A new key beyond that fails the chain with `ATTRIBUTE_COUNT_LIMIT_REACHED`; replacing an existing key still succeeds.

### Correlating with a span

`setTraceContextFromSpan(pSpan)` ties a log to the [[FB_Span]] whose work it describes. It fills the record's trace context from the span's context, taking only the parts the OpenTelemetry log data model defines: TraceId, SpanId and TraceFlags. The record gets its own copies of the span's trace id and span id, and the span's W3C trace flags (bits 0–7 of the span's `flags`) go into the low 8 bits of the record's `flags`. The span is only borrowed for the call.

The rest of the span context stays on the span. The log data model has no field for trace state, and bits 8 and 9 of the span's `flags` describe the span's parent rather than the span.

A null span, or one without ids, is a no-op rather than a failure, so the same chain works where no span is running. Every span the tracer builds has both ids, so a span without them should not happen, and failing the log over it would lose the log for no benefit.

The flags are copied when the log is written. They record the head sampling decision made by the sampler's `onStart`. When a sampler drops the span in `onEnd`, as `FB_Sampler_ErrorsOnly` does, its logs have already been emitted and stay marked sampled. The OpenTelemetry SDK behaves the same way. See [[FB_Sampler]].

`setTraceContextFromSpan` is built from three internal setters, one per field: `_setTraceId(pBytes, nSize)` and `_setSpanId(pBytes, nSize)` set an id from raw bytes, and `_setFlags(traceFlags)` sets the W3C trace flags. The leading underscore marks them as internal: they exist for tests and for `setTraceContextFromSpan` itself. `_setFlags` takes a `BYTE`, so the reserved upper bits of `flags` stay zero. A byte buffer shorter than the id fails the chain with `TRACE_ID_BYTE_COUNT_TOO_SMALL` or `SPAN_ID_BYTE_COUNT_TOO_SMALL`.

## FB_LogRecord

`FB_LogRecord` is the record the logger builds. It follows the OpenTelemetry log data model.

| Field | Owned | Set by |
| --- | --- | --- |
| `severityNumber: E_SeverityNumber` | — | `startLogRecord` |
| `timestamp: ULINT` | — | `startLogRecord`, `setTimestamp` |
| `eventName: POINTER TO FB_String` | yes | `setEventName` |
| `traceId: POINTER TO FB_TraceId` | yes | `setTraceContextFromSpan` |
| `spanId: POINTER TO FB_SpanId` | yes | `setTraceContextFromSpan` |
| `flags: UDINT` | — | `setTraceContextFromSpan`, `_setFlags` |
| `body: POINTER TO FB_AnyValue` | yes | `setBody`, `setBody_AnyValue` |
| `droppedAttributesCount: UDINT` | — | no setter yet |
| `resource`, `scope` | yes | `startLogRecord`, as snapshots |
| `attributes` | yes | `setStringAttribute`, `setNumberAttribute` |

The fields the logger writes are `VAR_INPUT`, so the logger can assign them. The snapshots and attributes are `VAR_OUTPUT` instances.

`flags` is the OTLP `LogRecord.flags` field, a fixed32. Its low 8 bits are the W3C trace flags of the record's span, so bit 0 is set only when the span was sampled; its upper 24 bits are reserved and zero. The serializer writes `flags` only for a record that has a trace id, because a record outside any trace has no trace flags.

`severityText` is derived rather than stored: it is the name of `severityNumber`.

`cloneTo(pDest)` deep copies the record, including every owned value and both snapshots, for a processor that must keep it past the provider's `tick`. `pDest` must be `0` on entry, or the clone fails with `DESTINATION_ALREADY_ASSIGNED`. `free` releases everything the record owns, and `delete` releases the record itself and clears the caller's pointer.

## Failure reasons

`emit` reports one `E_LoggerFailureReason`:

| Reason | Cause |
| --- | --- |
| `LOG_RECORD_ALREADY_STARTED` | `startLogRecord` was called while a record was being built. |
| `LOG_RECORD_NOT_STARTED` | A setter or `emit` was called with no record started. |
| `EVENT_NAME_INVALID` | The event name could not be copied. |
| `BODY_VALUE_POINTER_NULL`, `BODY_VALUE_INVALID`, `BODY_VALUE_TYPE_UNSUPPORTED` | The body could not be set. |
| `ATTRIBUTE_VALUE_INVALID`, `ATTRIBUTE_VALUE_TYPE_UNSUPPORTED`, `ATTRIBUTE_COUNT_LIMIT_REACHED` | An attribute could not be set. |
| `TRACE_ID_*`, `SPAN_ID_*` | A raw id passed to `_setTraceId` or `_setSpanId` was invalid. `setTraceContextFromSpan` never causes these, because a span's ids are always valid. |
| `SNAPSHOT_COPY_FAILURE` | The resource or scope could not be copied into the record. |
| `MEMORY_ALLOCATION_FAILURE` | Any allocation failed. |
| `TRANSFER_TO_PROVIDER_FAILURE` | The provider's queue refused the record, usually because more than `TcOtlp_GVL.MAX_LOG_RECORDS_PER_SCAN` records were emitted in one scan. |

## Ownership summary

- The logger **borrows** its scope and provider, and `setTraceContextFromSpan` borrows the span.
- The logger **owns** the record between `startLogRecord` and `emit`, and releases it if the chain fails.
- The provider **owns** the record after a successful `emit`.
- `setBody_AnyValue` **clones** its value; the caller still owns `pVal`.

`FB_Exit` calls `free`, so a record still being built is released when the logger instance is removed. During an online change `FB_Exit` skips `free`, because the copied instance keeps `pLogRecord`. A program that abandons a chain while the logger lives on, for example on a reset, calls `logger.free()` or `logger.reset()`.

## Tests

- `FB_TestLogger` covers `emit` with no record, the first-failure rule, starting a second record, the Unix-epoch timestamp, `FB_Exit` with and without an online change, `setTraceContextFromSpan` with sampled, unsampled, null and id-less spans, and `_setFlags`.
- `FB_TestLogRecord` covers `cloneTo`.
- `FB_TestProtoJsonSerializer` builds a full record through the logger and checks every serialized field, and checks that `flags` is left out of a record without a trace id.
