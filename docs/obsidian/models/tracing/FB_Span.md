---
type: model
domain: tracing
status: partial
implements:
  - FB_Span
source: TcOtlp/test/OTEL/TRACING/SPAN/FUNCTION_BLOCKS/FB_Span.TcPOU
gap: flags, setStatusOk and setStatusError exist; getContext does not.
---

## Methods
### getContext
Used to create an instance of an [[FB_SpanContext]] instance that is an immutable VALUE OBJECT.

