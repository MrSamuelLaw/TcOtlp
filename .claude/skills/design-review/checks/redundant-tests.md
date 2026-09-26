# Check: no redundant tests

**Scope:** tests

## Rule

Every test method must check some behaviour that no other test already checks. A test is **redundant** when another, more complete test runs the same setup, reaches the same code paths, and asserts the same outcomes, or a superset of them. The narrow test adds run time and upkeep but catches no failure the broader test would miss.

A test can be redundant in three ways:

- **Subsumed.** Test B does everything test A does and asserts more. A's assertions all appear in B, against the same kind of input and the same code path.
- **Duplicated.** Two tests, often in different suites, check the same behaviour with the same kind of input. This usually happens after a refactor moves behaviour, for example the URL parser tests that moved from each HTTP exporter suite to `FB_TestHttpUrlParser`.
- **Superseded.** A test that was written for an earlier design and is now covered by a newer suite. One example is a trace state assertion in a span test after `FB_TestTraceState` was added.

## Why

- CLAUDE.md asks for the smallest change within the owning domain. Tests follow that too: each behaviour is tested once, in the suite of the domain that owns it.
- Redundant tests make a failure look bigger than it is. One bug turns several tests red, and the reader has to work out which one points at the cause.
- Each test adds to the TcUnit cycle time on the PLC, and each has to be migrated whenever an API changes, as the `FB_TraceState` rewiring showed.

## What to look for

- List every test suite under the scope (`FUNCTION_BLOCK ... EXTENDS FB_TestSuite`) and every test method it calls in its body.
- Group tests by the **production method they drive**. Grep each test for the factory, builder or method calls it makes (`ContextFactory.buildContext`, `TraceStateFactory.parse`, `LinkFactory.fromContext`, `serializeSpan`, `push`, `pop` and so on).
- Within each group, compare pairs:
  1. Same setup and the same kind of input (for example "a valid remote context with a trace state").
  2. Same code path. The same branches are taken: success versus failure, and which failure reason.
  3. Assertions: are all of A's assertions also made by B, on equal or stronger terms?
- Look across suites, not only inside one. A behaviour may be tested in its owning suite and again, incidentally, in a caller's suite, for example trace state copying in `FB_TestSpanContext`, `FB_TestLinks` and `FB_TestTracer`.
- Look for tests whose name or comment describes behaviour that a later, more thorough test in another suite now owns.
- Include failure-path tests. For example, two tests that both check `DESTINATION_ALREADY_ASSIGNED` for the same factory method are duplicates.

## Exceptions (do not report)

- **The same behaviour at different domain boundaries.** A factory test checks the factory. A caller's test that checks the caller *uses* the factory correctly (for example, that `FB_Tracer.setParentUsingContext` copies the trace state instead of borrowing it) tests the caller's contract, not the factory's. Report it only if its assertions go beyond what the caller is responsible for, for example re-checking trace state grammar in a tracer test.
- **Different inputs that exercise different branches or limits**, such as 32 entries accepted and 33 rejected, or an empty header versus a header of only empty members.
- **Regression tests for a specific bug**, when the comment names the bug or the edge case. Report them as `review` only if a broader test now clearly covers that exact edge case.
- **End-to-end tests** that run the whole pipeline (create, process, serialize, export). They overlap with unit tests on purpose.
- **Setup overlap alone.** Two tests that share setup but assert different outcomes are not redundant.

## Preferred structures

- Keep the more complete test, and move any assertion unique to the narrow test into it, **if** it fits the broader test's purpose. Otherwise keep the narrow test and cut its overlapping assertions.
- A caller's test keeps one assertion that shows it delegated to the owning domain (for example, "the trace state was copied and outlives its source"). Grammar and edge cases stay in the owning suite.
- Name the test that should stay, the one that should go, and the assertions to carry over.

## Severity

- **violation:** a test whose assertions are all made by another test, with the same kind of input and the same code path. Removing it loses nothing.
- **review:**
  - partial overlap, where most assertions are covered but one or two are unique
  - a caller-suite test that re-checks detail owned by another domain's suite
  - a regression test that may now be covered by a broader test
