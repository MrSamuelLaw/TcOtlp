---
type: model
domain: tracing
status: design
implements:
  - TraceContextPropagator
  - E_PropagationFailureReason
gap: nothing implemented; no source files exist yet.
---

When an external system triggers work in the PLC, something has to decide where one trace ends and the next begins. This document fixes that boundary for the case that motivates it: an Ignition gateway starts a long-running process on the controller.

## The decision

**An inbound trigger starts a new trace in the PLC, linked back to the caller's span. It does not continue the caller's trace.**

The rule that produces this answer is the one already stated in [[FB_Link]] and the tracing research notes:

> Parent/child is for spans where the parent overlaps the child completely. Links are for spans that occur sequentially.

Applied at a system boundary, that becomes a question about the caller: **does it still exist when the callee finishes?**

- **The caller blocks for the result** — a bounded request/response. One trace, parent-child, `CLIENT` on the caller and `SERVER` in the PLC. This is ordinary RPC and needs nothing from this document beyond extraction.
- **The caller fires a trigger and moves on** — the PLC process outlives the call by orders of magnitude. Two traces and a link, `PRODUCER` on the caller and `CONSUMER` on the PLC root.

Starting a chiller skid is the second. The command lands in milliseconds; the startup sequence runs for minutes.

```text
Ignition:  [start command ~ms]
PLC:            [--------------- startup sequence, minutes ---------------]
                ^ link back to the command span
```

### Why not parent-child across the boundary

Making the PLC root a child of the command span produces a child that ends long after its parent. The OTLP data model does not forbid this, but every consumer of the data assumes containment: waterfall rendering, critical-path analysis, duration rollups, and the heuristics backends use to decide a trace is complete once its root ends. The trace would look finished in milliseconds and then accumulate late spans for the rest of the run.

It also forces the caller to hold a span open for the duration and end it on a completion signal it does not have. [[FB_Link]] rejects this explicitly — the caller is not keeping the trace on ice.

### Why not adopt the caller's trace ID

The tempting middle option is to keep the inbound trace ID and start a fresh root span under it: same trace, no parent-child. Avoid it.

One trigger commonly starts several independent processes — two skids from one command, in the [[FB_Link]] example. Sharing the trace ID collapses them into a single trace that never ends cleanly, and the operator asking how long one skid took to start gets one undifferentiated blob instead of an answer per skid. Separate trace IDs keep each run independently queryable. Links are the OTLP mechanism for same-causal-family, different-lifetime; a shared trace ID is not.

## The carrier

A trace ID alone is not enough to build a link. `FB_Link` requires a span ID as well — it refers to *one span*, not to a trace. The carrier is therefore the full W3C traceparent:

```text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Read left to right: version, then the 16-byte trace ID, then the 8-byte span ID of the caller's span, then the trace flags whose bit 0 is the sampled flag. Exactly 55 ASCII characters for version `00`. `tracestate` is a separate, optional value carried verbatim.

### Delivery is atomic

Ignition invokes an RPC method on the PLC rather than writing tags. The trigger and the context arrive as arguments of one call, so there is no window in which the trigger is visible with a stale or half-written context beside it, and no rising-edge latch is needed:

```iecst
{attribute 'TcRpcEnable'}
METHOD startProcess : BOOL
VAR_INPUT
	traceparent: STRING(55);
	tracestate: T_MaxString;
END_VAR
```

The method body extracts the context, starts the local root span with a link to it, and returns. It does not wait for the process.

TwinCAT runs an RPC method in the context of the owning PLC task, so this introduces no second-task concern and needs no guarding, which is consistent with the repository's single-task assumption.

### Optionally, a span for the acceptance itself

The RPC call is short and bounded, so it *can* legitimately be its own `SERVER` span inside the caller's trace, as a child of the caller's `CLIENT` span. That makes command rejection — busy, invalid parameters, process already running — visible from the caller's side, which a link alone does not show. The long-running process remains a separate trace linked to that span. This is optional; the link is the part that matters.

## API

`TraceContextPropagator` follows the existing factory idiom — a `PROGRAM`, `BOOL` return, `VAR_IN_OUT` destination, failure reason on an output — matching `ValueFactory` and `LinkFactory`.

- **`extract(context: FB_SpanContext, traceparent: STRING(55), tracestate: T_MaxString, failureReason: E_PropagationFailureReason) -> BOOL`** — Parses a carrier into a context. Returns `FALSE` and leaves the destination untouched on failure.

- **`inject(context: FB_SpanContext, traceparent: STRING(55), tracestate: T_MaxString, failureReason: E_PropagationFailureReason) -> BOOL`** — Formats a local context for an outbound call, for when the PLC is the caller.

Unlike `ValueFactory`, `extract` fills a caller-owned `FB_SpanContext` instead of allocating one. The extracted context lives only long enough to build a link, so its lifetime is bounded by the call and there is nothing for an allocation to buy. The ownership contract for `FB_Span.getContext`, which is a different path, remains open — see [[FB_SpanContext]].

### Parsing rules

- The length is fixed and the field offsets are constant, so parsing is 24 bytes of hex decode with no loop bound to discover and no allocation. This stays inside the bounded-execution rule without needing a cycle budget.
- Validation follows the OTLP validity rules in [[FB_IdGenerator]]: an all-zero trace ID or span ID is the encoding of "absent" and is rejected. Version `ff` is invalid. An unknown future version is parsed as its first 55 characters rather than rejected.
- **A malformed carrier must not fail the process.** It is treated as though no context arrived: the PLC starts an unlinked root trace and reports the failure reason. Refusing to start a chiller because a trace header was mangled would make observability a source of downtime.
- On success, both `SPAN_FLAGS_CONTEXT_HAS_IS_REMOTE_MASK` and `SPAN_FLAGS_CONTEXT_IS_REMOTE_MASK` are set, so `isRemote` reports `TRUE` for an extracted context and `FALSE` for anything a local [[FB_Tracer]] produced. This is the case that bit pair exists for.

## Sampling is decided locally

The sampled bit on an inbound link is advisory. The PLC makes its own sampling decision for its own trace.

This is a consequence of the two-trace model rather than an extra rule, and it is the point of it operationally: a minutes-long startup sequence should not be discarded because the gateway that triggered it samples writes at a low rate. It is also the first concrete requirement for the sampling design.

## Domain placement

Propagation does not need a new domain. Extraction reads bytes and produces a value object, which is the same shape as `ValueFactory` and `LinkFactory`, so it belongs with span creation alongside [[FB_Tracer]]. Serialization of *outbound* spans stays with the tracing serializer; `inject` writes a context carrier, not a wire encoding of a span.

## Open questions

- **Link direction is one-way.** The caller cannot link forward, because the PLC's trace ID does not exist when the command is sent. If correlation needs to be visible from the caller's side, the cheap path is log records carrying the inbound trace ID — already the stated direction, since [[FB_Span]] notes span events are deprecated in favour of logs with span context.
- **`tracestate` is pass-through only.** Nothing yet parses or edits the list. An implementation that adds a vendor entry for this controller needs a key/value representation, which is a Value Creation question.
- **Fan-out attribution.** When one command starts several processes, every resulting trace links to the same command span. Whether the operator also needs a shared correlation attribute to group those runs is undecided.
