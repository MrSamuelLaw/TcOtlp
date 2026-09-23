# Check: one pointer per address

## Rule

Every allocated address has **exactly one owning pointer at any point in time**. When a pointer is copied, one of the two copies must be cleared in the same step, so that ownership *moves* instead of being duplicated:

```
dest := src;
src := 0;   // same step: never two owners
```

No second pointer to the same address may be **stored**. That means an FB field (`VAR`, `VAR_INPUT`, `VAR_OUTPUT`), a list node, a global, `VAR_STAT` or `VAR_INST`. The only exceptions are the non-owning kinds listed below, which must be declared and documented as such.

Short-lived copies are allowed only while one method call runs:

- a local variable, or a `VAR_INPUT` parameter that is only borrowed (see `borrow-not-own`)
- the copy must not be stored, returned as owned, or released
- it must not be used after the owner may have released the address

## Why

- CLAUDE.md: "A callee owns a pointer only when the contract says so and the caller's pointer is cleared," and "release every owned allocation exactly once." With two stored pointers to one address, either both holders release it (a double free) or each holder assumes the other will (a leak).
- A copied pointer goes stale silently. After the owner releases the memory, the copy still looks valid, and reading or writing through it corrupts whatever is allocated there next. This is worst for state in flight across scan cycles, which CLAUDE.md requires to stay valid until an asynchronous request finishes.
- Having one owner makes ownership checkable by reading the code: find the one field or node holding the address, and that is the code that releases it.

## What to look for

- **Pointer copies that are not moves.** Every assignment `a := b`, where both sides are `POINTER TO` or `REFERENCE TO` an allocated object. Check whether `b` is cleared (`b := 0`) or is a local that goes out of use right away. Report copies where both `a` and `b` stay live and at least one of them is stored.
  - This includes FB-call parameter bindings such as `pVal:=_pNum` into a callee that stores the pointer. Check that the callee either clones it (as `ValueFactory.createKeyValue` does, after which the caller releases its own copy) or clears the caller's copy.
- **Stored copies of a pointer another object owns.**
  - A field, output or list node set from `other^.field`, from `queue.next()` / `peek()`, from a getter, or from a `VAR_INPUT` parameter, where the value is kept past the current call. `FB_Span`, `FB_LogRecord`, `FB_Link` and `FB_Status` sub-objects must be **clones**, not copies of another record's pointer.
  - This is the snapshot rule in CLAUDE.md: records capture resource and scope *snapshots*, and processors *clone* records.
- **Two owning fields for one address.** One address reachable from two lists or two FBs, for example a record pushed to two queues without cloning, or a span stored both in `FB_Tracer.pSpan` and in a caller's variable after `build` returned without clearing `pSpan`.
- **`ADR(...)` stored.** Taking the address of a local variable, `VAR_INPUT`, temporary string or literal, and storing it in a field or list node, or passing it to a callee that stores it. The address dies when the method returns. `ADR(...)` passed to a callee that only reads it during the call (serializers, factories that copy the data) is fine.
- **Owning pointers returned without clearing.** Methods that return an owning pointer (as a return value or in `VAR_OUTPUT`) while also keeping it in a field.
- **`MEMCPY` or struct assignment of FBs or structs that contain owning pointers.** For example, `recordA := recordB` or `MEMCPY(ADR(a), ADR(b), SIZEOF(b))` duplicates every pointer inside. Deep copies must go through `clone` or a factory.

## Exceptions (do not report)

These are non-owning pointers. They are allowed as stored fields only if their declaration or a comment says they are non-owning, they are never released through, and the thing they point to is guaranteed to outlive them.

- **Wiring references** to statically declared FB instances, set once in `FB_Init`. For example: `FB_LoggerProvider._resource` (already commented "borrowed; the declaring scope owns its lifetime"), `FB_TracerProvider._resource` / `_idGenerator` and `FB_LogRecordProcessor_Simple._exporter`. They are not heap allocations and nobody releases them. Report them as `review` only if the non-owning comment is missing.
- **Interior cursors and iterators** into a structure the same FB owns, for example `FB_LogRecordQueue._cursor`, the queue's `_tail`, or `FB_IdGenerator._head` / `_tail` inside `_pBuffer`. The owning FB must reset them whenever it releases or changes the structure.
- **Short-lived borrows**, as described in the Rule.
- **Pointers passed to vendor APIs** that read the buffer during an asynchronous request, as long as the owner keeps the buffer alive and does not release it until the request is done. File and HTTP `_pString` in the exporters are examples.

## Preferred structures

- Move ownership: `dest := src; src := 0;` This is the `pDest` and `push` contract, for example `FB_Tracer.build`, `FB_Logger`'s record hand-off and `FB_LogRecordQueue.push`.
- Keep both sides with a clone: `ValueFactory.clone*`, `FB_LogRecord.clone` and `ContextFactory.buildContext`. The original owner keeps its pointer, and the new owner gets a separate allocation.
- Non-owning references use `REFERENCE TO` with a `// borrowed; <who> owns its lifetime` comment, so readers can tell them apart from `POINTER TO` owners.

## Severity

- **violation:**
  - two stored owning pointers to one allocation
  - a stored `ADR` of a local, input or temporary
  - a struct copy or `MEMCPY` that duplicates owning pointers
  - an owning pointer returned while also kept
- **review:**
  - a stored non-owning pointer with no comment saying so
  - an unclear binding into a callee whose storing or cloning behaviour could not be confirmed
  - a borrow that may be used after the owner releases it across scan cycles

Cross-references: `borrow-not-own` covers parameter signatures, and `release-clears-pointer` covers clearing on release. Report here only when the problem is **two live pointers to one address**, so the same line is not reported under three checks.
