---
type: model
domain: tracing
status: implemented
implements:
  - FB_SpanExporter_Base
  - FB_SpanExporter_File
  - FB_SpanExporter_Console
  - FB_SpanExporter_HTTP
source: TcOtlp/test/OTEL/TRACING/EXPORTING/FUNCTION_BLOCKS/
gap: register is not implemented, so nothing stops two processors from sharing one exporter.
---

`FB_SpanExporter_Base` defines the ownership and coordination contract shared by span exporters. It mirrors [[FB_LogRecordExporter]]. Processors check `isBusy()` before offering a batch, and they call `tick` every scan to advance the exporter's destination work. The exporter is the only tracing component allowed to perform destination I/O.

Only ended spans reach an exporter. A span that has been started but not ended is never offered for export, so the exporter never has to reason about mutable spans.

## Methods

- **`export(spans: FB_SpanQueue, count: UDINT, failureReason: E_SpanExporterFailureReason) -> BOOL`** — If the exporter is busy, returns `FALSE` with `ACTIVE_EXPORT_IN_PROGRESS` and leaves the source queue unchanged. Otherwise, transfers ownership of up to `count` oldest spans from the source queue into the exporter without cloning them. Accepted spans are removed from the source queue. A `count` of zero transfers no spans. Queue-transfer failure returns `FALSE`; successful transfer returns `TRUE`, including an empty transfer.

- **`isBusy() -> BOOL`** — Reports whether the exporter can currently accept another batch.

- **`tick(failureReason: E_SpanExporterFailureReason) -> BOOL`** — Advances the concrete exporter's cyclic work and reports destination-specific failure. The processor that owns the exporter calls it once per provider tick.

- **`free()`** — Releases all spans currently owned by the exporter and clears its active-export flag. `FB_Exit` invokes this during normal destruction.

## Concrete exporters

Concrete exporter function-block bodies invoke `tick()`.

| Exporter | Status | Busy semantics |
| --- | --- | --- |
| `FB_SpanExporter_File` | Implemented | Busy while its serialization and file-I/O state machine owns a batch, which takes several scans; exposes that state through `currentState`. |
| `FB_SpanExporter_Console` | Implemented | Never busy; writes the accepted spans and releases the batch inside `export`. |
| `FB_SpanExporter_HTTP` | Implemented | Busy for the duration of the OTLP/HTTP request/response cycle; exposes that state through `currentState` and the last `statusCode`. |

### FB_SpanExporter_File

`FB_Init(filepath)` sets the target file. Each accepted batch is appended to the file as one line of JSON, a complete `TracesData` object, so the file is JSON Lines. The state machine runs `idle`, `serializing`, `opening`, `buffering`, `writing`, `closing`, then `done`, or `error` on a failure. The batch is released in `done` or `error`. In both states `export` accepts a new batch straight away.

The exporter starts a batch on the rising edge of "export active and the batch queue is not empty". This relies on the serializer draining the batch queue in the `serializing` state, which re-arms the edge before the batch ends; see the drain requirement in [[Spans ProtoJSON Serializer]].

Use it with [[FB_SpanProcessor_Batch]]. The exporter stays busy for several scans, and [[FB_SpanProcessor_Simple]] drops every span that ends in that time.

### FB_SpanExporter_HTTP

`FB_Init(url, bNoServerCertCheck)` sets the full collector endpoint, for example `http://192.168.1.10:4318/v1/traces`. `F_ParseHttpUrl` in `OTEL/COMMON` splits the URL into scheme, host, port and path once, at initialisation. `FB_LogRecordExporter_HTTP` uses the same parser. The scheme must be lower-case `http` or `https`, and IPv6 hosts are not supported. `bNoServerCertCheck` allows HTTPS to a collector with a self-signed certificate.

Each accepted batch is sent as one `POST` with `Content-Type: application/json` and a complete `TracesData` document as the body. The state machine runs `idle`, `serializing`, `sending`, `waiting`, `processing`, then `done`, or `error` on a failure:

| Failure | When |
| --- | --- |
| `HTTP_URL_PARSE_FAILURE` | The URL could not be parsed. Reported on the first tick, before anything is serialized. |
| `SERIALIZATION_FAILURE`, `BUFFER_ALLOCATION_FAILURE` | The batch could not be serialized or the payload buffer could not be allocated. |
| `HTTP_REQUEST_FAILURE` | The request could not be sent, or it failed, for example because the connection was refused. |
| `HTTP_STATUS_FAILURE` | The collector answered outside 2xx. `statusCode` holds the answer. |

The payload buffer is kept until the request completes and is released in `processing`, or by `FB_Exit` if the instance is destroyed with a request in flight. Nothing is retried: the batch is released in `done` or `error`, and `export` accepts the next one straight away. It starts on the same edge as the file exporter, so it also relies on the serializer draining the batch.

Use it with [[FB_SpanProcessor_Batch]], for the same reason as the file exporter.

The state machine mirrors `FB_LogRecordExporter_HTTP` in [[FB_LogRecordExporter]].

### FB_SpanExporter_Console

Writes one line per span to the TwinCAT ADS log at hint level, for development and commissioning. `export` accepts the batch, writes a line for each span, and releases the batch before it returns. So `isBusy()` is always `FALSE` and `tick` does nothing. That makes it the natural partner for [[FB_SpanProcessor_Simple]], which then writes every span, even spans that end in the same scan.

It does not serialize. `format` builds the line and is public, so tests can check it without reading the log:

```text
span "work" trace=01010101010101010101010101010101 span=0202020202020202 parent=none kind=SPAN_KIND_INTERNAL status=STATUS_CODE_UNSET duration=500ns
```

- Identifiers are written as lower-case hex.
- A root span is written with `parent=none`.
- A span without a status is written as `STATUS_CODE_UNSET`.
- The duration is `endTimestamp - startTimestamp` in nanoseconds, or 0 if the end is not after the start.
- Attributes, links, resource and scope are not written.
- Lines are truncated at 255 characters.

Writing is bounded by `MAX_LOOP_COUNT` spans per batch; any spans beyond that are released without a line.

## Serialization

File and HTTP exporters pass their batch queue to [[Spans ProtoJSON Serializer]], which takes ownership of the spans and drains the queue. After serializing, the exporter holds only the JSON document; the spans are already released. `free` in `done` or `error` releases whatever a failed or interrupted export left behind.

## Open questions

- Whether an exporter must preserve parent-before-child ordering within a batch, or whether the collector reassembles the tree from `parent_span_id` alone. The OTLP spec allows arbitrary ordering; confirming this lets the batch processor stay a simple FIFO.
