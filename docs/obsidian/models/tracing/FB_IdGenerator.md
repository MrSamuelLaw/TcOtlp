---
type: model
domain: tracing
status: implemented
implements:
  - FB_IdGenerator
---

`FB_IdGenerator` produces the trace and span identifiers that [[FB_Tracer]] instances attach to new [[FB_Span]] objects. It is the only place in the tracing domain that creates identifier values; every other function block borrows or copies them.

Generation is deliberately separated from span creation because identifier generation is not guaranteed to be bounded work. [[FB_TracerProvider]] owns the generator and refills it across cycles, so that `startSpan` performs a constant-time take rather than generating inline. When the generator is empty the requesting tracer fails rather than blocking, and reports that no identifiers were available.

The abstract contract lives on `FB_IdGenerator_Base`, so a provider holds a `REFERENCE TO FB_IdGenerator_Base` and a test can substitute a deterministic generator for the ADS-backed one.

## Invariants

Both identifier types are owned by the Value Creation domain (`FB_TraceId`, `FB_SpanId`) and follow the OTLP validity rules:

- A trace ID is 16 bytes and MUST NOT be all zeroes.
- A span ID is 8 bytes and MUST NOT be all zeroes.
- An all-zero identifier is the OTLP representation of "invalid/absent", so the generator must never emit one. No logic is required in the generator to enforce this, this invariant is fulfilled by the entropy source so that it can be dis-regarded by test classes that mock ids.

## Methods

- **`generateTraceId(traceId: FB_TraceId, failureReason: E_IdGenFailureReason) -> BOOL`** — Produces one valid trace ID. Returns `FALSE` without modifying the output on failure.

- **`generateSpanId(spanId: FB_SpanId, failureReason: E_IdGenFailureReason) -> BOOL`** — Produces one valid span ID. Returns `FALSE` without modifying the output on failure.

- **`tick(failureReason: E_IdGenFailureReason) -> BOOL`** — Advances the bounded per-cycle refill work. Invoked by the owning provider, not by tracers.

- **`free()`** — Releases the ring. Called from `FB_Exit` when the instance is not being copied for an online change.

Supporting members:

- **`configValid: BOOL`** (property) — `TRUE` once the ring is allocated. Every entry point checks it first, so a generator whose construction failed reports a configuration mistake instead of reading through a null pointer.
- **`errorId: UDINT`** (output) — the last ADS error reported by the guid service, cleared to `0` on the next refill that lands.

## Implementation

### A ring of bytes

The generator holds a ring of random bytes and cuts identifiers out of it. There is no separate pool per identifier type, because a trace ID and a span ID are only different widths of the same random bytes:

- `generateSpanId` takes the next **8** bytes.
- `generateTraceId` takes the next **16** bytes.

Neither method names those numbers. Each asks its identifier how wide it is (`SIZEOF(spanId.bytes)`) and passes that to the private `_take`, so the widths stay a property of the Value Creation domain rather than something the generator restates.

One ring therefore tracks the combined consumption rate, and nobody has to guess the ratio between root spans and child spans up front.

The ring is claimed once with `__NEW` and contains no fixed-size array, because how many bytes it holds is a property of the declaration site, not of the function block:

```iecst
_idGen: FB_IdGenerator(nTraceIds := 16, nSpanIds := 32);
```

The parameters are counts, not byte lengths, so a caller never has to round anything to an 8- or 16-byte boundary. `nTraceIds` and `nSpanIds` are how many of each the ring holds when full; together they give its length, `nTraceIds * 16 + nSpanIds * 8` bytes. There is no parameter for the refill size, because refills are not a fixed size — see below.

One length is rounded, and it is the ring rather than any parameter: it grows **up** to a whole number of 16-byte GUIDs. The guid service writes nothing narrower than one whole GUID, so a remainder shorter than that could never be filled, and a ring cannot describe a hole to skip it — the tail would strand at the wrap. Rounding up also means the caller still gets at least the identifiers it asked for.

That rounding is load-bearing beyond the initial allocation. Because the ring length is a multiple of 16 and every refill is a multiple of 16, the room ahead of the fill point stays a multiple of 16 for the life of the ring. There is therefore never a gap at the wrap too small for the service to fill, which is what rules out the stall the rounding exists to prevent.

### A read point, a fill point, and the room ahead of each

- `_head` is where the unread bytes start; `_count` is how many there are.
- `_tail` is the fill point, where the next refill writes.
- `_headRoom` and `_tailRoom` are the bytes from each pointer to the end of the ring.

The room counters exist so that neither side has to subtract one pointer from another. Pointer subtraction has no precedent elsewhere in this repository and is awkward to reason about on 64-bit runtimes; a `UDINT` counter updated alongside each pointer says the same thing without it.

A take raises `_head` and lowers `_count` by the same amount, and **never touches `_tail`**. Two things follow: a refill in flight cannot have its destination moved out from under it, and no byte in the ring is ever copied to make room.

The two edges behave differently at the wrap:

- **A draw may straddle it.** `_take` copies the bytes ahead of `_head` first, and if that runs out before the draw is satisfied, stitches the remainder from the start of the ring with a second `MEMCPY`.
- **A refill never straddles it.** A refill is anchored at `_tail` and stops at the end of the ring, because the guid service writes one contiguous region and a fill that wrapped could not be expressed to it at all. Free space on the far side of the wrap is simply left to the refill after this one — filling that side first would leave a hole at `_tail`, and a ring has no way to describe a hole.

The seam is therefore something only the read side has to know about.

### Entropy source

Bytes come from `Tc2_System.FB_CreateGUID`, which is the operating system random generator reached over ADS. Asking the operating system removes any argument about uniqueness from a hand-rolled seed: the OS generator is already responsible for uniqueness across restarts and across PLCs. It is also what satisfies the OTLP rule that an identifier must not be all zeroes: the generator does not check for that case at runtime, because a run of zeroes out of an OS GUID is not a case that occurs. The invariant is enforced by the choice of source, not by a guard — the tests are what hold it.

The cost is that the request is **asynchronous**. `FB_CreateGUID` is ADS-backed and reports `bBusy` across several cycles, which is precisely why the design separates generation from span creation. `tick` drives the request; `generateTraceId` and `generateSpanId` only cut a fixed number of bytes off a ring that is already populated.

The service writes straight into the ring, so a refill costs one ADS round trip and no intermediate copy. The remaining timing rules are:

- **A refill claims whatever whole GUIDs fit.** Each `tick` with nothing in flight takes the room from `_tail` to the end of the ring, bounds it by the free space when that runs out first, and cuts the result down to a whole number of GUIDs. Refills are consequently variable in size. When fewer than 16 bytes are available the claim comes out zero, no request goes out, and a full ring simply does not ask.
- **The claim is remembered, not recomputed.** `_inFlight` holds the length handed to the service, because takes move `_head` while the request is out and the free space is no longer the same number by the time the request lands.
- **The service is only ever handed the region `_inFlight` claims.** That claim is what proves the region lies inside the allocation; outside it the service is passed a zero length rather than a region that could sit past the end of the ring.
- **`bExecute` is only asserted on the `tick` after the decision to refill.** The call to `_creator` sits at the top of `tick` and reads `_inFlight` as it was left last cycle, which is what leaves the service a low cycle to see the rising edge.
- **`bBusy` is ignored for one cycle after the edge.** `_edgeHeld` records that the service has now seen `bExecute` high, because until it has, `bBusy` still describes the previous request rather than this one.
- **A request that fails never advances `_count`**, so the bytes it did not write are not handed out as identifiers. The ADS error is latched on `errorId` and the claim is dropped, so the next `tick` starts a fresh request.

The generator only runs dry when the ring is consumed faster than it refills. Generation then fails with `NO_IDENTIFIERS_AVAILABLE` rather than blocking the cycle or re-issuing a stale identifier.

### Lifetime

`FB_Exit` calls `free()`, which releases the ring with `__DELETE`. This does not currently wait for a refill in flight: if the instance is destroyed while `_inFlight` is non-zero, the guid service still holds a pointer into freed memory. Generators are expected to outlive the provider that ticks them, so this has not bitten in practice, but it is a real gap against the repository rule that state handed to an asynchronous service must stay valid until the request finishes.

## Failure reasons

`E_IdGenFailureReason`:

- `NA` — no failure occurred.
- `NO_IDENTIFIERS_AVAILABLE` — the ring held too few bytes; the caller must retry on a later cycle.
- `GUID_SERVICE_FAILED` — the TwinCAT GUID service reported an ADS error while the ring was being refilled. The error code is left on the `errorId` output.
- `INVALID_CONFIGUATION` — no ring was allocated, or the draw is wider than the whole ring. The second case is reported as a configuration mistake rather than an empty ring because no amount of waiting could ever serve it. (The spelling is the enum member's; it is misspelled in the source.)
- `MEMORY_ALLOCATION_FAILURE` — declared but not currently emitted. A ring that fails to allocate leaves `configValid` false, which every entry point reports as `INVALID_CONFIGUATION`.
