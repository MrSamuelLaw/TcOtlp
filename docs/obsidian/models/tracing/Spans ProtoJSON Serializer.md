---
type: model
domain: serialization
status: implemented
implements:
  - FB_SpanProtoJsonSerializer
source: TcOtlp/test/OTEL/TRACING/SERIALIZATION/FUNCTION_BLOCKS/FB_SpanProtoJsonSerializer.TcPOU
---

`FB_SpanProtoJsonSerializer.serializeTracesData` converts a queue of ended spans into one OTLP ProtoJSON `TracesData` object: `resourceSpans` → `scopeSpans` → `spans`. It extends `FB_BaseProtoJsonSerializer`, and the document is left in `parser` and `jsonValue`, as with [[LogRecords ProtoJSON Serializer]].

## Ownership

`serializeTracesData` takes ownership of every span in the `FB_SpanQueue` it is given and drains the queue, like `serializeLogsData`. Each span is released as soon as it is written. On failure, the span being written and every span still queued are released too. So the queue is empty when the method returns, whatever the result. A caller that needs the spans afterwards must clone them first.

`serializeSpan` only reads the span it is given.

## Drain requirement

A queue serializer must leave the queue it is given empty when it returns, whether it succeeds or fails. It pops each span and releases it once written, and on failure it releases the span it holds and every span still queued. Only the JSON document in `parser` and `jsonValue` is left behind.

Two things depend on this:

- **Ownership.** The exporter hands its own batch queue to the serializer. Draining is how that batch is released exactly once, and a failed serialization cannot leak spans or leave a half-written batch behind to be sent again.
- **The exporter's start trigger.** `FB_SpanExporter_File` starts a batch on the rising edge of "export active and the batch queue is not empty". The serializer empties the queue in the `serializing` state, so the trigger drops and re-arms before the batch finishes. A batch accepted in the same scan that the previous one reaches `done` or `error` then produces a new edge and starts. If the serializer left the queue full, the trigger would stay high across batches, the next batch would never start, and `isBusy()` would stay TRUE forever.

A caller that still needs the spans after serialization must clone them first. The serializer never changes the content of what it writes.

## Grouping and order

The grouping keys are the same as for log records:

1. `ResourceSpans` groups use `resource.id` as their key.
2. Within each resource group, `ScopeSpans` groups use `scope.name` as their key.
3. Spans with the same keys are merged into one group even when they are not adjacent in the queue.
4. Resource groups, scope groups, and spans within a scope all keep first-seen queue order.

When spans share keys but differ in other resource or scope metadata, the first span's metadata is written for the group.

Grouping pops and rotates the queue, as the log serializer does:

- A resource group starts by popping the oldest queued span.
- A scope pass writes its leading span, then walks the queue once. It pops, writes and releases each span with the same resource and scope, and uses `rotate` to move every other span to the back, which keeps their order.
- The next scope of the resource starts from the first remaining span with that resource, which is popped the same way.

Each group costs one walk of the queue, so the work is bounded by count².

## Span fields

| Field | Written |
| --- | --- |
| `traceId`, `spanId` | As hex, when set |
| `parentSpanId` | As hex. Only for a child span; a root span omits it |
| `traceState` | When set |
| `flags` | When not zero |
| `name` | When set |
| `kind` | Always, as the `E_SpanKind` number |
| `startTimeUnixNano`, `endTimeUnixNano` | Always, as decimal strings |
| `attributes`, `droppedAttributesCount` | When present or non-zero |
| `links`, `droppedLinksCount` | When present or non-zero. Each Link has hex `traceId` and `spanId`, and `traceState`, `attributes`, `droppedAttributesCount` and `flags` when set |
| `status` | When the span has one: `message` when set, and `code` as a number unless it is `STATUS_CODE_UNSET` |

## Failures

`E_ProtoJsonSerializerFailureReason`:

| Failure reason | Cause |
| --- | --- |
| `LOOP_LIMIT_EXCEEDED` | The queue, or a span's links, hold more than `TcOtlp_GVL.MAX_LOOP_COUNT` entries. |
| `SPAN_COLLECTION_INCONSISTENT` | The queue's `count` and its linked spans disagree. |
| `QUEUE_POP_FAILURE`, `QUEUE_ROTATE_FAILURE` | The queue could not pop or rotate a span while grouping. |
| `SPAN_POINTER_NULL` | `serializeSpan` was given a null span. |
| `JSON_VALUE_INVALID`, `JSON_OPERATION_FAILURE` | The JSON DOM could not be written. |

An empty queue succeeds, producing an empty `resourceSpans` array.
