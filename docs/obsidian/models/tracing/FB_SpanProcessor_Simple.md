---
type: model
domain: tracing
status: implemented
implements:
  - FB_SpanProcessor_Base
  - FB_SpanProcessor_Simple
  - FB_SpanProcessor_Console
source: TcOtlp/test/OTEL/TRACING/PROCESSORS/FUNCTION_BLOCKS/
gap: FB_SpanProcessor_Console writes to the ADS log itself, because there is no FB_SpanExporter_Console yet. onStart is not part of the contract yet.
---

`FB_SpanProcessor_Simple` extends `FB_SpanProcessor_Base` and handles each ended span as soon as [[FB_TracerProvider]] hands it over: `enrich`, then `export`. It keeps nothing between calls.

`FB_SpanProcessor_Console` extends it and overrides `export` to write one line per span to the TwinCAT ADS log, for development and commissioning.

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

## FB_SpanProcessor_Console

`export` writes the result of `format` with `ADSLOGSTR` at hint level. `format` is public so tests can check the line without reading the log:

```text
span "work" trace=01010101010101010101010101010101 span=0202020202020202 parent=none kind=SPAN_KIND_INTERNAL status=STATUS_CODE_UNSET duration=500ns
```

- Identifiers are written as lower-case hex.
- A root span is written with `parent=none`.
- A span without a status is written as `STATUS_CODE_UNSET`.
- The duration is `endTimestamp - startTimestamp` in nanoseconds, or 0 if the end is not after the start.
- Attributes, links, resource and scope are not written.
- Lines are truncated at 255 characters.

Declare it with `exporter:=0`, because it overrides `export` and never uses an exporter. Writing to a destination is Log Exporting behaviour, not processing. The console processor mirrors the logging test double `FB_LogRecordProcessor_ConsolePrinter`. Move its output into an `FB_SpanExporter_Console` once span exporters exist.

## Trade-off

The simple processor keeps nothing. A span that ends while the exporter is busy is dropped, and no counter records the drop. Exporters that take several scans, such as `FB_SpanExporter_File`, stay busy after each span. So spans that end in the same scan, or within a few scans of each other, are lost. Use [[FB_SpanProcessor_Batch]] with those exporters.
