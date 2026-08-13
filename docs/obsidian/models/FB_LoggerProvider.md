`FB_LoggerProvider` is a context object that exposes the `FB_Resource` used by its loggers.

The provider borrows the resource reference supplied to `FB_Init`; the scope that declares the resource remains responsible for its lifetime. A logger likewise borrows a reference to the provider, so both the provider and its resource must remain valid while that logger can start log records.

When a logger creates a log record, it copies the current resource and instrumentation scope into the record. Processors can therefore retain a cloned record without retaining the logger, provider, resource, or scope that created it.

## Members

- **`FB_Init(resource: REFERENCE TO FB_Resource)`** — Stores a borrowed reference to the resource.

- **`resource: REFERENCE TO FB_Resource`** — Read-only property that returns the borrowed resource.

The provider has no cyclic behavior and no explicit setup or teardown operations beyond initialization.
