---
type: model
domain: tracing
status: design
implements:
  - FB_SpanContext
gap: no source file exists yet; FB_SpanContext is design only, and FB_Span.getContext is not implemented.
---

`FB_SpanContext` is the immutable VALUE OBJECT that identifies a span well enough for something outside this PLC to place it in the same trace. It is what crosses a boundary: it is serialized and propagated alongside a distributed context, attached to a [[FB_Link]], and quoted by a log record for correlation.

The distinction that matters is that a context is not a span. A [[FB_Span]] is mutable, has a duration, and is still being written to; a context is a fixed snapshot of the identity of one span, taken with `getContext` and valid after the span it came from has ended. Nothing on a context can be edited after it is created, so a holder never has to ask whether the span it came from has moved on.

## Invariants

- The trace ID and span ID are copies, not borrowed references. A context outlives the span it was taken from, so it cannot hold pointers into that span's storage.
- A context is created valid or not at all. The OTLP validity rules from [[FB_IdGenerator]] apply: a trace ID is 16 bytes and MUST NOT be all zeroes, a span ID is 8 bytes and MUST NOT be all zeroes. An all-zero identifier is the OTLP spelling of "absent", so it can never appear in a context that exists.
- No member has a setter. Every field is fixed at construction.

## Members

### traceId: FB_TraceId

The 16-byte identifier of the trace this span belongs to, copied from the span. Shared by every span in the trace, which is what makes a remote consumer able to join them up.

### spanId: FB_SpanId

The 8-byte identifier of the span itself. Unique within the trace; this is the value a child span or a link points back to as its parent.

### traceState: FB_String

The W3C `tracestate` list — vendor-specific key/value pairs carried along the trace untouched. [[FB_Span]] already holds it as a `POINTER TO FB_String`, and the context copies it. It is optional and often empty.

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

isValid is a method, not a field, because it is a function of traceid and spanid. It returns true if and only if the SpanContext has a non-zero TraceID and a non-zero SpanID.
## Creation paths

A context is produced in exactly two ways, and they have different ownership rules:

- **`FB_Span.getContext`** takes a snapshot of a local span. Ownership here is still open — see below.
- **`TraceContextPropagator.extract`** rebuilds a remote context from a W3C traceparent, setting both remoteness bits. It fills a caller-owned instance rather than allocating, because the extracted context lives only long enough to build a [[FB_Link]]. See [[Trace Context Propagation]].

## Open questions

- **Ownership on creation.** `FB_Span.getContext` is sketched as handing back a `POINTER TO FB_SpanContext`, which makes the caller the owner and obliges it to release the context exactly once. Whether the out parameter is `VAR_IN_OUT` so a failed call can zero it, and whether contexts are pooled rather than allocated per call, are both undecided. A span-per-cycle rate would make per-call allocation the wrong default. The extract path does not have this problem, having settled on a caller-owned instance.
- **Three-state remoteness.** `isRemote` returning a plain `BOOL` collapses "known local" and "not known" into `FALSE`. If callers need to tell those apart, the method needs a second output rather than a wider return type.
