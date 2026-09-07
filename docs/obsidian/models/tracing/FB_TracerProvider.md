---
type: model
domain: tracing
status: partial
implements:
  - FB_TracerProvider
source: TcOtlp/test/OTEL/TRACING/PROVIDER/FUNCTION_BLOCKS/FB_TracerProvider.TcPOU
gap: Only FB_Init and resource exist; the id buffer and processing pipeline are not implemented.
---

The `FB_TracerProvider` is instantiated with a reference to a `FB_Resource` and it passed as a reference to [[FB_Tracer]] instances during their instantiation in order for them to inject both scope and resources into `FB_Spans` during processing/exporter. When a [[FB_Span]] is ended via a `FB_Tracer` the `FB_Tracer` uses its reference to the `FB_TracerProvider` to begin the processing pipeline.

Additionally the `FB_TracerProvider` is responsible for building up a buffer of GUIDs using the [[FB_IdGenerator]] to use for traces/spans that the `FB_Tracer` instances can request when instantiating `FB_Span` objects. In the event that the buffer is empty the `FB_Tracer` instances should set their failure status to indicate that no GUIDs were available.