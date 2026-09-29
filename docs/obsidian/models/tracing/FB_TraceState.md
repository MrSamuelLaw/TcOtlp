---
type: model
domain: tracing
status: implemented
implements:
  - FB_TraceState
  - TraceStateFactory
  - E_TraceStateFailureReason
source: TcOtlp/otel/OTEL/TRACING/TRACESTATE/
gap: TraceContextPropagator (extract/inject) does not exist yet, so nothing parses or truncates at a carrier boundary outside tests.
---

`FB_TraceState` is the immutable VALUE OBJECT for the W3C `tracestate` header: an ordered list of up to 32 vendor `key=value` entries that travels next to `traceparent`. It is its own submodule because it has its own grammar, validation and length limits. Those are more than a plain string can express, and they are not attribute semantics either.

## Why not attributes

It looks like a key/value collection, but it behaves differently from [[FB_Attributes]]:

| | Attributes | Trace state |
| --- | --- | --- |
| Order | Not significant | Significant: the leftmost entry is the most recently updated |
| Keys | Any string | Restricted grammar, including the `tenant@system` form |
| Values | Any `AnyValue` | Printable ASCII only, up to 256 characters, no `,` or `=` |
| Size limit | `maxCount`, dropped count | 32 entries; propagate at least 512 characters, truncated by W3C rules |
| Wire form in OTLP | Array of `KeyValue` | **One string** (`Span.trace_state`, `Link.trace_state`) |
| Wire form in W3C | — | The same string, as the `tracestate` header |

The last two rows decide the design. Both wire forms are the **same canonical string**, so nothing ever needs the list form except code that reads or edits one entry.

## Representation

**Recommended: the canonical header string, validated once.** `FB_TraceState` owns exactly one heap buffer, sized to the string plus its terminator. That buffer is the header in canonical form: entries separated by `,`, with optional whitespace removed. The constructor guarantees it is valid.

- Clone is one allocation and one `MEMCPY`, which is the same cost as the `FB_String` it replaces.
- OTLP serialization and `inject` write the buffer as it is. Nothing is rebuilt from a list.
- `truncate` splits the buffer on `,`. The scan is bounded by the string length, and the entry table by the 32-entry limit.
- There is no per-entry allocation. A full list would otherwise cost 32 node allocations on every span that carries it.

The alternative is a linked list of entries, following [[FB_Attributes]]. It only pays off if the PLC edits trace state often. The PLC never adds or edits an entry of its own, so trace state is only ever passed through, and the string form wins.

## Invariants

- Immutable. Nothing edits an `FB_TraceState` after construction; `truncate` builds a **new** one, as the OpenTelemetry API requires.
- Always valid. Anything that fails the grammar is rejected before any allocation happens.
- Never empty. An absent or empty header means `pTraceState = 0` on the holder, not an empty object. W3C: accept empty headers, but do not send them.
- At most 32 entries, and no duplicate keys.
- Supports lengths above `T_MaxString`. All copying and measuring uses `LEN2` and `MEMCPY` on the buffer, never an assignment of `STRING` / `T_MaxString`, because those would silently cut the value at 80 or 255 characters.

## TraceStateFactory

A `PROGRAM` factory. Like `ValueFactory` and `LinkFactory`, each method returns `BOOL`, takes `pDest` as `VAR_IN_OUT` (it must be `0` on entry), and reports `failureReason` as an output.

- **`parse(pDest, pHeader: POINTER TO STRING, failureReason)`**. Validates the header and canonicalises it into a new object.
  - Validation covers the key and value grammar, the 32-entry limit and duplicate keys.
  - An empty or whitespace-only header succeeds with `pDest = 0`.
  - An invalid header fails. W3C says an unparseable tracestate must not be propagated, so the caller drops it and keeps the `traceparent`.
- **`clone(pDest, pSrc, failureReason)`**. Makes one copy of the buffer. `ContextFactory`, `LinkFactory`, `FB_Span` and `FB_Tracer` use it.
- **`truncate(pDest, pSrc, maxLength, failureReason)`**. Applies the W3C rules for a limited carrier: remove entries longer than 128 characters first, then remove entries from the right, until the whole string fits. Entries are always removed whole and never cut. If nothing fits, it succeeds with `pDest = 0`; if everything fits, it is a `clone`.

`FB_TraceState` itself exposes `length`, `count` and `pString`, a read-only view for serializers. Release it with `pTraceState^.delete(pSelf:=pTraceState)`.

## Limits

| Constant | Value | Source |
| --- | --- | --- |
| `MAX_ENTRIES` | 32 | W3C list limit |
| `MAX_KEY_LENGTH` | 256 | W3C key grammar |
| `MAX_VALUE_LENGTH` | 256 | W3C value grammar |
| `MAX_HEADER_LENGTH` | 16447 | 32 full entries, plus separators; bounds the `parse` loop |
| `CARRIER_LENGTH` | 512 | W3C §3.3.1.5: SHOULD propagate at least 512 characters |
| `LARGE_ENTRY_LENGTH` | 128 | W3C truncation: remove entries over 128 characters first |

These are `VAR CONSTANT` on `TraceStateFactory`. The carrier type at the RPC boundary is `STRING(512)`. `parse` accepts any header up to `MAX_HEADER_LENGTH`. The 512 limit is only for fixed carriers: the RPC input, and the output of `inject`.

## Holders

- `FB_SpanContext`, `FB_Span` and `FB_Link` store `traceState: POINTER TO FB_TraceState` and release it in `free`.
- `ContextFactory.buildContext` takes `pTraceState: POINTER TO FB_TraceState`. The pointer is borrowed and cloned, so the caller still owns and releases its own trace state.
- `LinkFactory`, `FB_Span` and `FB_Tracer`'s parent setters copy through `TraceStateFactory.clone`.
- `FB_SpanProtoJsonSerializer` writes `traceState` from `pTraceState^.pString`. It still emits a single JSON string, and the wire output does not change. A 515-character state is written whole (`testSerializeLongTraceState`).

## Propagation (not built yet)

- `TraceContextPropagator.extract` takes `tracestate: STRING(512)` and calls `TraceStateFactory.parse`. A bad trace state is dropped without failing extraction. A bad traceparent drops the trace state as well.
- `inject` writes the canonical string, truncated to 512 characters. It writes nothing when trace state is absent.

## Tests

`FB_TestTraceState` covers canonicalisation (whitespace and empty members), empty headers, key and value rejections, duplicate keys, the 32-entry limit, a 515-character header, `clone` independence and `truncate`. `FB_TestSpanProtoJsonSerializer.testSerializeLongTraceState` checks a 515-character state through a remote context, a span and the serializer.

## Decisions

- **The PLC never adds its own entry.** So there is no `put`, `delete` or `get`. Add them only if a PLC vendor key is ever needed.
- **The sender truncates.** Ignition truncates by the W3C rules before it fills the `STRING(512)` carrier. The PLC does not treat a full buffer as suspect. `truncate` applies the same rules to what the PLC sends out.
