---
type: model
domain: tracing
status: implemented
implements:
  - FB_IdGenerator
---

`FB_IdGenerator` produces the trace and span identifiers that [[FB_Tracer]] instances attach to new [[FB_Span]] objects. It is the only place in the tracing domain that creates identifier values; every other function block borrows or copies them.

Generation is deliberately separated from span creation because identifier generation is not guaranteed to be bounded work. [[FB_TracerProvider]] owns the generator and refills it across cycles, so that `startSpan` performs a constant-time take rather than generating inline. When the generator is empty the requesting tracer fails rather than blocking, and reports that no identifiers were available.

## Invariants

Both identifier types are owned by the Value Creation domain (`FB_TraceId`, `FB_SpanId`) and follow the OTLP validity rules:

- A trace ID is 16 bytes and MUST NOT be all zeroes.
- A span ID is 8 bytes and MUST NOT be all zeroes.
- An all-zero identifier is the OTLP representation of "invalid/absent", so the generator must never emit one.

## Methods

- **`generateTraceId(traceId: FB_TraceId, failureReason: E_IdGenFailureReason) -> BOOL`** — Produces one valid trace ID. Returns `FALSE` without modifying the output on failure.

- **`generateSpanId(spanId: FB_SpanId, failureReason: E_IdGenFailureReason) -> BOOL`** — Produces one valid span ID. Returns `FALSE` without modifying the output on failure.

- **`call(failureReason: E_IdGenFailureReason) -> BOOL`** — Advances any bounded per-cycle generation work. Invoked by the owning provider, not by tracers.

## Implementation

### A list of chunks

The generator is a linked list of eight-byte chunks (`ST_IdChunkNode`) plus the utility methods that cut identifiers out of it. Eight bytes is the width of a span ID and half the width of a trace ID, so every identifier is a whole number of chunks:

- `generateSpanId` takes **one** node.
- `generateTraceId` takes **two** nodes.

Nothing about an identifier width is baked into a fixed array. The length of the list is chosen where the generator is declared, through `FB_Init`, and both parameters are required at every instantiation:

```iecst
_idGen: FB_IdGenerator(maxCount := 128, guidsPerRefill := 32);
```

`maxCount` is the number of chunks the list holds when full; it is raised to two if a shorter list is asked for, because a list shorter than a trace ID could never serve one. `guidsPerRefill` is capped at what the list can actually hold.

Nodes are allocated on demand up to `maxCount` and are never freed while the generator lives. A drained node moves to a spare list and is refilled in place, so a warm generator stops allocating entirely.

### Entropy source

Chunks are filled from `Tc2_System.FB_CreateGUID`, which is the operating system random generator reached over ADS. This removes the need to argue about uniqueness from a hand-rolled seed: the OS generator is already responsible for uniqueness across restarts and across PLCs, and a `GUID` is 16 bytes, which is exactly two chunks.

The cost is that the request is **asynchronous**. `FB_CreateGUID` is ADS-backed and reports `bBusy` across several cycles, which is precisely the reason the design separates generation from span creation. `call` drives the request and appends the chunks it returns; `generateTraceId` and `generateSpanId` only take a fixed number of nodes off a list that is already populated.

### The staging block

`FB_CreateGUID` writes into one contiguous region, so it cannot fill linked nodes in place. A single staging block is allocated on the first `call`, sized from `guidsPerRefill`, and each returned GUID is split into its two chunks and appended to the list. Sizing the block that way keeps a refill to one ADS round trip instead of one per chunk.

`__NEW` cannot build an array of a structured type, so the block is claimed as plain bytes and read back as GUIDs. A `GUID` has no padding, so the two layouts agree.

The remaining timing rules are:

- A refill is only started once a whole GUID's worth of room has opened in the list, and `bExecute` is asserted on the following `call`, which leaves a low cycle for the edge.
- `bBusy` is only trusted after `bExecute` has been observed held for a full cycle, so a completed prior request is not mistaken for the current one.
- The staging block is only read once a request completes and only written while one is in flight, so its address is stable for the life of a request.

The generator only runs dry when the list is consumed faster than it refills. Generation then fails with `NO_IDENTIFIERS_AVAILABLE` rather than blocking the cycle or re-issuing a stale identifier.

### Zero identifiers

An all-zero identifier is the OTLP invalid value, so that draw is discarded and another is cut instead, under a bounded retry budget. The chunks are assembled into a local before being copied out, so a failed draw leaves the caller's identifier untouched. In practice this never fires against a real random source; it exists so the OTLP invariant is enforced by the generator rather than assumed.

## Failure reasons

`E_IdGenFailureReason`:

- `NA` — no failure occurred.
- `NO_IDENTIFIERS_AVAILABLE` — the chunk list held too few chunks; the caller must retry on a later cycle.
- `GUID_SERVICE_FAILED` — the TwinCAT GUID service reported an ADS error while the list was being refilled.
- `MEMORY_ALLOCATION_FAILURE` — a chunk node or the staging block could not be allocated.
