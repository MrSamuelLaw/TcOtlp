---
type: model
domain: tracing
status: implemented
implements:
  - FB_SpanProcessor_Base
  - FB_SpanProcessor_Simple
source: TcOtlp/test/OTEL/TRACING/PROCESSORS/FUNCTION_BLOCKS/
gap: onStart is not part of the contract yet.
---

`FB_SpanProcessor_Simple` extends `FB_SpanProcessor_Base` and handles each ended span as soon as [[FB_TracerProvider]] hands it over: `enrich`, then `export`. It keeps nothing between calls.

To write spans to the TwinCAT ADS log, give it an `FB_SpanExporter_Console`; see [[FB_SpanExporter]].

## Processor contract

[[FB_TracerProvider]] stages processors each scan with `stageProcessor`. Its `tick` passes every ended span to `onEnd` of each staged processor, in staging order, and releases the span once they have all returned. The span is borrowed, so a processor that keeps it past `onEnd` must clone it. `enrich` runs against the original, so one processor's enrichment is visible to the processors after it.

Only ended spans reach a processor. The OpenTelemetry `onStart` notification is not implemented; add it to the base when a processor needs to act on span creation.

## FB_SpanProcessor_Base

Abstract. It declares:

- `onEnd(span: REFERENCE TO FB_Span)`
- `enrich(span: FB_Span)` (VAR_IN_OUT)
- `tick()`
- `free()`
- the `pSelf` property the provider uses to stage it

## FB_SpanProcessor_Simple

- **`onEnd`** ignores an invalid reference, then calls `enrich` and `export`.
- **`enrich`** is a no-op extension point.
- **`export`** does nothing when there is no exporter or the exporter is busy. Otherwise it clones the span and offers the clone to the [[FB_SpanExporter]] as a batch of one. The exporter owns the clone once it accepts it. If the clone or the hand-off fails, the clone is released. Override `export` to send spans somewhere else.
- **`tick`** ticks the exporter. **`free`** releases a clone left by a failed hand-off, because the processor keeps nothing between calls.
- `FB_Init(exporter)` borrows the exporter, which must outlive the processor. Declare it with `exporter:=0` to drop every span.

## Trade-off

The simple processor keeps nothing. A span that ends while the exporter is busy is dropped, and no counter records the drop. `FB_SpanExporter_Console` is never busy, so nothing is dropped with it. Exporters that take several scans, such as `FB_SpanExporter_File`, stay busy after each span. So spans that end in the same scan, or within a few scans of each other, are lost. Use [[FB_SpanProcessor_Batch]] with those exporters.
