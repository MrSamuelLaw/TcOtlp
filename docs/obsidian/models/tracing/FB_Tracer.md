---
type: model
domain: tracing
status: partial
implements:
  - FB_Tracer
  - E_TracerFailureReason
source: TcOtlp/test/OTEL/TRACING/TRACER/FB_Tracer.TcPOU
gap: The fluent build chain (startSpan, setParent, attributes, build) and endSpan are implemented; replaceSpan is not.
---

`FB_Tracer` builds [[FB_Span]] instances with the same fluent chain that `FB_Logger` uses for log records. Each setter validates its input as the chain runs. The difference is at the end of the chain: the logger's `emit` pushes the record to its provider, but the tracer's `build` **hands the span to the caller**, because a span starts running when it is built and ends later. See the lifecycle in [[FB_Span]].

```iec
IF NOT tracer
	.startSpan(name := 'chiller.startup', kind := E_SpanKind.SPAN_KIND_CONSUMER)
	.setParent(pContext := pParentContext)      // optional; omit for a root span
	.setStringAttribute('skid', 'A')
	.setNumberAttribute('setpoint', 42)
	.build(pDest := pSpan, failureReason => reason) THEN
	// CASE reason OF ...
END_IF
```

A tracer is instantiated with a scope and a provider, like a logger:

```iec
tracer: FB_Tracer(scope := scope, provider := tracerProvider);
```

## The chain

The tracer builds one span at a time and holds it in `pSpan` until `build`.

- **`startSpan(name, kind := SPAN_KIND_INTERNAL)`** allocates the span, stamps its start time, copies the name, and snapshots the resource and scope. It fails if the name is empty or the kind is `SPAN_KIND_UNSPECIFIED`. If a span is already being built, the chain fails with `SPAN_ALREADY_STARTED`; the span that is already building is kept, and `build` releases it.
- **`setParent(pContext)`** makes the span a child of the given context. It borrows the context and copies what it needs: the trace ID, the parent span ID, the trace state, and the trace flags. It sets bit 8 of the span's flags, and also bit 9 when the context is remote. It rejects a null pointer and a context whose `isValid()` is `FALSE`. The tracer is the producer of spans, so this is where the parent is validated. Calling it again replaces the parent.
- **`setStringAttribute(key, value)`** and **`setNumberAttribute(key, value)`** add attributes, with the same limits as the logger.
- **`build(pDest, failureReason) : BOOL`** ends the chain. It takes a new span ID from the provider's [[FB_IdGenerator]], and a new trace ID as well for a root span. Identifiers are taken only when everything before them has succeeded, so a failed chain does not consume any. On success the span moves to `pDest`, which is `VAR_IN_OUT` and must be `0` on entry, and `pSpan` is cleared. On failure the incomplete span is released, `pDest` stays `0`, and the first failure in the chain is reported.

A root span sets the sampled bit and bit 8, and leaves bit 9 clear. There is no sampler yet, so every span is recorded.

Processors are not notified when a span is built. The processor contract has an `onStart`, but the provider has no processors yet.

## Failure reasons

`E_TracerFailureReason` reports the first failure in the chain:

| Reason | Cause |
| --- | --- |
| `SPAN_ALREADY_STARTED` | `startSpan` was called while a span was still being built. |
| `SPAN_NOT_STARTED` | A setter or `build` ran without a `startSpan`. |
| `SPAN_NAME_EMPTY` | `startSpan` was given an empty name. |
| `SPAN_KIND_UNSPECIFIED` | `startSpan` was given `SPAN_KIND_UNSPECIFIED`, which OTLP says not to use. |
| `PARENT_CONTEXT_POINTER_NULL` | `setParent` was given a null pointer. |
| `PARENT_CONTEXT_INVALID` | The parent context has an all-zero trace ID or span ID. |
| `ATTRIBUTE_VALUE_INVALID` | An attribute could not be created from the supplied value. |
| `ATTRIBUTE_VALUE_TYPE_UNSUPPORTED` | The attribute value type is not supported. |
| `ATTRIBUTE_COUNT_LIMIT_REACHED` | The span cannot own another attribute. |
| `DESTINATION_ALREADY_ASSIGNED` | `build` was given a `pDest` that was not `0`. |
| `IDENTIFIERS_UNAVAILABLE` | The generator had no identifiers ready. Retry on a later cycle. |
| `ID_GENERATION_FAILURE` | The generator failed for another reason. |
| `SNAPSHOT_COPY_FAILURE` | The resource or scope could not be copied. |
| `MEMORY_ALLOCATION_FAILURE` | Dynamic memory allocation failed. |
| `SPAN_POINTER_NULL` | `endSpan` was given a null pointer. |
| `TRANSFER_TO_PROVIDER_FAILURE` | The provider could not queue the ended span, so it was released. |

## endSpan

```iec
tracer.endSpan(pSpan := pSpan, failureReason => reason);
```

`endSpan` stamps the end timestamp and moves the span into [[FB_TracerProvider]]'s queue through `onEnd`. The caller's pointer is **always cleared**, whether or not the hand-off succeeds: an ended span has no other owner, so if the provider cannot queue it, `endSpan` releases it and reports `TRANSFER_TO_PROVIDER_FAILURE`. That only happens when a queue node cannot be allocated, because a full queue drops its oldest span instead of refusing the new one.

`endSpan` is not part of the fluent chain. It does not read or reset the chain's failure, so it can be called while another span is being built.

## Methods not yet implemented

### replaceSpan

Ends one span and starts the next one linked to it, for sequential steps. The research notes call this `handoffSpan`.
