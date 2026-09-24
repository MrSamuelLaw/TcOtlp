---
type: model
domain: serialization
status: implemented
implements:
  - FB_LogRecordProtoJsonSerializer
source: TcOtlp/test/OTEL/LOGGING/SERIALIZATION/FUNCTION_BLOCKS/FB_LogRecordProtoJsonSerializer.TcPOU
---

`FB_LogRecordProtoJsonSerializer.serializeLogsData` converts a queue of log records into one OTLP ProtoJSON `LogsData` object.

## Ownership

`serializeLogsData` takes ownership of every record in the `FB_LogRecordQueue` it is given and drains it. It pops each record, writes it, and releases it. On failure, including a queue over `MAX_LOOP_COUNT`, it releases the record it holds and frees the rest of the queue. The queue is empty when the method returns, whatever the result.

## Drain requirement

A queue serializer must leave the queue it is given empty when it returns, whether it succeeds or fails. It pops each record and releases it once written, and on failure it releases the record it holds and every record still queued. Only the JSON document in `parser` and `jsonValue` is left behind.

Two things depend on this:

- **Ownership.** The exporter hands its own batch queue to the serializer. Draining is how that batch is released exactly once, and a failed serialization cannot leak records or leave a half-written batch behind to be sent again.
- **The exporter's start trigger.** `FB_LogRecordExporter_File` and `FB_LogRecordExporter_HTTP` start a batch on the rising edge of "export active and the batch queue is not empty". The serializer empties the queue in the `serializing` state, so the trigger drops and re-arms before the batch finishes. A batch accepted in the same scan that the previous one reaches `done` or `error` then produces a new edge and starts. If the serializer left the queue full, the trigger would stay high across batches, the next batch would never start, and `isBusy()` would stay TRUE forever.

A caller that still needs the records after serialization must clone them first. The serializer never changes the content of what it writes.

## Grouping and order

Records are grouped globally rather than only by adjacent runs:

1. `ResourceLogs` groups use `resource.id` as their key.
2. Within each resource group, `ScopeLogs` groups use `scope.name` as their key.
3. Non-adjacent records with the same resource ID and scope name are coalesced into one group.
4. Resource groups, scope groups, and records within each group preserve first-seen arrival order.

Resource fields other than ID and scope fields other than name are not part of the grouping keys. If records have matching keys but different metadata, they share one group and the first record's resource and scope metadata is serialized for that group.

The operation fails with `LOOP_LIMIT_EXCEEDED` when the input contains more than `GVL.MAX_LOOP_COUNT` records. Other queue or JSON failures are returned through `E_ProtoJsonSerializerFailureReason` after the serializer releases its owned records.
