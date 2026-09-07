---
type: model
domain: tracing
status: design
implements:
  - FB_SpanProcessor_Simple
---

> [!abstract] Design note — not yet implemented
> No source exists under `TcOtlp/test/OTEL/TRACING/` for this function block. The contract below is intended design, mirroring the implemented `FB_LogRecordProcessor_Simple` described in [[FB_LogRecordProcessor]].

`FB_SpanProcessor_Simple` extends `FB_SpanProcessor_Base` and forwards each ended span to its registered [[FB_SpanExporter]] as soon as the span ends. It has no retained backlog and uses a one-span `FB_SpanQueue` only as a transient ownership-transfer buffer.

## Processor contract

A span processor is notified twice per span, which is the significant difference from the logging pipeline's single `onEmit`:

- **`onStart`** fires when [[FB_Tracer]] creates the span. The span is still mutable and incomplete — it has no end time, no final status, and may gain attributes, events, and [[FB_Link]] entries before it ends. A processor must not clone or export a span here.
- **`onEnd`** fires when the span is ended through its tracer. The span is complete and immutable from this point, and this is the only notification from which a span may be cloned or exported.

[[FB_TracerProvider]] passes the span to each registered processor and deletes the original after all processors return, so a processor that retains a span must clone it. `enrich` runs against the original before cloning, so enrichment by one processor is visible to processors later in the chain.

## Methods

- **`onStart(span: REFERENCE TO FB_Span)`** — No-op in the simple processor. Present so that subclasses can stamp cycle-time or task context at span creation.

- **`onEnd(span: REFERENCE TO FB_Span)`** — Calls `enrich` unconditionally. If a registered exporter exists and is not busy, clones the span, places the clone in its transient queue, and offers one span to the exporter. It then releases anything the exporter did not accept. A missing or busy exporter, clone failure, queue failure, or export failure produces no exported clone and logs no warning.

- **`enrich(span: FB_Span)`** — No-op extension point invoked before the exporter validity and busy checks.

- **`call()`** — Calls the registered exporter's `call()` method. As with the logging simple processor, the function-block body is empty, so invoking `processor()` is not an alias for this method.

- **`free()`** — Releases any span in the transient queue. Normal destruction also invokes this method.

## Trade-off

Because export is attempted inline on `onEnd`, a busy exporter silently drops the span rather than deferring it. This keeps per-cycle work constant and bounded, which is why the simple processor is appropriate for development and console output but not for a network destination. Use [[FB_SpanProcessor_Batch]] when spans must survive a busy exporter.
