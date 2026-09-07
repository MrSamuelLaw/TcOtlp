---
type: model
domain: tracing
status: design
implements:
  - FB_SpanContext
---

Instances of `FB_SpanContext` are immutable  VALUE OBJECTS that must be serialized and propagated along side of a distributed context and has the following members.

### TraceId: FB_TraceId
### SpanId: FB_SpanId

### TraceFlags: udint

### TraceState

### IsRemote
