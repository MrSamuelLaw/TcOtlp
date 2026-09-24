---
type: model
domain: tracing
status: implemented
implements:
  - FB_SpanProcessor_Batch
source: TcOtlp/test/OTEL/TRACING/PROCESSORS/FUNCTION_BLOCKS/FB_SpanProcessor_Batch.TcPOU
gap: There is no forceFlush, so spans still queued when the PLC stops are lost. onStart is not part of the processor contract.
---

`FB_SpanProcessor_Batch` extends `FB_SpanProcessor_Base`. It keeps cloned spans in a bounded FIFO queue and hands the oldest of them to its [[FB_SpanExporter]] in batches. It mirrors `FB_LogRecordProcessor_Batch` from [[FB_LogRecordProcessor]].

Use it with any exporter that stays busy for more than one scan, such as `FB_SpanExporter_File`. [[FB_SpanProcessor_Simple]] drops every span that ends while the exporter is busy, so spans that end close together are lost. The batch processor keeps those spans and sends them in the next batch.

## Configuration

`FB_Init` takes every argument. TwinCAT does not apply defaults when the instance is declared with arguments.

```iec
exporter: FB_SpanExporter_File(filepath:='C:\otel\spans.jsonl');
processor: FB_SpanProcessor_Batch(maxQueueSize:=256, scheduledDelayMillis:=1000, maxExportBatchSize:=64, exporter:=exporter);
```

- **`maxQueueSize`**: the most spans the processor keeps. It is held to `TcOtlp_GVL.MAX_LOOP_COUNT`, and zero means that limit. When the queue is full, the oldest span is deleted to make room for the newest.
- **`scheduledDelayMillis`**: the longest a partial batch waits after the queue stops being empty.
- **`maxExportBatchSize`**: the most spans handed to one export. Zero never exports.
- **`exporter`**: borrowed, and it must outlive the processor. Pass 0 to drop every span.

## Outputs and properties

- **`failureReason: E_SpanProcessorFailureReason`**: the result of the last `onEnd` or export attempt. The values are `NA`, `SPAN_CLONE_FAILURE`, `QUEUE_PUSH_FAILURE` and `EXPORT_FAILURE`.
- **`queuedCount`**: the number of spans waiting for export.
- **`droppedCount`**: the number of spans lost so far. It counts spans pushed out of a full queue and spans that could not be cloned or queued. Watch this value to size the queue.

## Methods

- **`onEnd(span)`**: ignores an invalid span, and ignores every span when there is no exporter. Otherwise it calls `enrich`, clones the span, and pushes the clone onto the queue. Nothing is exported during `onEnd`.
- **`enrich(span)`**: a no-op extension point that runs before the clone.
- **`tick()`**: [[FB_TracerProvider]] calls it once per scan, after handing out the ended spans. It advances the schedule-delay timer and ticks the exporter. Then, if the exporter is not busy, it exports up to `maxExportBatchSize` of the oldest spans, either once the delay has passed or as soon as a full batch is waiting. Spans the exporter accepts belong to the exporter. If the export fails, the spans stay queued for the next tick.
- **`free()`**: releases every queued span and restarts the delay. `FB_Exit` calls it.

The exporter is ticked before the export check. So an exporter that finishes a batch during this tick can take the next batch in the same tick.

## Drop policy and traces

Records in a log are independent, so dropping the oldest one under queue pressure is fine. Spans are not independent: if a parent span is dropped, its children point to a `parentSpanId` that the collector never receives. Most collectors still show the result as a partial trace, so the trace is degraded rather than lost. Size `maxQueueSize` for the deepest span tree you expect, and check `droppedCount`. A drop policy that removes whole traces is deferred until there is a real workload to measure.

## Verified behaviour

`FB_TestSpanProcessors` checks that:

- spans are only queued until a full batch or the delay;
- spans are kept while the exporter is busy and sent oldest first;
- a full queue drops its oldest span and counts it;
- nothing is kept without an exporter;
- a partial batch waits for `scheduledDelayMillis`.

`FB_TestSpanSimulation` runs the manufacturing example from [[Tracing Implementation Research]] through the provider and `FB_SpanExporter_File`. `step-b` and the process span end in the same scan and are written to the file as one batch.
