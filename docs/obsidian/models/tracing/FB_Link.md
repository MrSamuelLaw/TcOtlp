---
type: model
domain: tracing
status: implemented
implements:
  - FB_Link
  - FB_Links
  - LinkFactory
source: TcOtlp/otel/OTEL/TRACING/LINK/FUNCTION_BLOCKS/
gap: No cloneLink yet; nothing needs to copy a link until spans are cloned.
---

Links are immutable VALUE OBJECTS used to link **Asynchronous** spans together in a so that the context is not lost. For example, a trigger from a SCADA system causes two chiller pump skids to start up. The sending of the data from SCADA is a single root span that takes a few milliseconds, logging the write commands. The chiller pump skids then initiate one trace each that are independent of the trigger from SCADA, in other words, SCADA is not keeping the trace "on ice" while it waits for the skids. The two skids then start up, with each step of the startup sequence being a child span of the root span that is linked to the SCADA span, because the parent span duration is the sum of the child span durations.

# FB_Link
A link holds its own copies of the linked context's `traceId`, `spanId` and `traceState`, plus `flags` and `attributes`. It owns every pointer member and releases them in `free`; release a link with `pLink^.delete(pSelf:=pLink)`. `flags` uses the same encoding as a span's parent flags: the W3C trace flags in bits 0-7, bit 8 when remoteness is known and bit 9 when the linked context is remote (see [[FB_SpanContext]]).

# LinkFactory
The LinkFactory creates links and keeps their invariants: a link always points at a valid span context and owns copies of its identity. Both methods take `pDest` as `VAR_IN_OUT`; it must be `0`, the caller owns the link on success, and nothing is allocated on failure.

## Methods

### fromContext
Creates an `FB_Link` from an [[FB_SpanContext]], such as one extracted from a SCADA request. The context is borrowed, so it can be released straight after. Rejects a null context and one whose `isValid()` is `FALSE`.

### fromSpan
Creates an `FB_Link` to an [[FB_Span]] the caller holds, through `ContextFactory.fromSpan`. The span is unchanged, and the link is local: bit 8 set, bit 9 clear.

`E_LinkFailureReason`:

| Reason | Cause |
| --- | --- |
| `DESTINATION_ALREADY_ASSIGNED` | `pDest` was not `0`. |
| `CONTEXT_POINTER_NULL`, `SPAN_POINTER_NULL` | The context or span pointer was null. |
| `CONTEXT_INVALID` | The context, or the span's identity, has an all-zero trace ID or span ID. |
| `MEMORY_ALLOCATION_FAILURE` | Dynamic memory allocation failed. |

# FB_Links
`FB_Span.links` holds a span's links, oldest first, and owns them.

- **`push(pValue)`** takes ownership and clears the caller's pointer. A null link fails with `LINK_POINTER_NULL`.
- A full collection keeps the links it has, as the OpenTelemetry limits require. `push` refuses the new link with `LINK_COUNT_LIMIT_REACHED`, counts it in `droppedCount`, and leaves it with the caller to release. The bound is `maxCount`, `TcOtlp_GVL.DEFAULT_MAX_LINK_COUNT` (128) on a span, and never more than `MAX_LOOP_COUNT`.
- **`pop(pValue)`** hands the oldest link back to the caller, or fails with `LINKS_EMPTY`.
- **`reset`** and **`next`** walk the links without taking them, for serializers.
- **`free`** releases every link and clears `droppedCount`. `FB_Span.free` calls it.

# Adding links to a span
[[FB_Tracer]]`.addLink(pContext)` links the span being built; see the chain there. `addSpanLink(pSpan, pContext)` does the same for a running span. A link with attributes is built with `LinkFactory`, given attributes, and pushed to the running span with `pushSpanLink`, which takes the link whether or not it succeeds:

```iec
IF LinkFactory.fromSpan(pDest := pLink, pSpan := pScadaSpan) THEN
	pLink^.attributes.setStringAttribute(key := 'trigger', value := 'setpoint');
END_IF
tracer.pushSpanLink(pSpan := pSpan, pLink := pLink);  // pLink is 0 afterwards
```
