`FB_LogRecordExporter_Base` defines the ownership and coordination contract shared by log record exporters. Processors query `isBusy()` before offering a batch and call the exporter cyclically to advance destination-specific work.

An exporter accepts at most one processor identity. The first call to `register` succeeds, and another call from the same processor also succeeds. A different processor is rejected and an ADS error is logged. Processor initialization retains its exporter reference only when this registration succeeds.

## Methods

- **`export(logRecords: FB_LogRecordQueue, count: UDINT, failureReason: E_LogRecordExporterFailureReason) -> BOOL`** — If the exporter is busy, returns `FALSE` with `ACTIVE_EXPORT_IN_PROGRESS` and leaves the source queue unchanged. Otherwise, transfers ownership of up to `count` oldest records from the source queue into the exporter without cloning them. Accepted records are removed from the source queue. A `count` of zero transfers no records. Queue-transfer failure returns `FALSE`; successful transfer returns `TRUE`, including an empty transfer.

- **`register(processor: I_LogRecordProcessor) -> BOOL`** — Registers the processor's `pSelf` identity and enforces the one-processor-per-exporter constraint.

- **`isBusy() -> BOOL`** — Reports whether the exporter can currently accept another batch.

- **`call(failureReason: E_LogRecordExporterFailureReason) -> BOOL`** — Advances the concrete exporter's cyclic work and reports destination-specific failure.

- **`free()`** — Releases all records currently owned by the exporter and clears its active-export flag. `FB_Exit` invokes this during normal destruction.

Concrete exporter function-block bodies invoke `call()`. The console exporter is never busy and writes accepted string bodies synchronously before releasing the batch. The file exporter remains busy while its serialization and file-I/O state machine owns a batch, and exposes that state through `currentState`.
