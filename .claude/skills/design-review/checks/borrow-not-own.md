# Check: read-only access means `VAR_INPUT`

## Rule

A method that only **borrows** an object (reads it without taking ownership, replacing it, or clearing it) must receive the object's **pointer** as `VAR_INPUT`, not `VAR_IN_OUT`.

`VAR_IN_OUT pX: POINTER TO ...` is reserved for methods whose contract changes the caller's pointer:

- **Producers** that hand out a new allocation: `pDest`, as in `ValueFactory`, `ContextFactory`, `FB_LogRecord.clone`, `FB_Tracer.build` and `FB_Span.getContext`.
- **Consumers** that take ownership and clear the caller's pointer, such as `push`, `append`, `setAttribute` or `transferTo`, when the contract says the pointer is cleared on success.

Every `VAR_IN_OUT` pointer parameter must therefore sit next to a comment or contract that says which of these two it is.

## Why

- CLAUDE.md: "Make pointer ownership transfer explicit. A callee owns a pointer only when the contract says so and the caller's pointer is cleared." A `VAR_IN_OUT` pointer tells readers the callee *may* replace or clear it. When the callee only reads it, the signature misstates the ownership contract.
- CLAUDE.md: "Keep serialization side-effect free with respect to the source records." A serializer that takes `pLogRecord` by `VAR_IN_OUT` can, and by a typo might, set the caller's pointer to 0 or to another record. The caller would then leak the record or release it twice.
- `VAR_INPUT` makes the callee work on a copy of the pointer, so the caller's ownership cannot change, whatever the callee does.

## What to look for

- Every `VAR_IN_OUT` block in method and FB declarations. Collect each parameter declared as `POINTER TO <object>`, meaning an FB, a DUT or `STRING` data that is owned elsewhere.
- For each one, read the method body and decide what it does with the pointer:
  - **borrows** it: only dereferences it with `p^.x` or passes it down as a borrow. It never assigns `p :=`, never passes `p` to a `VAR_IN_OUT` parameter that assigns it, and never calls `p^.delete(pSelf:=p)`.
  - **produces**: assigns `p := <new allocation>`.
  - **consumes**: stores `p` somewhere and then sets `p := 0`.
- Report the borrows.
- Follow calls one level down: if a borrowed pointer is passed to another method's `VAR_IN_OUT` pointer parameter, that callee's parameter is a candidate too.
- Also check the reverse: a `VAR_INPUT` pointer that the method stores in a list or field as its own, and later releases. That is a consumer hiding behind a borrow signature, because the caller's pointer is not cleared. Report it as `review`.

## Exceptions (do not report)

- `VAR_IN_OUT` parameters that are **FB instances or structs**, not pointers, for example `logRecords: FB_LogRecordQueue` or `v: SJsonValue`. Passing them this way avoids copying an FB and is the normal TwinCAT idiom. Iteration state such as a queue cursor may change, but ownership of the object does not.
- Producer and consumer pointers whose contract is documented and followed, as described in the Rule.
- `VAR_IN_OUT` pointers required by an external library signature.

## Preferred structures

- Borrowed pointer:

  ```
  VAR_INPUT
      pLogRecord: POINTER TO FB_LogRecord;  // borrowed; not owned or released
  END_VAR
  ```

- Produced pointer: `VAR_IN_OUT pDest: POINTER TO X;` with the `pDest <> 0` precondition, assigned only on success, and a comment saying the caller owns it. `ValueFactory` is the example.
- Consumed pointer: `VAR_IN_OUT pValue: POINTER TO X;`, cleared to 0 when ownership is taken, with a comment saying so. `FB_LogRecordQueue.push` and `FB_Attributes.setAttribute` are the examples.

## Severity

- **violation:**
  - a serializer method, or any other method CLAUDE.md requires to be side-effect free, that takes a **borrowed** object pointer as `VAR_IN_OUT`
  - a `VAR_INPUT` pointer that the callee stores and later releases, where the caller's pointer is never cleared
- **review:**
  - a borrowed `VAR_IN_OUT` pointer in any other domain
  - a producer or consumer pointer whose ownership comment is missing
