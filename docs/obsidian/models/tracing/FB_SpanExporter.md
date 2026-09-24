---
type: model
domain: tracing
status: design
implements:
  - FB_SpanExporter_Base
---

> [!abstract] Design note — not yet implemented
> No source exists under `TcOtlp/test/OTEL/TRACING/` for this function block. The contract below is intended design, mirroring the implemented [[FB_LogRecordExporter]].

`FB_SpanExporter_Base` defines the ownership and coordination contract shared by span exporters. Processors query `isBusy()` before offering a batch and call the exporter cyclically to advance destination-specific work. The exporter is the only tracing component permitted to perform destination I/O.

An exporter accepts at most one processor identity. The first call to `register` succeeds, and another call from the same processor also succeeds. A different processor is rejected and an ADS error is logged. Processor initialization retains its exporter reference only when this registration succeeds.

Only ended spans reach an exporter. A span that has been started but not ended is never offered for export, so the exporter never has to reason about mutable spans.

## Methods

- **`export(spans: FB_SpanQueue, count: UDINT, failureReason: E_SpanExporterFailureReason) -> BOOL`** — If the exporter is busy, returns `FALSE` with `ACTIVE_EXPORT_IN_PROGRESS` and leaves the source queue unchanged. Otherwise, transfers ownership of up to `count` oldest spans from the source queue into the exporter without cloning them. Accepted spans are removed from the source queue. A `count` of zero transfers no spans. Queue-transfer failure returns `FALSE`; successful transfer returns `TRUE`, including an empty transfer.

- **`register(processor: FB_SpanProcessor_Base) -> BOOL`** — Registers the processor's `pSelf` identity and enforces the one-processor-per-exporter constraint.

- **`isBusy() -> BOOL`** — Reports whether the exporter can currently accept another batch.

- **`call(failureReason: E_SpanExporterFailureReason) -> BOOL`** — Advances the concrete exporter's cyclic work and reports destination-specific failure.

- **`free()`** — Releases all spans currently owned by the exporter and clears its active-export flag. `FB_Exit` invokes this during normal destruction.

## Concrete exporters

Concrete exporter function-block bodies invoke `call()`. The intended set mirrors logging:

| Exporter | Busy semantics |
| --- | --- |
| `FB_SpanExporter_Console` | Never busy; writes accepted spans synchronously before releasing the batch. |
| `FB_SpanExporter_File` | Busy while its serialization and file-I/O state machine owns a batch; exposes that state through `currentState`. |
| `FB_SpanExporter_HTTP` | Busy for the duration of the OTLP/HTTP request/response cycle. |

## Serialization

File and HTTP exporters serialize with [[Spans ProtoJSON Serializer]], which reads the batch without taking ownership, so the exporter keeps the batch until delivery finishes.

## Open questions

- Whether an exporter must preserve parent-before-child ordering within a batch, or whether the collector reassembles the tree from `parent_span_id` alone. The OTLP spec allows arbitrary ordering; confirming this lets the batch processor stay a simple FIFO.
