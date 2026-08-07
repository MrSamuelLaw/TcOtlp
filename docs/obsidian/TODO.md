# Notes For Next Time
1. Create a FB_TestLogRecord function block to test the log record functionality.
2. Once the FB_TestLogRecord clone method is working, run a processor that retains a deep copy of the record so I can interrogate if it augments the log record properly.

## Modeling
- [x] Update the domain model
	- [x] Check if each member is an aggregate, and invariant, or a value object?
	- [x] I think the record itself is the aggregate. The Invariants are with respect to each member, and each member is itself a value object. Check with chat to verify.

## Infrastructure/Domain Logic
- [x] Implement the log record processing pipeline
	- [x] I have the bones of the system ready to go. Next I have to link up an exporter to a processor.
- [ ] Determine idomatic way for an exporter to return the status of the exporter operation to the processor.
- [ ] Implement an invariant that droppedAttributesCount is only serialized IFF attributes is non-zero length OR attributes is zero length and droppedAttributesCount is non-zero.
	- [ ] LogRecords
	- [ ] ScopeLogs
	- [ ] ResourceLogs
- [ ] Finalize interface between the log record processors and the log record exporter.

## Low priority
- [ ] Implement an "array" value type.
- [ ] Implement a bytes value type.

