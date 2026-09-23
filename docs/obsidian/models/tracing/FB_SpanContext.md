---
type: model
domain: tracing
status: implemented
implements:
  - FB_SpanContext
  - ContextFactory
source: TcOtlp/test/OTEL/TRACING/SPAN/
gap: FB_Span.getContext is implemented; TraceContextPropagator.extract is not. The parent-remote flags case is untested (see FB_Span TODO).
---

`FB_SpanContext` is the immutable VALUE OBJECT that identifies a span well enough for something outside this PLC to place it in the same trace. It is what crosses a boundary: it is serialized and propagated alongside a distributed context, attached to a [[FB_Link]], and quoted by a log record for correlation.

The distinction that matters is that a context is not a span. A [[FB_Span]] is mutable, has a duration, and is still being written to; a context is a fixed snapshot of the identity of one span, taken with `getContext` and valid after the span it came from has ended. Nothing on a context can be edited after it is created, so a holder never has to ask whether the span it came from has moved on.

## Invariants

- The trace ID and span ID are copies, not borrowed references. A context outlives the span it was taken from, so it cannot hold pointers into that span's storage.
- The trace state is a copy owned by the context and released with it.
- No member has a setter. Every field is fixed at construction.
- A context does not validate its own identity. **Producers validate**: [[FB_IdGenerator]] never hands out an all-zero identifier, and `TraceContextPropagator.extract` rejects a carrier that would produce one. A context built from all-zero identifiers is still created; it reports `isValid() = FALSE`, which is how OpenTelemetry represents "no span", for example the parent of a root span.

## Creation and ownership

A context is always dynamically allocated through `ContextFactory.buildContext`. It cannot be declared as a plain variable, because its `FB_Init` takes the identity as arguments.

```iec
ok := ContextFactory.buildContext(
	pDest:=pContext,            // VAR_IN_OUT, must be 0
	pTraceId:=ADR(traceId),
	pSpanId:=ADR(spanId),
	pTraceState:=ADR(state),    // optional; 0 means none
	traceFlags:=flags,
	failureReason=>reason);
```

`ContextFactory` follows the `ValueFactory` idiom: a `PROGRAM`, a `BOOL` return, a `VAR_IN_OUT` destination pointer that must be `0` on entry, and an `E_ContextFactoryFailureReason` on an output. It checks only its arguments, never the identity:

| Failure reason | Cause |
| --- | --- |
| `DESTINATION_ALREADY_ASSIGNED` | `pDest` was not `0`. The factory never overwrites a pointer the caller already owns. |
| `TRACE_ID_POINTER_NULL` | `pTraceId` was `0`. |
| `SPAN_ID_POINTER_NULL` | `pSpanId` was `0`. |
| `MEMORY_ALLOCATION_FAILURE` | The trace state copy or the context itself could not be allocated. |

The trace state is copied first, through `ValueFactory.createString`, and the context is allocated last. If allocating the context fails, the factory deletes the trace state copy, so a failed call leaves nothing allocated and `pDest` still `0`.

On success the caller owns the context and releases it exactly once:

```iec
pContext^.delete(pSelf:=pContext);
```

`delete` runs `FB_Exit`, which frees the trace state. `free` can also be called directly to release the trace state and clear the identity early; it is safe to call more than once. During an online change `FB_Exit` skips `free`, because the copied instance keeps the trace state pointer.

## Members

Every member is private and exposed through a get-only property.

### traceId: FB_TraceId

The 16-byte identifier of the trace this span belongs to, copied from the span. Shared by every span in the trace, which is what makes a remote consumer able to join them up. The property returns a reference.

### spanId: FB_SpanId

The 8-byte identifier of the span itself. Unique within the trace; this is the value a child span or a link points back to as its parent. The property returns a reference.

### traceState: POINTER TO FB_String

The W3C `tracestate` list — vendor-specific key/value pairs carried along the trace untouched. It is optional and often empty; `0` means the context carries none. The pointer is borrowed: the context owns the string and releases it.

### traceFlags: UDINT

The span-flags word, as defined by `E_SpanFlags`:

- Bits 0–7 (`SPAN_FLAGS_TRACE_FLAGS_MASK`) are the W3C trace flags; bit 0 is the sampled flag.
- Bit 8 (`SPAN_FLAGS_CONTEXT_HAS_IS_REMOTE_MASK`) says whether remoteness is known.
- Bit 9 (`SPAN_FLAGS_CONTEXT_IS_REMOTE_MASK`) says whether the span is remote.
- Bits 10–31 are reserved.

The flags are stored as one word rather than as separate fields because that is the shape OTLP puts on the wire, and because bits 8 and 9 only mean anything as a pair.

## Methods

### isRemote

isRemote is a **method**, not a field, because it is a decode of the flags word rather than a fact stored beside it. Bit 8 and bit 9 have to be read together: bit 9 alone cannot distinguish "local" from "not known", and a stored boolean would flatten the three-state answer into two. Keeping the decode in one method also means the mask constants stay in `E_SpanFlags` instead of being restated at every call site.

`TRUE` means the span was propagated in from a remote parent — that is, the context was reconstructed from a carrier rather than produced by a local [[FB_Tracer]]. This is the flag a sampler or an exporter uses to tell an inbound trace from one this controller started.

### isValid

isValid is a method, not a field, because it is a function of traceid and spanid. It returns true if and only if the SpanContext has a non-zero TraceID and a non-zero SpanID. It is a query for consumers; nothing in the context or the factory uses it to refuse creation.

### free

Releases the trace state and clears the identifiers and flags. Called by `FB_Exit`, and safe to call again.

### delete

Releases the context itself and clears the caller's pointer: `pContext^.delete(pSelf:=pContext)`. `pSelf` is `VAR_IN_OUT` and is cleared before the context is freed. A pointer to any other object is refused: `delete` returns `FALSE` and releases nothing.

## Creation paths

A context is produced in exactly two ways. Both go through `ContextFactory.buildContext` and both hand the caller an owned pointer:

- **`FB_Span.getContext`** takes a snapshot of a local span. The context is always local: bit 8 set, bit 9 clear. The factory does not enforce this; `FB_TestSpan` does. The case where the span's parent is remote is not tested yet; see the TODO in [[FB_Span]].
- **`TraceContextPropagator.extract`** rebuilds a remote context from a W3C traceparent, setting both remoteness bits. It validates the carrier before building anything. See [[Trace Context Propagation]].

## Open questions

- **Allocation rate.** Every context is a heap allocation. A span-per-cycle rate could make that too expensive; pooling contexts would be the fix, but nothing needs it yet.
- **Three-state remoteness.** `isRemote` returning a plain `BOOL` collapses "known local" and "not known" into `FALSE`. If callers need to tell those apart, the method needs a second output rather than a wider return type.
