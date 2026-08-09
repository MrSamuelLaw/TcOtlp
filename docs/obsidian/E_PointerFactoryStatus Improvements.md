# Possible improvements to E_PointerFactoryStatus

## Summary

`E_PointerFactoryStatus` has outgrown the factory operation it originally described. It is currently used for:

1. Value creation and cloning
2. Attribute collection mutation
3. Log record copying
4. Logger build lifecycle and emission
5. Batch processor queueing

There is no single DDD-aligned name that accurately represents all of these responsibilities. The preferred improvement is to split it into operation-specific result enums. If a transitional rename is needed before that split, `E_OtlpOperationResult` is more accurate than `E_PointerFactoryStatus`, but it should not be the final design.

`Result` is preferable to `Status` for method return values because these values describe the terminal outcome of an operation rather than the persistent state of an object.

## Problems with the existing members

| Existing member | Current meanings | Possible replacements |
| --- | --- | --- |
| `SUCCESS` | The operation succeeded | Keep `SUCCESS` |
| `UNSPECIFIED_ERROR` | Unsupported `AnyValue` type; log record release failure; post-`free` logger sentinel | `UNSUPPORTED_VALUE_TYPE`, `LOG_RECORD_RELEASE_FAILURE`; represent logger lifecycle separately |
| `POINTER_ALREADY_ALLOCATED` | A destination output is nonzero; a log record is already being built | `DESTINATION_ALREADY_ASSIGNED`, `LOG_RECORD_ALREADY_STARTED` |
| `UNEXPECTED_NULL_POINTER` | A null attribute was passed to `append`; a logger method was called without an active record | `ATTRIBUTE_VALUE_REQUIRED`, `LOG_RECORD_NOT_STARTED` |
| `OUT_OF_MEMORY` | An allocation failed; the attribute limit was reached; the batch queue was full; a linked-list insertion failed | `MEMORY_ALLOCATION_FAILURE`, `ATTRIBUTE_LIMIT_REACHED`, `LOG_RECORD_QUEUE_FULL`, and specific insertion failures |
| `INVALID_PARAMETERS` | Null source; uninitialized source; missing payload; invalid payload size; short Span ID or Trace ID input | Parameter-specific members described below |
| `POINTER_OWNERSHIP_TRANSFER_FAILURE` | No current producer | Remove unless an observable ownership-transfer failure is introduced |

### `POINTER_ALREADY_ALLOCATED` is technically inaccurate

The factory methods only test whether `pDest <> 0`. That proves the destination is already assigned, but it does not prove the pointer was dynamically allocated or identify its owner. `DESTINATION_ALREADY_ASSIGNED` describes the observed precondition failure more accurately.

The same member has a different meaning in `FB_Logger.startLogRecord`, where it means that a log record build is already active. That outcome should use `LOG_RECORD_ALREADY_STARTED`.

### `OUT_OF_MEMORY` combines allocation and capacity failures

An unsuccessful `__NEW` operation proves that memory allocation failed, but not necessarily that the entire runtime is out of memory. `MEMORY_ALLOCATION_FAILURE` is therefore a more precise description.

Capacity failures are separate domain outcomes:

- `FB_LinkedList_KeyValue.append` returns `OUT_OF_MEMORY` when `GVL.MAX_ATTRIBUTES` has been reached, before attempting an allocation.
- `FB_LogRecordProcessor_Batch.onEmit` returns `OUT_OF_MEMORY` when `maxQueueSize` has been reached.
- The batch processor also maps every failed `FB_LinkedList_LogRecord.insert` call to `OUT_OF_MEMORY`, even though `insert` can fail because its value is null, its index is invalid, its capacity was reached, or node allocation failed.

These should be represented as `ATTRIBUTE_LIMIT_REACHED`, `LOG_RECORD_QUEUE_FULL`, and an exact list insertion result respectively.

### `UNSPECIFIED_ERROR` is being used as both an error and a state sentinel

`ValueFactory.cloneAnyValue` uses `UNSPECIFIED_ERROR` for an unsupported `E_ValueType`. `FB_Logger.emit` uses it when deleting the active log record does not clear the pointer. `FB_Logger.free` also assigns it as a lifecycle sentinel.

The first two cases have identifiable causes and should use `UNSUPPORTED_VALUE_TYPE` and `LOG_RECORD_RELEASE_FAILURE`. Logger lifecycle should be modeled independently rather than encoded as an unspecified failure.

## Suggested result enums

The following enums are possible boundaries rather than a requirement that every implementation detail receive a distinct result. Members should distinguish outcomes that are meaningful or actionable to the caller.

### `E_ValueFactoryResult`

Use for the `ValueFactory.create*` and `ValueFactory.clone*` methods.

```iecst
SUCCESS
DESTINATION_ALREADY_ASSIGNED
SOURCE_POINTER_NULL
SOURCE_NOT_INITIALIZED
SOURCE_PAYLOAD_POINTER_NULL
SOURCE_PAYLOAD_SIZE_INVALID
KEY_POINTER_NULL
VALUE_POINTER_NULL
VALUE_NOT_INITIALIZED
STRING_POINTER_NULL
SPAN_ID_BYTES_POINTER_NULL
SPAN_ID_BYTE_COUNT_TOO_SMALL
TRACE_ID_BYTES_POINTER_NULL
TRACE_ID_BYTE_COUNT_TOO_SMALL
UNSUPPORTED_VALUE_TYPE
MEMORY_ALLOCATION_FAILURE
```

These members separate conditions that are currently combined under `INVALID_PARAMETERS`, including:

- `pSrc = 0`
- `NOT pSrc^.initialized`
- `pSrc^.value.pValue = 0`
- `value.diSize <= 0`
- `pKey = 0`
- `pVal = 0`
- `pBytes = 0`
- Too few bytes for a Span ID or Trace ID

### `E_AttributeCollectionResult`

Use for `addNumberAttribute`, `addStringAttribute`, `append`, and attribute copying.

```iecst
SUCCESS
ATTRIBUTE_VALUE_REQUIRED
ATTRIBUTE_VALUE_NOT_INITIALIZED
ATTRIBUTE_VALUE_TYPE_UNSUPPORTED
ATTRIBUTE_LIMIT_REACHED
ATTRIBUTE_VALUE_ALLOCATION_FAILURE
ATTRIBUTE_ALLOCATION_FAILURE
ATTRIBUTE_NODE_ALLOCATION_FAILURE
```

These names describe the attribute operation rather than exposing its internal linked-list and pointer implementation.

### Separate logger state from log record build results

`FB_Logger.sts` currently acts as both the sticky result of a fluent build chain and an implicit lifecycle guard. Those are different concepts.

A possible state enum is:

#### `E_LoggerState`

```iecst
IDLE
BUILDING_LOG_RECORD
FAULTED
```

A separate operation result could be:

#### `E_LogRecordBuildResult`

```iecst
SUCCESS
LOG_RECORD_ALREADY_STARTED
LOG_RECORD_NOT_STARTED
BODY_POINTER_NULL
BODY_NOT_INITIALIZED
SPAN_ID_BYTES_POINTER_NULL
SPAN_ID_BYTE_COUNT_TOO_SMALL
TRACE_ID_BYTES_POINTER_NULL
TRACE_ID_BYTE_COUNT_TOO_SMALL
ATTRIBUTE_LIMIT_REACHED
UNSUPPORTED_BODY_VALUE_TYPE
MEMORY_ALLOCATION_FAILURE
LOG_RECORD_RELEASE_FAILURE
```

Separating state from result removes the need to use `UNSPECIFIED_ERROR` merely to prevent fluent methods from continuing.

### `E_LogRecordEnqueueResult`

Use for `FB_LogRecordProcessor_Batch.sts`.

```iecst
SUCCESS
QUEUE_CAPACITY_REACHED
LOG_RECORD_CLONE_FAILURE
GROUP_ALLOCATION_FAILURE
QUEUE_NODE_ALLOCATION_FAILURE
QUEUE_INSERT_INDEX_INVALID
```

If callers need the root cause of `LOG_RECORD_CLONE_FAILURE`, the processor should retain the underlying clone result separately instead of expanding this enum with every possible nested factory failure.

## Preserve failure information at lower-level boundaries

Changing only `E_PointerFactoryStatus` cannot make every failure exact. `FB_LinkedList_LogRecord.insert` currently returns `BOOL`, so its caller cannot distinguish between:

- A null value
- An index greater than the current count
- A full list
- A node allocation failure

It could instead return an `E_LogRecordListInsertResult` with:

```iecst
SUCCESS
VALUE_REQUIRED
INDEX_OUT_OF_RANGE
CAPACITY_REACHED
NODE_ALLOCATION_FAILURE
```

The batch processor could then translate those low-level results into its own domain vocabulary without guessing.

## Naming recommendation

- Use `E_ValueFactoryResult` for factory methods.
- Use operation-specific enums such as `E_AttributeCollectionResult`, `E_LogRecordBuildResult`, and `E_LogRecordEnqueueResult` at other boundaries.
- Use a separate `E_LoggerState` for logger lifecycle.
- Use `E_OtlpOperationResult` only as a temporary umbrella name if the split cannot be completed in one change.
- Remove `POINTER_OWNERSHIP_TRANSFER_FAILURE` unless a real producer and recovery contract are identified.

The preferred final design is therefore not a better global name for `E_PointerFactoryStatus`, but a set of smaller result types expressed in the vocabulary of the operation that can fail.
