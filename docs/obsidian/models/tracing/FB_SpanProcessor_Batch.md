---
type: model
domain: tracing
status: design
implements:
  - FB_SpanProcessor_Batch
---

> [!abstract] Design note — not yet implemented
> No source exists under `TcOtlp/test/OTEL/TRACING/` for this function block. The contract below is intended design, mirroring the implemented `FB_LogRecordProcessor_Batch` described in [[FB_LogRecordProcessor]].

`FB_SpanProcessor_Batch` extends `FB_SpanProcessor_Base` and retains cloned spans in FIFO arrival order, exporting the oldest spans to its registered [[FB_SpanExporter]] in bounded batches. Its underlying `FB_SpanQueue` is unbounded; `maxQueueSize` is enforced by the processor's explicit drop policy.

It observes the same two-phase notification described in [[FB_SpanProcessor_Simple]]: `onStart` when [[FB_Tracer]] creates the span, `onEnd` when the span is complete. Only `onEnd` clones and queues.

## Configuration

- **`maxQueueSize: UDINT := 2048`** — Maximum retained spans. Zero is unbounded. When a nonzero limit is exceeded, the oldest span is deleted to retain the newest span.

- **`scheduledDelayMillis: UDINT := 1000`** — Maximum time a partial batch waits before becoming eligible for export.

- **`maxExportBatchSize: UDINT := 512`** — Maximum spans transferred per export. Zero disables export attempts.

- **`lastOperationSucceeded: BOOL` and `failureResult: E_SpanProcessorFailureReason`** — Report the most recent clone, queue, or export operation result.

## Methods

- **`onStart(span: REFERENCE TO FB_Span)`** — No-op. Spans are not queued at start, because a started span is still mutable and its clone would capture an incomplete end time and status.

- **`onEnd(span: REFERENCE TO FB_Span)`** — Calls `enrich`, clones the span, and queues the clone even when no exporter is registered. Clone and queue failures are reported through the status outputs. If the configured queue limit is exceeded, the oldest queued span is deleted.

- **`enrich(span: FB_Span)`** — No-op extension point invoked before every clone.

- **`call()`** — Advances the schedule-delay timer and registered exporter. If the exporter is available and not busy, exports up to `maxExportBatchSize` oldest spans when a full batch is available or the delay has elapsed. A busy exporter leaves the queue untouched for a later cycle. Without a registered exporter, spans remain queued until dropped by `maxQueueSize` or released by `free()`.

  The function-block body invokes `call()`, so `processor()` and `processor.call()` advance the same cyclic behavior.

- **`free()`** — Releases every queued span and resets the schedule-delay timer. Normal destruction also invokes this method.

## Drop policy and traces

Dropping the oldest span under queue pressure is correct for logs, where records are independent, but it silently produces broken traces: a dropped parent leaves orphaned children referencing a `parent_span_id` the collector never receives. Most collectors render these as partial traces rather than discarding them, so this is a degradation rather than a failure, but the batch size and queue limit should be tuned against the deepest expected span tree. Whether to add a span-aware drop policy that evicts whole traces is deferred until there is a real workload to measure.
