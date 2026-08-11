An exporter MUST have a way to indicate its current state/status to a processor. Processors are responsible for coordinating their push operations to the exporter. There MUST be a one to one relationship between exporter instances and processor instances. If an attempt is made to violate the 1 to 1 relationship a error SHOULD be logged to the console.

## Methods:

`export(records: FB_LogRecordQueue, count: int = 0`) -> void
transfers log records to the exporter for export. If the exporter is busy no logs will be transferred.

`register(processor: I_LogRecordProcessor) -> bool`
used to enforce the 1 to 1 constraint between the exporters and the processors.

`FB_LogRecordExporter()` cyclical call of the function block used to facilitate the exporter.
