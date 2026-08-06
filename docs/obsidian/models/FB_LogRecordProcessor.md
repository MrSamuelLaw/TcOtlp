# FB_LogRecordProcessor

`FB_LogRecordProcessor` models the OpenTelemetry SDK `LogRecordProcessor` hook. It is not part of OTLP itself: OTLP defines the wire protocol, while the OpenTelemetry Logs SDK defines processors, exporters, and their lifecycle.

## Reference implementation

There is no official OpenTelemetry SDK for IEC 61131-3 Structured Text.

- **C++ is the closest mechanical reference** because Structured Text and C++ both permit explicit pointers, deterministic object lifetimes, interfaces/inheritance, and operation without garbage collection.
- **Java is the better reference for this processor API**. Its `LogRecordProcessor` has only one abstract operation, `onEmit`. `forceFlush`, `shutdown`, and `close` have default implementations. This is the model to reproduce with an abstract `FB_LogRecordProcessor`: derivatives only need to implement `onEmit`, while the base function block supplies common lifecycle behavior.

Do not copy the C++ `MakeRecordable`/`unique_ptr` API literally. It solves C++-specific ownership requirements and would make the Structured Text processor contract unnecessarily large.

## Processor topology

Registered processors are **ordered hooks with independent output pipelines**, not queues connected end to end.

```text
FB_Logger.emit (owns the source record)
    |
    +--> processor 0.onEmit(source)       -- borrow, optionally mutate
    |
    +--> processor 1.onEmit(source)       -- clone --> queue 1 --> exporter 1
    |
    +--> processor 2.onEmit(source)       -- clone --> queue 2 --> exporter 2
    |
    `--> source record is deleted by its owner
```

The provider invokes `onEmit` synchronously in registration order. A mutation made by processor 0 MUST therefore be visible to processors 1 and 2. A processor which needs to retain a record after `onEmit` returns, such as a simple or batch exporting processor, MUST place a deep copy in its own queue.

The following model is incorrect:

```text
queue 0 --> queue 1 --> queue 2 --> exporter
```

Passing ownership from one processor to the next prevents independent exporters, makes a full queue block later processors, and makes ordered record mutation difficult to define.

## Required derivative method

### onEmit

`onEmit` is the **only method that an `FB_LogRecordProcessor` derivative is required to override**.

Proposed Structured Text shape:

```iecst
METHOD PUBLIC ABSTRACT onEmit
VAR_INPUT
    pLogRecord : POINTER TO FB_LogRecord;
END_VAR
```

`pLogRecord` is a mutable, borrowed pointer. Passing the pointer as `VAR_INPUT`, rather than `VAR_IN_OUT`, helps communicate that `onEmit` does not receive ownership and must not set the caller's pointer to `0`.

#### Preconditions

- `pLogRecord` MUST be non-zero.
- The record MUST be fully populated with its resource and instrumentation-scope associations available.
- The provider MUST call `onEmit` only while the processor is running.
- The same PLC task SHOULD perform the complete ordered `onEmit` pass so mutations are deterministic.

#### Required behavior

- The method MUST complete synchronously and in bounded time.
- The method MUST NOT perform network or file I/O.
- The method MAY mutate the source record before returning. Those mutations are visible to processors registered later.
- The method MUST NOT delete the source record, retain its pointer, enqueue its pointer, or transfer its ownership.
- If work must continue in later PLC scans, the method MUST deep-clone the record and retain only the clone.
- The method has no return value. A processor-local allocation failure or full queue drops that processor's clone and updates processor diagnostics; it does not fail `FB_Logger.emit` and does not prevent later processors from running.

The OpenTelemetry method also receives a resolved `Context`. TcOtlp does not currently define a context object, so this model intentionally omits that parameter. Add it to `onEmit` when a context model exists rather than hiding context in queue ownership rules.

## Queue and ownership rules

| Object                                | Owner                                 | Rule                                                                                                                                |
| ------------------------------------- | ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Source `FB_LogRecord` during dispatch | `FB_Logger`/provider dispatch code    | Borrowed by each `onEmit`; deleted after every registered processor has returned.                                                   |
| Queued `FB_LogRecord` clone           | The processor whose queue accepted it | Deleted by that processor after export succeeds, fails terminally, or is abandoned during cleanup.                                  |
| Queue nodes                           | The containing processor              | Never exposed through `I_LogRecordProcessor`.                                                                                       |
| Processor configuration and lifecycle | `FB_LoggerProvider` logically         | The PLC program may allocate processor FBs statically, but the provider controls registration, calls, flush, and shutdown ordering. |
| Exporter FB                           | The PLC program/static FB hierarchy   | A processor holds a non-owning `REFERENCE TO` it; the exporter MUST outlive the processor.                                          |
| Batch passed to an exporter           | The processor                         | The exporter borrows it. While the exporter reports `BUSY`, the processor retains the batch and MUST NOT delete or reuse it.        |

A full queue drops only the clone intended for that processor. The original source record remains valid and continues to every later processor. This is especially important when several exporting processors are registered.

### Simple processor

The OpenTelemetry simple processor exports synchronously and has no queue. Blocking inside `onEmit` is not acceptable in a PLC task, so `FB_LogRecordProcessor_Simple` is an intentional real-time adaptation:

- its private queue has capacity 1;
- `onEmit` clones and enqueues when the slot is free;
- a later cyclic base call advances the exporter;
- when the slot is occupied, only the new clone is dropped;
- it exports as soon as the next processor execution opportunity occurs.

### Batch processor

`FB_LogRecordProcessor_Batch` uses the same ownership rule with a larger bounded queue. It begins an export when at least one of these conditions is true:

- `maxExportBatchSize` records are ready;
- `scheduledDelayMillis` has elapsed;
- a force-flush or shutdown request is active.

The batch processor removes no record from owned storage until the exporter reaches a terminal success or failure state. A retry policy belongs to the exporter, not the processor.

## Inherited base behavior

OpenTelemetry requires `ForceFlush` and `Shutdown` operations, but they do not need to be abstract derivative methods. `FB_LogRecordProcessor` should provide their common implementation, following Java's default-method approach.

| Base operation | Intended use | Derivative override required? |
| --- | --- | --- |
| `onEmit` | Synchronous hook for one borrowed mutable record. | **Yes; this is the only required override.** |
| cyclic execution (`call` or the FB body) | Advances delay timers, queue-to-batch movement, and a `BUSY` exporter without blocking the PLC task. | No. |
| `forceFlush` | Requests export of every record accepted before the request and reports completion asynchronously over later scans. | No. |
| `shutdown` | Stops intake, includes force-flush behavior, shuts down the exporter, and becomes idempotently complete. | No. |
| `free`/`FB_Exit` | Deletes processor-owned clones and queue nodes after orderly shutdown, or performs bounded emergency cleanup. | No. |

After shutdown begins, the provider MUST NOT call `onEmit`. If it is called accidentally, the base processor SHOULD ignore the record without taking ownership. `Shutdown` includes the effects of `ForceFlush` and SHOULD be safe to request more than once, even though the provider is expected to request it only once.

`isFull`, `isDone`, `push`, and `pop` are queue/state-machine implementation details. They SHOULD NOT be part of `I_LogRecordProcessor` and SHOULD NOT be methods that every custom processor must implement. If retained, keep them protected or private on the queue-owning base function block.

## State model

```text
RUNNING --forceFlush--> FLUSHING --queue drained/exporter flushed--> RUNNING
    |
    `--shutdown-------> SHUTTING_DOWN --drain/flush/exporter shutdown--> SHUT_DOWN
```

- `RUNNING` accepts records through `onEmit`.
- `FLUSHING` prioritizes records accepted before the flush request. Completion means those records reached a terminal export result and exporter flush completed.
- `SHUTTING_DOWN` accepts no new records and includes the effects of force flush.
- `SHUT_DOWN` is terminal. Cyclic calls and repeated shutdown requests are harmless.

All transitions must advance incrementally across PLC scans. No lifecycle operation may wait in a loop for an exporter or perform unbounded work in one scan.

## Sources

- [OpenTelemetry Logs SDK specification: LogRecordProcessor](https://opentelemetry.io/docs/specs/otel/logs/sdk/#logrecordprocessor)
- [OpenTelemetry Java `LogRecordProcessor`](https://github.com/open-telemetry/opentelemetry-java/blob/main/sdk/logs/src/main/java/io/opentelemetry/sdk/logs/LogRecordProcessor.java)
- [OpenTelemetry Java ordered composite processor](https://github.com/open-telemetry/opentelemetry-java/blob/main/sdk/logs/src/main/java/io/opentelemetry/sdk/logs/MultiLogRecordProcessor.java)
- [OpenTelemetry Java batch processor](https://github.com/open-telemetry/opentelemetry-java/blob/main/sdk/logs/src/main/java/io/opentelemetry/sdk/logs/export/BatchLogRecordProcessor.java)
- [OpenTelemetry C++ processor ownership interface](https://github.com/open-telemetry/opentelemetry-cpp/blob/main/sdk/include/opentelemetry/sdk/logs/processor.h)
