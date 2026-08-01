## Constraints
- MUST NOT mutate the LogRecords it is serializing.
- MUST process each LogRecord only once.
- SHOULD group log records by resource and scope to minimize payload size.
