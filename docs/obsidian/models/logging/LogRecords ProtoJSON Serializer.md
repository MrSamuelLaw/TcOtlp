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

`serializeLogsData` attempts to transfer every supplied record into an internal queue without cloning. After a successful transfer, the caller's queue is empty and the serializer deletes all transferred records on both serialization success and failure. Serialization is therefore a consuming operation once ownership transfer succeeds.

## Grouping and order

Records are grouped globally rather than only by adjacent runs:

1. `ResourceLogs` groups use `resource.id` as their key.
2. Within each resource group, `ScopeLogs` groups use `scope.name` as their key.
3. Non-adjacent records with the same resource ID and scope name are coalesced into one group.
4. Resource groups, scope groups, and records within each group preserve first-seen arrival order.

Resource fields other than ID and scope fields other than name are not part of the grouping keys. If records have matching keys but different metadata, they share one group and the first record's resource and scope metadata is serialized for that group.

The operation fails with `LOOP_LIMIT_EXCEEDED` when the input contains more than `GVL.MAX_LOOP_COUNT` records. Other queue or JSON failures are returned through `E_ProtoJsonSerializerFailureReason` after the serializer releases its owned records.
