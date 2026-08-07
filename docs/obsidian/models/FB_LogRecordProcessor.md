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

