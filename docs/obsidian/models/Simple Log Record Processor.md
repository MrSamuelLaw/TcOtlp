Normally a simple log record processor, or any log record processor for that matter, is synchronous in that the function call can run on a thread in the background and it will finish when it finishes. For a realtime environment there really isn't an option to run on a background thread so what I must do is treat it similar to a batched log record processor with length 1.

Any class that implements a log record processor MUST override the onEmit method.
The onEmit method MUST pass the log record to the exporter if the exporter isn't busy, otherwise the processor MUST drop the record and SHOULD emit a console log indicating the error to the user.

For a [[FB_LogRecordProcessor]] with a full processing queue, the incoming log record WILL be deleted.