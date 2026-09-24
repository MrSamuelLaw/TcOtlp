---
type: model
domain: tracing
status: partial
implements:
  - FB_SpanExporter_Base
  - FB_SpanExporter_File
source: TcOtlp/test/OTEL/TRACING/EXPORTING/FUNCTION_BLOCKS/
gap: There is no console or HTTP span exporter, and register is not implemented, so nothing stops two processors from sharing one exporter.
---

`FB_SpanExporter_Base` defines the ownership and coordination contract shared by span exporters. It mirrors [[FB_LogRecordExporter]]. Processors check `isBusy()` before offering a batch, and they call `tick` every scan to advance the exporter's destination work. The exporter is the only tracing component allowed to perform destination I/O.

Only ended spans reach an exporter. A span that has been started but not ended is never offered for export, so the exporter never has to reason about mutable spans.

## Methods

- **`export(spans: FB_SpanQueue, count: UDINT, failureReason: E_SpanExporterFailureReason) -> BOOL`** — If the exporter is busy, returns `FALSE` with `ACTIVE_EXPORT_IN_PROGRESS` and leaves the source queue unchanged. Otherwise, transfers ownership of up to `count` oldest spans from the source queue into the exporter without cloning them. Accepted spans are removed from the source queue. A `count` of zero transfers no spans. Queue-transfer failure returns `FALSE`; successful transfer returns `TRUE`, including an empty transfer.

- **`isBusy() -> BOOL`** — Reports whether the exporter can currently accept another batch.

- **`tick(failureReason: E_SpanExporterFailureReason) -> BOOL`** — Advances the concrete exporter's cyclic work and reports destination-specific failure. The processor that owns the exporter calls it once per provider tick.

- **`free()`** — Releases all spans currently owned by the exporter and clears its active-export flag. `FB_Exit` invokes this during normal destruction.

## Concrete exporters

Concrete exporter function-block bodies invoke `tick()`.

| Exporter | Status | Busy semantics |
| --- | --- | --- |
| `FB_SpanExporter_File` | Implemented | Busy while its serialization and file-I/O state machine owns a batch, which takes several scans; exposes that state through `currentState`. |
| `FB_SpanExporter_Console` | Not built | Never busy; would write accepted spans synchronously before releasing the batch. |
| `FB_SpanExporter_HTTP` | Not built | Busy for the duration of the OTLP/HTTP request/response cycle. |

### FB_SpanExporter_File

`FB_Init(filepath)` sets the target file. Each accepted batch is appended to the file as one line of JSON, a complete `TracesData` object, so the file is JSON Lines. The state machine runs `idle`, `serializing`, `opening`, `buffering`, `writing`, `closing`, then `done`, or `error` on a failure. The batch is released in `done` or `error`. In both states `export` accepts a new batch straight away.

The exporter starts whenever it holds a batch, not on a rising edge. A batch accepted in the scan straight after the previous one finished therefore still starts. The rising-edge version left such a batch stuck, with `isBusy()` TRUE forever.

Use it with [[FB_SpanProcessor_Batch]]. The exporter stays busy for several scans, and [[FB_SpanProcessor_Simple]] drops every span that ends in that time.

## Serialization

File and HTTP exporters serialize with [[Spans ProtoJSON Serializer]], which reads the batch without taking ownership, so the exporter keeps the batch until delivery finishes.

## Open questions

- Whether an exporter must preserve parent-before-child ordering within a batch, or whether the collector reassembles the tree from `parent_span_id` alone. The OTLP spec allows arbitrary ordering; confirming this lets the batch processor stay a simple FIFO.
