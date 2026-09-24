---
type: model
domain: tracing
status: partial
implements:
  - FB_TracerProvider
source: TcOtlp/test/OTEL/TRACING/PROVIDER/FUNCTION_BLOCKS/FB_TracerProvider.TcPOU
gap: FB_Init, resource, idGenerator and the ended-span queue (onEnd) exist; calling the generator's tick each cycle and handing queued spans to processors are not implemented.
---

The `FB_TracerProvider` is instantiated with a reference to a `FB_Resource` and it passed as a reference to [[FB_Tracer]] instances during their instantiation in order for them to inject both scope and resources into `FB_Spans` during processing/exporter. When a [[FB_Span]] is ended via a `FB_Tracer` the `FB_Tracer` uses its reference to the `FB_TracerProvider` to begin the processing pipeline.

The provider is also instantiated with a reference to an [[FB_IdGenerator]] (any `FB_IdGenerator_Base`), and exposes it through its `idGenerator` property:

```iec
tracerProvider: FB_TracerProvider(resource := resource, idGenerator := idGenerator);
```

The generator buffers identifiers ahead of time. [[FB_Tracer]]`.build` takes a span ID from it, plus a trace ID for a root span. When the buffer is empty, `build` fails with `IDENTIFIERS_UNAVAILABLE`, which the caller can retry on a later cycle. The provider is meant to call the generator's `tick` once per cycle to refill the buffer; that call is not implemented yet.

## Ended spans

[[FB_Tracer]]`.endSpan` hands each ended span to the provider through `onEnd(pSpan)`. `onEnd` takes ownership and clears the caller's pointer on success; on failure the pointer is left unchanged and the caller still owns the span.

The provider keeps ended spans in an `FB_SpanQueue` bounded by `TcOtlp_GVL.MAX_SPAN_RECORDS_PER_SCAN`, mirroring the log-record queue in `FB_LoggerProvider`. A full queue releases its oldest span and counts it in `droppedCount`. The queue releases whatever is left when the provider is destroyed. Nothing drains the queue yet: handing spans to [[FB_SpanProcessor_Simple]] is the next step.
