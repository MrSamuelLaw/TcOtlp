# Check: bounded cleanup must not leak

## Rule

A loop that releases a collection (`free`, `FB_Exit`, `clear`, `reset`, drop or flush paths) may stop at an iteration limit only if the collection **can never be longer than that limit**. After the loop, the code must not set the head, tail or count to empty while unreleased nodes may still remain.

Either:

- the limit is the same value the collection's insert path already enforces, such as `maxCount` checked in `push` or `setAttribute`, and that value can never be 0 ("unbounded") at the same time, or
- the loop stops without discarding the rest: it leaves `_head` pointing at the first unreleased node, so a later call or cycle can continue, or
- a comment states why the collection can never exceed the limit, and the code backs that claim up.

## Why

- CLAUDE.md requires every owned allocation to be released exactly once. A cleanup loop that stops at `MAX_LOOP_COUNT` and then sets `_head := 0` orphans every node after the limit, so that memory leaks from the router heap.
- CLAUDE.md also requires bounded execution, so the loops need a limit. The fix is to make the limit match what the collection can actually hold, not to remove the limit.
- The leak is invisible in tests that use short collections. It only shows up under sustained load, when a queue with `maxCount = 0` (no limit) backs up behind a slow exporter.

## What to look for

- Grep for `__DELETE`, `.delete(pSelf:=` and `free` in method bodies, then open every `FOR`, `WHILE` or `REPEAT` loop that walks `_head` / `nxt` / `next()`.
- For each loop, find:
  1. **The loop limit**, such as `TcOtlp_GVL.MAX_LOOP_COUNT`, `THIS^.maxCount` or a local count.
  2. **The collection's real maximum length.** Read the insert path (`push`, `append`, `setAttribute`, `add...`). Check whether it rejects inserts at a limit, and whether that limit can be 0 or unlimited. Look at the `FB_Init` defaults and at what callers pass. For example, `FB_LoggerProvider` passes `MAX_LOG_RECORDS_PER_SCAN` into `FB_LogRecordQueue`.
  3. **What happens after the loop.** A line such as `_head := 0`, `_tail := 0` or `count := 0` placed after a loop that may have stopped early is the leak.
- Check off-by-one limits: `FOR _idx := 0 TO maxCount` runs `maxCount + 1` times, which is fine. `FOR _idx := 1 TO maxCount - 1` runs one time too few.
- `transferTo` or move paths that stop at a count, then patch head and tail pointers: check that no node is left outside both lists.

## Exceptions (do not report)

- Loops whose limit equals or exceeds a maximum length that the insert path enforces, when that maximum can never be 0 or unlimited.
- Loops that walk a collection to **read** it (serialize, count, search) and do not release or clear anything. Those fall under the bounded-execution rule, not this check.
- Per-cycle work budgets that deliberately leave the rest of the collection intact for the next cycle, such as exporting at most N records per scan.

## Preferred structures

- Enforce a limit on insert, and use **that same value** as the cleanup loop's limit. This is what `FB_Attributes` does with `maxCount`.
- If a collection allows `maxCount = 0` to mean unlimited, either:
  - enforce a hard upper limit on insert anyway, for example `MAX_LOOP_COUNT`, and count the rejected items in `droppedCount`, or
  - make cleanup resumable: release up to the limit, leave `_head` at the next node, report that more remains, and let `FB_Exit` or the next cycle finish.
- Do not reset `_head`, `_tail` or `count` to empty unless the loop reached the end of the list, meaning it saw `_head = 0` or `next() = 0`.

## Severity

- **violation:** a release loop can stop before the end of a collection whose length is not provably within the limit, and the code then clears the list pointers. One example is an unlimited queue freed with a `MAX_LOOP_COUNT` limit.
- **review:**
  - the limit is correct only because of a caller's configuration and not the collection's own insert check
  - off-by-one limits
  - release loops without a clear-after that might need several calls to finish
