---
type: model
domain: tracing
status: implemented
implements:
  - FB_Sampler
  - FB_Sampler_AlwaysOn
  - FB_Sampler_ErrorsOnly
source: TcOtlp/test/OTEL/TRACING/SAMPLING/FUNCTION_BLOCKS/
gap: Only the sampled bit is decided. There is no RECORD_ONLY decision, and a sampler cannot add attributes or change the trace state as the OpenTelemetry ShouldSample can.
---

A sampler decides which spans are exported. It does this through one bit: bit 0 of the span's trace flags, the W3C sampled flag. [[FB_Span]]`.isSampled()` reads it and `setSampled(sampled)` writes it.

## Two decisions

`FB_Sampler` has two methods, and a span is processed only if its sampled bit is still set after both:

- **`onStart(span)`** is the head decision. [[FB_Tracer]]`.build` calls it once the span has its identifiers, parent, links and attributes, just before handing the span to the caller. The bit it leaves is carried into the span's context by `getContext`, so children and injected carriers inherit it.
- **`onEnd(span)`** is a later decision, made once the span's status is known. [[FB_TracerProvider]]`.onEnd` calls it when the span ends, before the span is queued for the processors.

The provider asks `onEnd` only about spans that are still sampled, and releases the rest without asking. So `onEnd` can drop a span but never keep one that `onStart` dropped. This follows OpenTelemetry: the SDK specification says exporters should not receive spans without the sampled flag, and the sampling concepts page places error-based sampling after head sampling, working only on what head sampling kept.

A span that is sampled out still runs normally and is owned by the caller until it ends; it just never reaches a processor. Dropping it counts as success, so `endSpan` does not report `TRANSFER_TO_PROVIDER_FAILURE`.

Both methods borrow the span for the call and must not keep it.

## Samplers

| Sampler | `onStart` | `onEnd` |
| --- | --- | --- |
| `FB_Sampler` | Samples a root span; a child keeps the bit it copied from its parent. | Keeps every span. |
| `FB_Sampler_AlwaysOn` | Samples every span, even the child of an unsampled parent. | Inherited: keeps every span. |
| `FB_Sampler_ErrorsOnly` | Inherited: the default start decision. | Drops a span unless its status is `STATUS_CODE_ERROR`. |

`FB_Sampler` used as is gives the OpenTelemetry default, `ParentBased(root=AlwaysOn)`. A remote parent's sampled bit is followed, so a child of an unsampled remote parent is not exported. A link carries no sampling decision: a root span that links to an unsampled context is still sampled. This keeps the rule in [[Trace Context Propagation]] that an inbound trigger, which is linked rather than parented, does not decide the sampling of the PLC's trace.

`FB_Sampler_ErrorsOnly` keeps the default start decision, so a failed span whose parent was not sampled is still dropped. Unlike the OpenTelemetry `ShouldSample`, which runs before a span exists, its decision is made at the end. OpenTelemetry leaves error sampling to tail sampling in the Collector; here it is done per span in the PLC.

## Custom samplers

Extend `FB_Sampler` and override either method. Call `SUPER^.onStart(span := span)` to keep the default start decision and add to it.

```iec
FUNCTION_BLOCK FB_Sampler_SlowOrFailed EXTENDS FB_Sampler
VAR_INPUT
	thresholdNs: ULINT;
END_VAR

METHOD onEnd
VAR_INPUT
	span: REFERENCE TO FB_Span;
END_VAR
IF (span.status = 0 OR_ELSE span.status^.code <> E_StatusCode.STATUS_CODE_ERROR)
	AND span.endTimestamp - span.startTimestamp < thresholdNs THEN
	span.setSampled(FALSE);
END_IF
```

## The provider's sampler

The sampler is a required `FB_Init` parameter of [[FB_TracerProvider]] and is borrowed, like the resource and id generator. `TcOtlp_GVL.defaultSampler` is a shared `FB_Sampler` for the common case; a sampler without state can be shared by every provider.

```iec
provider: FB_TracerProvider(resource := resource, idGenerator := idGenerator, sampler := TcOtlp_GVL.defaultSampler);
errorsOnly: FB_Sampler_ErrorsOnly;
failuresProvider: FB_TracerProvider(resource := resource, idGenerator := idGenerator, sampler := errorsOnly);
```

The provider's `sampler` property returns the sampler it was given, or `TcOtlp_GVL.defaultSampler` if that reference is invalid.

## Tests

`FB_TestSamplers` covers the default parent-based decision, always-on sampling of a child of an unsampled parent, the errors-only sampler, an `onEnd` that tries to sample a span dropped on start, and a root span linked to an unsampled context.
