---
type: model
domain: logging
status: implemented
implements:
  - FB_LoggerProvider
source: TcOtlp/test/OTEL/LOGGING/PROVIDER/FUNCTION_BLOCKS/FB_LoggerProvider.TcPOU
---

`FB_LoggerProvider` is the context object that owns the per-scan log record buffer and drives the processing pipeline. It exposes the `FB_Resource` used by its loggers and provides the cyclic entry point for the whole logging domain.

The provider borrows the resource reference supplied to `FB_Init`; the scope that declares the resource remains responsible for its lifetime. A logger likewise borrows a reference to the provider, so both the provider and its resource must remain valid while that logger can start log records.

When a logger creates a log record, it copies the current resource and instrumentation scope into the record. Processors can therefore retain a cloned record without retaining the logger, provider, resource, or scope that created it.

## Cyclic behavior

The provider is not a passive container. A logger's `emit` hands its completed record to `onEmit`, which pushes the record into the provider's queue and returns — no processor runs at emit time. All processing happens later in the scan when the application calls `tick()`.

This split is what makes the pipeline usable in a real-time context: `emit` is a bounded queue push with no downstream work, so the cost of logging at the call site does not depend on how many processors or exporters are configured.

The record queue is bounded by `TcOtlp_GVL.MAX_LOG_RECORDS_PER_SCAN`, so a scan that emits more records than the buffer holds fails the push rather than growing without limit.

### Processor registration is per-scan

`stageProcessor` returns `REFERENCE TO FB_LoggerProvider`, so registrations chain:

```iecst
IF NOT provider
    .stageProcessor(consoleProcessor)
    .stageProcessor(batchProcessor)
    .tick(failureReason => failureReason) THEN
    // handle failure
END_IF
```

Registration is cyclic by design: the `stageProcessor` chain is called every scan, ahead of the `tick()` call. `tick()` releases the processor list as part of its cleanup, so the provider starts each scan with no processors registered. Adding the same processor twice within one scan is silently ignored rather than treated as an error. This arrangement survives online change, because the provider holds no processor references across scans.

## Members

- **`FB_Init(resource: REFERENCE TO FB_Resource)`** — Stores a borrowed reference to the resource.

- **`resource: REFERENCE TO FB_Resource`** — Read-only property that returns the borrowed resource.

- **`processorCount: UDINT`** — `VAR_OUTPUT` reporting how many distinct processors are registered for the current scan.

- **`stageProcessor(processor: REFERENCE TO FB_LogRecordProcessor_Base) -> REFERENCE TO FB_LoggerProvider`** — Appends the processor's `pSelf` identity to the provider's linked list and returns `THIS^` for chaining. A processor already present for this scan is ignored. Allocation failure records `ADD_PROCESSOR_FAILURE` and is reported by the next `tick()`.

- **`onEmit(record: POINTER TO FB_LogRecord) -> BOOL`** — Takes ownership of the record by pushing it into the provider's queue. Returns `FALSE` for a null record or a failed push. Called by `FB_Logger.emit`, not by application code.

- **`tick(failureReason: E_LoggerProviderFailureReason) -> BOOL`** — The cyclic entry point. Short-circuits if an earlier `stageProcessor` call in this scan failed. With no processors registered, it frees the queued records and succeeds. Otherwise it pops each queued record, offers it to every registered processor's `onEmit` in registration order, and deletes the record once all processors have seen it. It then calls `tick()` on each processor so they can advance their own exporters. On completion it frees the record queue and the processor list.

- **`FB_Exit()`** — Releases queued records and the processor list during normal destruction.

## Ownership

The provider owns every record between `onEmit` and the end of the `tick()` that consumes it. Processors receive the record by reference during `onEmit` and must clone it if they intend to retain it, because the provider deletes the original as soon as the last processor returns.
