---
type: model
domain: exporting
status: implemented
implements:
  - FB_LogRecordExporter_Base
  - FB_LogRecordExporter_Console
  - FB_LogRecordExporter_File
  - FB_LogRecordExporter_HTTP
source: TcOtlp/test/OTEL/LOGGING/EXPORTING/FUNCTION_BLOCKS/
---

`FB_LogRecordExporter_Base` is the `ABSTRACT` base defining the ownership and coordination contract shared by log record exporters. Processors query `isBusy()` before offering a batch and call the exporter cyclically to advance destination-specific work.

An exporter is bound to a processor by construction, not by registration: [[FB_LogRecordProcessor|the processor]] takes a `REFERENCE TO FB_LogRecordExporter_Base` in its `FB_Init`. The exporter itself holds no processor identity and enforces no one-processor-per-exporter constraint, so two processors may share one exporter — the exporter's `isBusy()` flag is the only arbitration between them. This is not safe for multi-tasked architectures.

## Methods

- **`export(logRecords: FB_LogRecordQueue, count: UDINT, failureReason: E_LogRecordExporterFailureReason) -> BOOL`** — If the exporter is busy, returns `FALSE` with `ACTIVE_EXPORT_IN_PROGRESS` and leaves the source queue unchanged. Otherwise, transfers ownership of up to `count` oldest records from the source queue into the exporter without cloning them. Accepted records are removed from the source queue. A `count` of zero transfers no records. Queue-transfer failure returns `FALSE`; successful transfer returns `TRUE`, including an empty transfer.

- **`isBusy() -> BOOL`** — Reports whether the exporter can currently accept another batch.

- **`tick(failureReason: E_LogRecordExporterFailureReason) -> BOOL`** — Advances the concrete exporter's cyclic work and reports destination-specific failure.

- **`free()`** — Releases all records currently owned by the exporter and clears its active-export flag. `FB_Exit` invokes this during normal destruction.

## Concrete exporters

Concrete exporter function-block bodies invoke `tick()`.

| Exporter                       | Busy semantics                                                                      | State output                                            |
| ------------------------------ | ----------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `FB_LogRecordExporter_Console` | Never busy; writes accepted string bodies synchronously before releasing the batch. | —                                                       |
| `FB_LogRecordExporter_File`    | Busy while its serialization and file-I/O state machine owns a batch.               | `currentState: E_FileExporterState`                     |
| `FB_LogRecordExporter_HTTP`    | Busy for the duration of the OTLP/HTTP request/response cycle.                      | `currentState: E_HttpExporterState`, `statusCode: UINT` |

The file and HTTP exporters take their destination through `FB_Init`; the HTTP exporter parses the supplied URL once and derives host, port, path, and TLS use from it.
