---
type: model
domain: tracing
status: partial
implements:
  - FB_TracerProvider
source: TcOtlp/test/OTEL/TRACING/PROVIDER/FUNCTION_BLOCKS/FB_TracerProvider.TcPOU
gap: Implemented except for onStart notifications to processors, which the processor contract does not have yet.
---

The `FB_TracerProvider` is instantiated with a reference to a `FB_Resource` and it passed as a reference to [[FB_Tracer]] instances during their instantiation in order for them to inject both scope and resources into `FB_Spans` during processing/exporter. When a [[FB_Span]] is ended via a `FB_Tracer` the `FB_Tracer` uses its reference to the `FB_TracerProvider` to begin the processing pipeline.

The provider is also instantiated with a reference to an [[FB_IdGenerator]] (any `FB_IdGenerator_Base`), and exposes it through its `idGenerator` property:

```iec
tracerProvider: FB_TracerProvider(resource := resource, idGenerator := idGenerator);
```

The generator buffers identifiers ahead of time. [[FB_Tracer]]`.build` takes a span ID from it, plus a trace ID for a root span. When the buffer is empty, `build` fails with `IDENTIFIERS_UNAVAILABLE`, which the caller can retry on a later cycle. The provider's `tick` calls the generator's `tick` once per scan to refill the buffer.

## Ended spans

[[FB_Tracer]]`.endSpan` hands each ended span to the provider through `onEnd(pSpan)`. `onEnd` takes ownership and clears the caller's pointer on success; on failure the pointer is left unchanged and the caller still owns the span.

The provider keeps ended spans in an `FB_SpanQueue` bounded by `TcOtlp_GVL.MAX_SPAN_RECORDS_PER_SCAN`, mirroring the log-record queue in `FB_LoggerProvider`. A full queue releases its oldest span and counts it in `droppedCount`. The queue releases whatever is left when the provider is destroyed.

## Processing

Processors are staged each scan, as in `FB_LoggerProvider`, and `tick` is called once afterwards:

```iec
provider.stageProcessor(consoleProcessor);
// ... tracers start and end spans ...
provider.tick(failureReason => reason);
```

- **`stageProcessor(processor)`** borrows any `FB_SpanProcessor_Base` for the next tick and returns the provider, so calls chain. Staging the same processor twice has no effect. `stagedProcessorCount` reports how many are staged.
- **`tick(failureReason)`**, in order:
  1. Pops each queued span and passes it to `onEnd` of every staged processor, in staging order, then releases it.
  2. Calls `tick` on each processor.
  3. Calls the id generator's `tick`.

  It always clears the queue and the staged list, so a span is never carried into the next scan. Spans are only queued while at least one processor is staged, because [[FB_Tracer]]`.endSpan` releases a span straight away when none is.

`tick` returns `FALSE` with an `E_TracerProviderFailureReason`:

| Failure reason | Cause |
| --- | --- |
| `STAGE_PROCESSOR_FAILURE` | A `stageProcessor` call since the last tick could not allocate its list node. The spans are released unprocessed. |
| `QUEUE_POP_FAILURE` | An ended span could not be popped from the queue. |
| `UNEXPECTED_NULL_LINKED_LIST_NODE` | The staged list was shorter than `stagedProcessorCount`. |
| `UNEXPECTED_NULL_PROCESSOR_POINTER` | A staged processor pointer was null. |
| `ID_GENERATOR_TICK_FAILURE` | The id generator could not advance. Reported only when nothing else failed. |

A staging failure is cleared by `tick`, so the next scan starts clean. See [[FB_SpanProcessor_Simple]] for the processor contract.
