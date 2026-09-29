# Check: no static arrays of objects

## Rule

Do not use a fixed-length array to hold a collection of objects. An object here means one of the following:

- a function block instance
- a pointer or reference to a function block
- an interface
- a STRUCT or DUT that represents a domain item

Examples of domain items are traces, spans, span contexts, links, log records, key-values, attributes, values, exporters and processors.

Collections of objects must use a dynamic structure instead, such as a linked list or a queue. Growth is limited by an explicit count limit, not by the size of an array.

## Why

- **Wasted memory.** A fixed array reserves memory for its largest size for as long as its owner lives, even when it is mostly empty.
- **The size becomes the policy.** The array's length silently becomes the capacity and drop policy. CLAUDE.md gives those decisions to Log Processing, as explicit `maxCount` and drop-policy settings on the owning component.
- **Unclear ownership.** Arrays of pointers become ad-hoc object pools. They blur the explicit, single-owner pointer ownership that CLAUDE.md requires, where an owner releases each allocation exactly once and a transfer clears the previous owner's pointer.
- **Clearing is harder to get right.** An array has to be compacted or have its slots tracked. A list can move or drop one node without touching the rest.

Bounded execution still applies. Any loop over a list must be limited by the list's count or by an explicit per-cycle budget.

## What to look for

Search the declarations (`VAR`, `VAR_INPUT`, `VAR_OUTPUT`, `VAR_IN_OUT`, `VAR_INST`, `VAR_GLOBAL`, `VAR_STAT`, STRUCT members, and method and property locals) for `ARRAY`. Use a case-insensitive grep such as `ARRAY\s*\[`. Report the declaration when the element type is any of the following:

- `FB_*`, or any other function block type
- `POINTER TO <anything but a primitive>`, especially `POINTER TO FB_*`
- `REFERENCE TO ...`
- `I_*`, or any other interface type
- `ST_*`, `T_*` or `E_*` wrappers, or any other STRUCT or DUT that stands for a domain item, such as a span, record, link, attribute or context
- `STRING` or `T_MaxString`, **when** each element is one item in a collection of domain data, such as a list of attribute keys, log bodies or trace-state entries
- `ARRAY[*] OF` any of the above, used in a `VAR_IN_OUT` parameter to pass a collection of objects

Also check the following:

- **Parallel arrays that together model objects.** For example, `keys: ARRAY[0..N] OF STRING` alongside `values: ARRAY[0..N] OF ...` is a hand-rolled array of key-values.
- **Fixed-size slot tables.** These are an array paired with a count or an "in use" flag array, used as a pool or queue. Ring buffers of pointers also count.
- **Constants that only size an object array.** For example, `MAX_SPANS: UDINT := 32;` used as `ARRAY[1..MAX_SPANS]`. Report the array, and mention the constant.

## Exceptions (do not report)

- **Fixed-width binary representation of one value.** For example, `FB_TraceId.bytes: ARRAY[0..15] OF BYTE` and `FB_SpanId.bytes: ARRAY[0..7] OF BYTE`. The width is set by the OTLP or W3C specification, and the array *is* the single value, not a collection.
- **Primitive scratch buffers inside one method or one serialization step.** Examples are a local `ARRAY OF BYTE` used for hex encoding, a UTF-8 buffer, or a fixed-size I/O chunk. They hold primitive data, not objects, and they do not outlive the call or the transfer.
- **`VAR CONSTANT` lookup tables of primitives.** An example is a hex-digit table.
- **Buffers whose size is set by a vendor API.** Beckhoff and Tc2/Tc3 library calls sometimes require a fixed array type, for example `ADSREAD`, `FB_FileWrite` or GUID buffers. Report these only if objects are kept in them.

When an exemption is a close call, report it as `review` instead of skipping it.

## Preferred structures

Name the replacement that fits, and point to the existing example:

- **FIFO of owned records or spans:** a queue built on a linked list, following `FB_LogRecordQueue`. It holds `ST_LinkedListNode` head and tail pointers, a `count`, a `maxCount` where 0 means unbounded, a `droppedCount`, `push` and `pop` with explicit ownership transfer, and `transferTo`, which moves nodes between owners without copying. `FB_SpanQueue` is the tracing counterpart, still a stub.
- **Key-value collections:** `FB_Attributes`, which holds `FB_KeyValue` items with `maxCount` and `droppedCount`.
- **Links:** `FB_Links`, a stub today, with `push` and `pop` of `POINTER TO FB_Link`.
- **A new kind of collection:** a linked list of `ST_LinkedListNode`, or a new queue FB that follows the `FB_LogRecordQueue` contract. Include an explicit count limit, dropped-item accounting, and loops limited by `count`.

## Severity

- **violation:** an array of objects, as defined in the Rule, declared in production code under `TcOtlp/otel/OTEL/`.
- **review:**
  - an array of strings whose domain meaning is unclear
  - a borderline exemption
  - a parallel-array pattern that may be primitive data
  - any finding under `TcOtlp/test/TEST/`, when tests are in scope, since test fixtures sometimes need fixed data
