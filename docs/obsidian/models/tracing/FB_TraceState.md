---
type: model
domain: tracing
status: design
implements:
  - FB_TraceState
  - TraceStateFactory
  - E_TraceStateFailureReason
source: TcOtlp/test/OTEL/TRACING/TRACESTATE/
gap: nothing implemented. Spans, links and contexts still hold trace state as POINTER TO FB_String.
---

`FB_TraceState` is the immutable VALUE OBJECT for the W3C `tracestate` header: an ordered list of up to 32 vendor `key=value` entries that travels next to `traceparent`. It is its own submodule because it has its own grammar, validation, mutation rules and length limits. Those are more than a plain string can express, and they are not attribute semantics either.

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
- `get`, `put` and `delete` scan the buffer. The scan is bounded by the 32-entry limit, and so by `MAX_LOOP_COUNT`.
- There is no per-entry allocation. A full list would otherwise cost 32 node allocations on every span that carries it.

The alternative is a linked list of entries, following [[FB_Attributes]]. It only pays off if the PLC edits trace state often. On a PLC, trace state is almost always passed through unchanged, so the string form wins.

## Invariants

- Immutable. `put` and `delete` build a **new** `FB_TraceState`, as the OpenTelemetry API requires; the original is untouched.
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
- **`clone(pDest, pSrc, failureReason)`**. Makes one copy of the buffer. This replaces `ValueFactory.cloneString` in `LinkFactory`, `FB_Span` and `FB_Tracer`.
- **`put(pDest, pSrc, pKey, pValue, failureReason)`**. Returns a copy with the entry at the **front**. An existing entry with that key is moved and updated. If adding the entry would exceed 32 entries, the rightmost entry is dropped. `pSrc` may be `0`.
- **`delete(pDest, pSrc, pKey, failureReason)`**. Returns a copy without that key. If no entries remain, it succeeds with `pDest = 0`.
- **`truncate(pDest, pSrc, maxLength, failureReason)`**. Applies the W3C rules for a limited carrier: remove entries longer than 128 characters first, then remove entries from the right, until the whole string fits. Entries are always removed whole and never cut.

`FB_TraceState` itself exposes `length`, `count`, `get(pKey, pValue out)` and `pString`, a read-only view for serializers. Release it with `pTraceState^.delete(pSelf:=pTraceState)`.

## Limits

| Constant | Value | Source |
| --- | --- | --- |
| `TRACE_STATE_MAX_ENTRIES` | 32 | W3C list limit |
| `TRACE_STATE_MAX_KEY_LENGTH` | 256 | W3C key grammar |
| `TRACE_STATE_MAX_VALUE_LENGTH` | 256 | W3C value grammar |
| `TRACE_STATE_CARRIER_LENGTH` | 512 | W3C §3.3.1.5: SHOULD propagate at least 512 characters |
| `TRACE_STATE_LARGE_ENTRY` | 128 | W3C truncation: remove entries over 128 characters first |

The carrier type at the RPC boundary is `STRING(512)`. `parse` accepts any length it is given. The 512 limit is only for fixed carriers: the RPC input, and the output of `inject`.

## Changes to existing code

These are mechanical once the submodule exists:

- `FB_SpanContext`, `FB_Span` and `FB_Link` store `traceState: POINTER TO FB_TraceState` in place of `POINTER TO FB_String`. Getters and `free` follow.
- `ContextFactory.buildContext`, `LinkFactory` and `FB_Tracer` call `TraceStateFactory.clone`.
- `FB_SpanProtoJsonSerializer` writes `traceState` from `pTraceState^.pString`. It still emits a single JSON string, and the wire output does not change.
- `TraceContextPropagator.extract` takes `tracestate: STRING(512)` and calls `TraceStateFactory.parse`. A bad trace state is dropped without failing extraction. A bad traceparent drops the trace state as well.
- `inject` writes the canonical string, truncated to 512 characters. It writes nothing when trace state is absent.

## Tests to write first

- Round trip: parse, then serialize, gives the canonical string. Includes whitespace around `,`.
- A 512-character state survives clone, span, link and the ProtoJSON serializer without being cut. This also checks that the `pString^` dereference in `serializeStringValue` is safe for long strings.
- Rejection: an upper-case key, `=` in a value, a trailing space in a value, 33 entries, a duplicate key.
- `put` moves an existing key to the front. `put` on a full list drops the rightmost entry.
- `truncate` removes large entries first, then entries from the right, and never cuts an entry.

## Open questions

- **A carrier truncated in transport.** If the RPC `STRING(512)` fills exactly, the sender may have cut an entry in half, and the cut entry may still parse. Either the caller (Ignition) must truncate by the W3C rules before it sends, or the PLC treats a full buffer as suspect and drops the last entry. The first is cleaner.
- **A PLC vendor entry.** Does this controller ever `put` its own key? If not, `put` and `delete` can wait, and the first slice is `parse`, `clone`, `truncate` and serialization.
