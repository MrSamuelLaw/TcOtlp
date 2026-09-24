---
type: model
domain: serialization
status: partial
implements:
  - FB_SpanProtoJsonSerializer
source: TcOtlp/test/OTEL/TRACING/SERIALIZATION/FUNCTION_BLOCKS/FB_SpanProtoJsonSerializer.TcPOU
gap: Span links are not written, because FB_Links has no implementation yet.
---

`FB_SpanProtoJsonSerializer.serializeTracesData` converts a queue of ended spans into one OTLP ProtoJSON `TracesData` object: `resourceSpans` → `scopeSpans` → `spans`. It extends `FB_BaseProtoJsonSerializer`, and the document is left in `parser` and `jsonValue`, as with [[LogRecords ProtoJSON Serializer]].

## Ownership

Serialization only reads. The spans stay in the caller's `FB_SpanQueue`, owned by the caller, whether serialization succeeds or fails. Nothing is popped, rotated, cloned or released, so the same queue can be serialized again, or released by its owner after a failed attempt.

This differs from `serializeLogsData`, which consumes its records.

## Grouping and order

The grouping keys are the same as for log records:

1. `ResourceSpans` groups use `resource.id` as their key.
2. Within each resource group, `ScopeSpans` groups use `scope.name` as their key.
3. Spans with the same keys are merged into one group even when they are not adjacent in the queue.
4. Resource groups, scope groups, and spans within a scope all keep first-seen queue order.

When spans share keys but differ in other resource or scope metadata, the first span's metadata is written for the group.

The log serializer groups by popping and rotating its queue. The span serializer cannot change the queue, so it uses the queue's borrow-only cursor (`reset` and `next`) together with a heap array holding one "written" flag per span:

- A resource group starts at the oldest span that has not been written.
- A scope group starts at the oldest unwritten span with that resource.
- Each scope pass walks the queue once. It writes every unwritten span that matches the group's resource and scope, and marks those spans as written.

Each group costs one walk of the queue, so the work is bounded by count². The flag array is released before the method returns.

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
| `status` | When the span has one: `message` when set, and `code` as a number unless it is `STATUS_CODE_UNSET` |
| `links` | Not written yet |

## Failures

`E_ProtoJsonSerializerFailureReason`:

| Failure reason | Cause |
| --- | --- |
| `LOOP_LIMIT_EXCEEDED` | The queue holds more than `TcOtlp_GVL.MAX_LOOP_COUNT` spans. |
| `MEMORY_ALLOCATION_FAILURE` | The written-flag array could not be allocated. |
| `SPAN_COLLECTION_INCONSISTENT` | The queue's `count` and its linked spans disagree. |
| `SPAN_POINTER_NULL` | `serializeSpan` was given a null span. |
| `JSON_VALUE_INVALID`, `JSON_OPERATION_FAILURE` | The JSON DOM could not be written. |

An empty queue succeeds, producing an empty `resourceSpans` array.
