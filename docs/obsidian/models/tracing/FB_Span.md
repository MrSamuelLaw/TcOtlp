---
type: model
domain: tracing
status: implemented
implements:
  - FB_Span
source: TcOtlp/test/OTEL/TRACING/SPAN/FUNCTION_BLOCKS/FB_Span.TcPOU
---

`FB_Span` is one timed operation in a trace. A log record is complete the moment it is emitted. A span is different because it has a lifecycle: it is built, it runs while the work it measures is in progress, and then it ends. Only an ended span is complete, and only an ended span is exported.

## Lifecycle

A span is always dynamically allocated and always has exactly one owner. Ownership moves at each stage, and every move clears the previous owner's pointer.

```text
startSpan ──► building ──► build(pDest) ──► running ──► endSpan(pSpan) ──► ended
             (tracer owns)                 (caller owns)                  (provider owns)
```

### 1. Building

[[FB_Tracer]]`.startSpan` allocates the span, and the tracer's fluent setters fill it in. While the chain runs, the span is held in `tracer.pSpan` and owned by the tracer. Each setter validates its input, and the rest of the chain keeps the first failure.

### 2. Running

`build(pDest)` ends the chain.

- On success, it assigns the identifiers, hands the pointer to the caller through `pDest`, and clears `tracer.pSpan`.
- On failure, it releases the incomplete span, leaves `pDest` at `0`, and reports the first failure.

This is where spans differ from the logging pipeline. A log record is *emitted* to the provider at the end of its chain. A span is *returned* to the caller, because its work has only just begun.

While the span runs, the caller owns it. The caller can take a context from it for a child span or a link (`getContext`), set its status, add attributes, and push links. Processors cannot see a running span yet.

### 3. Ended

`tracer.endSpan(pSpan)` stamps the end timestamp, hands the span to [[FB_TracerProvider]] for the processors' `onEnd`, and clears the caller's pointer. From then on the span is immutable. The provider queues it in an `FB_SpanQueue` until its next `tick`, which passes it to every staged processor and then releases it (see [[FB_SpanProcessor_Simple]]).

A caller that abandons a running span releases it with `pSpan^.delete(pSelf:=pSpan);`, for example when the PLC program resets. An abandoned span is never exported.

## Members

The fields the tracer writes during building are `VAR_INPUT`, as on `FB_LogRecord`. The collections are `VAR_OUTPUT` instances.

| Member | Owned | Set by |
| --- | --- | --- |
| `name: POINTER TO FB_String` | yes | `startSpan` |
| `kind: E_SpanKind` | — | `startSpan` |
| `startTimestamp: ULINT` | — | `startSpan`, in Unix-epoch nanoseconds |
| `endTimestamp: ULINT` | — | `endSpan`, in Unix-epoch nanoseconds |
| `traceId: POINTER TO FB_TraceId` | yes | `setParent`, or `build` for a root span |
| `spanId: POINTER TO FB_SpanId` | yes | `build` |
| `parentSpanId: POINTER TO FB_SpanId` | yes | `setParent`; `0` for a root span |
| `traceState: POINTER TO FB_String` | yes | `setParent`, copied from the parent |
| `flags: UDINT` | — | `setParent`, or `build` for a root span |
| `status: POINTER TO FB_Status` | yes | `setStatusOk` and `setStatusError` on a running span |
| `attributes`, `links`, `resource`, `scope` | yes | setters and `addLink`, or `links.push` on a running span; `startSpan` snapshots the resource and scope |

`free` releases everything the span owns, and `FB_Exit` calls it. `delete` releases the span itself and clears the caller's pointer; it is called as `pSpan^.delete(pSelf:=pSpan)` and refuses any pointer other than one to the span itself.

## Flags

A span's `flags` describe its **parent's** remoteness, not its own:

- **Bits 0–7** are the W3C trace flags, inherited from the parent. There is no sampler yet and every span is recorded, so a root span sets the sampled bit.
- **Bit 8** (`SPAN_FLAGS_CONTEXT_HAS_IS_REMOTE_MASK`) is always set, because the tracer always knows where the parent came from.
- **Bit 9** (`SPAN_FLAGS_CONTEXT_IS_REMOTE_MASK`) is set when the parent context is remote, meaning it came from `TraceContextPropagator.extract`.

## Methods

### getContext

Creates an [[FB_SpanContext]], an immutable VALUE OBJECT that snapshots this span's identity.

The context is dynamically allocated through `ContextFactory.buildContext`, following the factory idiom:

```iec
getContext(pDest: POINTER TO FB_SpanContext, failureReason) : BOOL
```

`pDest` is `VAR_IN_OUT` and must be `0` on entry. On success the caller owns the context and releases it exactly once with `pContext^.delete(pSelf:=pContext);`.

The span is the producer, so it is responsible for its identifiers being valid. They come from [[FB_IdGenerator]], which only hands out valid ones, so `getContext` does not check them again.

A span's `flags` describe its parent, so a context taken from a local span is local whatever its parent was. `getContext` keeps only the W3C trace flags (bits 0–7), sets `SPAN_FLAGS_CONTEXT_HAS_IS_REMOTE_MASK` and leaves `SPAN_FLAGS_CONTEXT_IS_REMOTE_MASK` clear. That means remoteness is known, and the span is not remote.

### setStatusOk, setStatusError

Fluent setters for a running span; both return the span, so they chain. They follow the OpenTelemetry status rules:

- `setStatusOk()` sets `STATUS_CODE_OK` with no message. OK is final: it replaces an earlier error and its message.
- `setStatusError(message)` sets `STATUS_CODE_ERROR` and keeps its own copy of `message`. An empty message leaves the status without one. A later error replaces an earlier one. On a span that is already OK, the error is ignored and `failureReason` is `STATUS_ALREADY_OK`.

Both build the new `FB_Status` before releasing the old one. If memory runs out, the previous status is kept and `failureReason` is `MEMORY_ALLOCATION_FAILURE`. A span that never sets a status is exported without one, which means unset.

```iec
pStep^.setStatusOk();
pStep^.setStatusError('setpoint not reached');
```

`FB_TestSpanSimulation` ends step-a as OK, and step-b and the process as errors.

## TODO

- [x] Give `flags` backing storage. `flags` is now a field that the tracer sets from the parent.
- [x] Test a span whose parent is remote. The span's flags have bits 8 and 9 set plus the sampled bit. `getContext` must keep the sampled bit, set bit 8 and clear bit 9, and the context's `isRemote()` must return `FALSE`. `FB_TestTracer` covers this.
- [x] [[FB_Tracer]] sets bits 8 and 9 on a span whose parent is a remote context.
- [x] `tracer.endSpan(pSpan)`: stamp the end timestamp, hand the span to the provider, and clear the caller's pointer.
- [x] `setStatusOk` and `setStatusError`.
- [x] Adding links to a building span with `addLink`, or to a running span with `links.push`. See [[FB_Link]].

`ContextFactory` intentionally does not enforce remoteness; it stores whatever flags it is given. Tests verify that `getContext` always produces a local context. Only `TraceContextPropagator.extract` should produce a remote one. See [[FB_SpanContext]].
