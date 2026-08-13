A logger passes its active log record by reference to each `I_LogRecordProcessor` in array order, then deletes the original record after all processors return. A processor that retains a record must therefore clone it. `I_LogRecordProcessor` requires `onEmit`, `enrich`, `call`, `free`, and the `pSelf` identity used for exporter registration.

Both concrete processors call `enrich` on the original record before cloning. Their default implementation is a no-op and can be overridden. Because enrichment mutates the original, changes made by one processor are visible to processors later in the logger's processor array.

## `FB_LogRecordProcessor_Simple`

The simple processor has no retained backlog. It uses a one-record queue only as a transient ownership-transfer buffer.

### Methods

- **`onEmit(logRecord: REFERENCE TO FB_LogRecord)`** — Calls `enrich` unconditionally. If a registered exporter exists and is not busy, clones the record, places the clone in its transient queue, and offers one record to the exporter. It then releases anything the exporter did not accept. A missing or busy exporter, clone failure, queue failure, or export failure produces no exported clone and logs no warning.

- **`enrich(logRecord: FB_LogRecord)`** — No-op extension point invoked before the exporter validity and busy checks.

- **`call()`** — Calls the registered exporter's `call()` method. The simple processor's function-block body is empty, so invoking `processor()` is not an alias for this method.

- **`free()`** — Releases any record in the transient queue. Normal destruction also invokes this method.

## `FB_LogRecordProcessor_Batch`

The batch processor retains cloned records in FIFO arrival order and exports the oldest records in bounded batches. Its underlying queue is unbounded; `maxQueueSize` is enforced by the processor's explicit drop policy.

### Configuration

- **`maxQueueSize: UDINT := 2048`** — Maximum retained records. Zero is unbounded. When a nonzero limit is exceeded, the oldest record is deleted to retain the newest record.

- **`scheduledDelayMillis: UDINT := 1000`** — Maximum time a partial batch waits before becoming eligible for export.

- **`maxExportBatchSize: UDINT := 512`** — Maximum records transferred per export. Zero disables export attempts.

- **`lastOperationSucceeded: BOOL` and `failureResult: E_LogRecordProcessorFailureReason`** — Report the most recent clone, queue, or export operation result.

### Methods

- **`onEmit(logRecord: REFERENCE TO FB_LogRecord)`** — Calls `enrich`, clones the record, and queues the clone even when no exporter is registered. Clone and queue failures are reported through the status outputs. If the configured queue limit is exceeded, the oldest queued record is deleted.

- **`enrich(logRecord: FB_LogRecord)`** — No-op extension point invoked before every clone.

- **`call()`** — Advances the schedule-delay timer and registered exporter. If the exporter is available and not busy, exports up to `maxExportBatchSize` oldest records when a full batch is available or the delay has elapsed. A busy exporter leaves the queue untouched for a later cycle. Without a registered exporter, records remain queued until dropped by `maxQueueSize` or released by `free()`.

The batch processor's function-block body invokes `call()`, so `processor()` and `processor.call()` advance the same cyclic behavior.

- **`free()`** — Releases every queued record and resets the schedule-delay timer. Normal destruction also invokes this method.
