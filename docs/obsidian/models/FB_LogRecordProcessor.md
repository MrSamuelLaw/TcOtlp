A log record processor takes a log, enriches it, and then clones it, saves it, and pushes it to an exporter if the exporter isn't busy. Processors MUST implement an onEmit method that can be extended to customize the behavior of the processor.

## FB_LogRecordProcessor_Simple

The FB_LogRecordProcessor_Simple class does not have an internal buffer to export logs. Instead it will silently drop the log records if the exporter is busy.
### Methods:

`onEmit(logRecord:FB_LogRecord) -> void`
This method is used by FB_Logger to pass the log record to the processor, if and only if the processor contains an exporter, it MUST clone the record and attempt to export it. If the exporter is busy it MUST drop the log record and SHOULD log to the console that the record was dropped.

enrich(logRecord: FB_LogRecord) -> void
This method is no-op on FB_LogRecordProcessor_Simple, but can be overridden by classes that extend FB_LogRecordProcessor_Simple to augment the log record prior to cloning it and passing it to the exporter if and only if the exporter exists.

call() -> void
alias for () used to call the processor body cyclically while maintaining compatibility with twincat interfaces.

## FB_LogRecordProcessor_Batch

The FB_LogRecordProcessor_Simple class has an internal buffer that is utilized to push records to the exporter in batches if and only if it contains an exporter. If the exporter is null the log records are silently dropped to reduce memory consumption.
### Methods:

`onEmit(logRecord:FB_LogRecord) -> void`
This method is used by FB_Logger to pass the log record to the processor, if and only if the processor contains an exporter, it MUST clone the record and attempt to export it. If the instance does not have a an exporter associated with it it MUST NOT clone and save the record to it's internal buffer. 
If the exporter is busy AND the internal buffer it not full it MUST wait and attempt to push log records to the exporter the next time the processor is called cyclically.

enrich(logRecord: FB_LogRecord) -> void
This method is no-op on FB_LogRecordProcessor_Simple, but can be overridden by classes that extend FB_LogRecordProcessor_Simple to augment the log record prior to cloning it and passing it to the exporter if and only if the exporter exists.

call() -> void
alias for () used to call the processor body cyclically while maintaining compatibility with twincat interfaces.



