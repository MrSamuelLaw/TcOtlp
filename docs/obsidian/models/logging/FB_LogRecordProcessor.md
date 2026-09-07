---
type: model
domain: processing
status: implemented
implements:
  - FB_LogRecordProcessor_Base
  - FB_LogRecordProcessor_Mixin
  - FB_LogRecordProcessor_Simple
  - FB_LogRecordProcessor_Batch
source: TcOtlp/test/OTEL/LOGGING/PROCESSORS/FUNCTION_BLOCKS/
---

Processors receive emitted log records from [[FB_LoggerProvider]] and prepare them for export.

During `tick()`, the provider pops each queued record and passes it by reference to every registered processor's `onEmit`, in the order the processors were staged for that scan. The provider deletes the original record once the last processor returns, so a processor that retains a record must clone it.

`FB_LogRecordProcessor_Base` is the abstract base every processor extends. It declares `onEmit`, `enrich`, `free`, and `tick`. The `pSelf` identity used by the provider to deduplicate registrations comes from `FB_LogRecordProcessor_Mixin`.

Both concrete processors call `enrich` on the original record before cloning. Their default implementation is a no-op and can be overridden. Because enrichment mutates the original, changes made by one processor are visible to processors staged after it.

Each processor binds to its exporter through `FB_Init`, which takes a `REFERENCE TO FB_LogRecordExporter_Base`. The reference is stored only when `__ISVALIDREF` passes, so passing `0` yields a processor with no exporter. Nothing prevents two processors from sharing one exporter, however, sharing one exporter is not safe for multi-tasked architectures and should be avoided.

## `FB_LogRecordProcessor_Simple`

The simple processor has no retained backlog. It uses a one-record queue only as a transient ownership-transfer buffer.

### Methods

- **`onEmit(logRecord: REFERENCE TO FB_LogRecord)`** — Calls `enrich` unconditionally. If the bound exporter is valid and not busy, clones the record, places the clone in its transient queue, and offers one record to the exporter. It then releases anything the exporter did not accept. A missing or busy exporter, clone failure, queue failure, or export failure produces no exported clone and logs no warning.

- **`enrich(logRecord: FB_LogRecord)`** — No-op extension point invoked before the exporter validity and busy checks.

- **`tick()`** — Calls the bound exporter's `tick()` method. The simple processor's function-block body is empty, so invoking `processor()` is not an alias for this method.

- **`free()`** — Releases any record in the transient queue. Normal destruction also invokes this method.

## `FB_LogRecordProcessor_Batch`

The batch processor retains cloned records in FIFO arrival order and exports the oldest records in bounded batches. Its underlying queue is bounded to `maxQueueSize`.

### Configuration

- **`maxQueueSize: UDINT := 2048`** — Maximum retained records. Zero is unbounded. When a nonzero limit is exceeded, the queue default FIFO behavior enforces dropping the oldest record.

- **`scheduledDelayMillis: UDINT := 1000`** — Maximum time a partial batch waits before becoming eligible for export.

- **`maxExportBatchSize: UDINT := 512`** — Maximum records transferred per export. Zero disables export attempts.

- **`lastOperationSucceeded: BOOL` and `failureResult: E_LogRecordProcessorFailureReason`** — Report the most recent clone, queue, or export operation result.

### Methods

- **`onEmit(logRecord: REFERENCE TO FB_LogRecord)`** — Calls `enrich`, clones the record, and queues the clone; when no exporter is bound only `enrich` is called.. Clone and queue failures are reported through the status outputs. If the configured queue limit is exceeded, the oldest queued record is deleted.

- **`enrich(logRecord: FB_LogRecord)`** — No-op extension point invoked before every clone.

- **`tick()`** — Advances the schedule-delay timer and the bound exporter, then calls `exportIfNeeded`. Without a bound exporter, records remain queued until dropped by `maxQueueSize` or released by `free()`.

- **`exportIfNeeded()`** — If the exporter is available and not busy, exports up to `maxExportBatchSize` oldest records when a full batch is available or the delay has elapsed. A busy exporter leaves the queue untouched for a later cycle.

- **`free()`** — Releases every queued record and resets the schedule-delay timer. Normal destruction also invokes this method.
