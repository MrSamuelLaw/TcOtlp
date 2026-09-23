# Check: every release clears the pointer

## Rule

Whenever code releases memory through a pointer, the same statement or the one right after it must set that pointer to 0:

- object release: `p^.delete(pSelf:=p);`. `delete` takes the caller's pointer as `VAR_IN_OUT pSelf` and clears it, so passing any other pointer than the one being released is wrong.
- raw release: `__DELETE(p);` followed right away by `p := 0;`.
- clearing the whole struct that holds the pointer, for example `MEMSET(ADR(THIS^.value), 0, SIZEOF(THIS^.value))` right after the delete, also counts.

This applies to locals as well as fields. Locals are held to the same rule so the convention does not depend on knowing a variable's lifetime.

## Why

- CLAUDE.md says every owned allocation is released exactly once. A pointer that is released but not cleared still looks owned, so a later `free`, `FB_Exit`, error path or retry will release it a second time. That double free corrupts the router heap, and the crash usually shows up far from the bug.
- Existing `free` methods are called from `FB_Exit` and may also be called directly. A field that `free` does not clear gets released twice when both run.
- CLAUDE.md also says a transfer clears the caller's pointer. Releasing is the same idea: once the memory is gone, the pointer is cleared.

## What to look for

- Grep for `\.delete\(` and check that every call has the form `<p>^.delete(pSelf:=<p>)`, with the same pointer on both sides. Report calls that pass a different pointer as `pSelf` (delete refuses them, so the object leaks).
- Grep for `__DELETE\(` and check the next statement or statements for `<same expression> := 0`, or for a `MEMSET` that zeroes the struct holding it. Walk through `END_IF` when the delete is inside a guard, for example:

  ```
  IF THIS^._pBuffer <> 0 THEN
      __DELETE(THIS^._pBuffer);
  END_IF
  ```

  This does **not** clear the pointer.
- For each `free` method: every pointer field it releases must be 0 when it returns, so that a second `free` call, or `free` followed by `FB_Exit`, does nothing.
- `delete` methods: they must take `VAR_IN_OUT pSelf: POINTER TO <own type>` (or the abstract base type for an override), return `FALSE` without releasing anything when `pSelf <> THIS`, and clear `pSelf` before `__DELETE`.

## Exceptions (do not report)

- `__DELETE(_pThis)` inside the object's own `delete` method, because `pSelf` (the caller's pointer) was already cleared just before it.
- A local pointer released immediately before `RETURN` or at the very end of a method with no later statements. Report it as `review` rather than `violation` when a bare `__DELETE(p)` is used, because the convention still applies.
- Linked-list node walks where the node pointer is overwritten on the next statement before any further use, for example `_node := THIS^._head; THIS^._head := _node^.nxt; __DELETE(_node);`, when `_node` is reassigned at the top of the next iteration and is not read after the loop. Mention it only if `_node` is read again after the loop.

## Preferred structures

- `p^.delete(pSelf:=p);` everywhere. Every heap-allocated FB (`FB_LogRecord`, `FB_Span`, `FB_SpanContext`, `FB_Status`, `FB_Link` and the value types) uses this contract.
- In `free` methods:

  ```
  IF THIS^.pX <> 0 THEN
      __DELETE(THIS^.pX);
      THIS^.pX := 0;
  END_IF
  ```

  This is how `FB_String.free` and `FB_KeyValue.free` are written.

## Severity

- **violation:** a **field** or other long-lived pointer (for example `THIS^.x`, `VAR_IN_OUT` or `VAR_OUTPUT`) is released without being cleared, especially in a `free` that `FB_Exit` also calls. A second call would free it twice.
- **review:**
  - an uncleared `__DELETE` on a **local** pointer. There is no double free today, but it breaks the convention.
  - a `delete` method that does not follow the `VAR_IN_OUT pSelf` contract
