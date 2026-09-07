---
type: model
domain: tracing
status: partial
implements:
  - FB_Link
  - FB_Links
  - LinkFactory
source: TcOtlp/test/OTEL/TRACING/LINK/FUNCTION_BLOCKS/
gap: FB_Link and FB_Links exist; LinkFactory is an empty shell with no methods.
---

Links are immutable VALUE OBJECTS used to link **Asynchronous** spans together in a so that the context is not lost. For example, a trigger from a SCADA system causes two chiller pump skids to start up. The sending of the data from SCADA is a single root span that takes a few milliseconds, logging the write commands. The chiller pump skids then initiate one trace each that are independent of the trigger from SCADA, in other words, SCADA is not keeping the trace "on ice" while it waits for the skids. The two skids then start up, with each step of the startup sequence being a child span of the root span that is linked to the SCADA span, because the parent span duration is the sum of the child span durations.

# LinkFactory
The LinkFactory is used to create links from various inputs and ensure that the invariants are maintained.

## Methods

### fromSpan
This method is used to create an `FB_Link` instance from an [[FB_Span]] instance.

### cloneLink
This method is used to create a clone of an FB_Link instance from an FB_Span instance.

### createLink
This method is used to create an FB_Link instance from parameters and validates them during creation.