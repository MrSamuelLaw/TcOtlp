# Check: readable tests that use the factories

**Scope:** tests

## Rule

A test must be easy for a PLC programmer to read without knowing the code under test. Each test method:

1. **Has a doc comment** above its `METHOD` line, in the `(* ... *)` block. The comment states the behaviour under test and why it matters, not the steps. For example: "A header longer than T_MaxString is kept whole; W3C asks for at least 512 characters."
2. **Has a descriptive name** that says what should happen, in the `test<Behaviour>` form: `testCloneIsIndependent`, not `test3` or `testClone`. The name passed to `TcUnit.TEST('...')` must match the method name.
3. **Has assertion messages that say what was expected**, in the form `'Expected ...'`. A failure message must make sense on its own in the TcUnit log.
4. **Reads as arrange, act, assert.** Non-obvious steps get a short `//` comment, such as a byte-by-byte string build, a release that proves a copy is independent, or a deliberately invalid input. Magic numbers get a name or a comment, for example `16#301` → "sampled, remoteness known, remote".
5. **Builds objects through the factory or builder** whenever the production code offers one, instead of raw instantiation.

Raw instantiation means:

- `__NEW(FB_X(...))` or `__NEW(FB_X)` for a type that a factory or builder can produce
- a local FB instance with constructor arguments, used where a factory product is expected
- writing an object's fields or outputs directly to fake a state the factory would produce, for example `pSpan^.traceState := ...`

These are the factories and builders:

| Object | Factory or builder |
| --- | --- |
| Values: `FB_String`, `FB_Number`, `FB_KeyValue` and the other `FB_AnyValue` types; `FB_TraceId`, `FB_SpanId` | `ValueFactory` |
| `FB_SpanContext` | `ContextFactory.buildContext`, `FB_Span.getContext` |
| `FB_Link` | `LinkFactory.fromContext`, `LinkFactory.fromSpan` |
| `FB_TraceState` | `TraceStateFactory.parse`, `clone`, `truncate` |
| `FB_Span` | `FB_Tracer.startSpan(...)...build`, and `FB_Span.cloneTo` |
| `FB_LogRecord` | `FB_Logger.startLogRecord(...)...emit`, and `FB_LogRecord.cloneTo` |

Check `TcOtlp/otel/OTEL/` for factories added since this table was written. Grep for `PROGRAM .*Factory` and for methods named `build`, `create*`, `from*`, `clone*` or `cloneTo`.

## Why

- Tests are the living documentation of the contracts in CLAUDE.md. A reader who opens a test to learn how to build a span context must see the real way to do it.
- The factories own the invariants: validation, cloning, `pDest` must be 0, and allocation failure clean-up. A test that uses `__NEW` skips them. It can then pass against an object that production code could never create, and it will not notice when the factory changes.
- When a constructor signature changes, factory-based tests keep compiling. Tests that call `__NEW` directly all have to be edited, as happened when trace state moved to `FB_TraceState`.
- A TcUnit failure is only reported by its message. A message like `'failed'` or `'check 2'` forces the reader to open the source.

## What to look for

- **Missing or weak comments.** Any `METHOD test...` whose declaration has no `(* ... *)` block before `METHOD`. Also any whose comment only repeats the method name, or describes steps instead of behaviour.
- **Names.** A name that does not say the expected behaviour, or a `TcUnit.TEST('...')` string that differs from the method name.
- **Assertion messages.** Grep for `Assert` calls. Report messages that are empty, generic (`'ok'`, `'failed'`, `'check'`), duplicated within one method for different checks, or that don't say what was expected.
- **Unexplained values.** Hex flags, byte offsets, lengths such as `515` or `146`, and loop bounds with no name or comment.
- **Long methods without structure.** A test method over roughly 60 lines that runs several scenarios with no `//` section comments. It may need splitting, or at least headings.
- **Raw instantiation.** Grep the scope for `__NEW(`, and for local declarations of `FB_String(`, `FB_Number(`, `FB_KeyValue(`, `FB_Span`, `FB_SpanContext`, `FB_Link`, `FB_LogRecord(` and `FB_TraceState(`. Also look for direct writes to owned pointer fields or outputs: `.traceState :=`, `.status :=`, `.traceId :=`, `.spanId :=`, `.pBody :=`. For each hit, decide whether a factory or builder from the table could produce the same object.
- **Helpers.** The same checks apply to private helpers in test suites (`_expectRejected`, `_fillIds`) and to test doubles (`FB_Mock*`, `*_ForInspection`). Doubles also need a comment that says what they fake and why.

## Exceptions (do not report)

- **Tests of the factory or constructor itself**, for example `FB_Init` defaults, or a test that must build the object by hand to compare it with the factory's output.
- **Deliberately invalid or unreachable states** that the factory refuses to build, for example a span with no identity for `getContext`, or a queue test that only needs opaque nodes. They are allowed when a comment says why the factory is bypassed. Without that comment, report them as `review`.
- **Objects with no factory or builder that returns an owned pointer to the test.** For example, a queue test that needs a bare `FB_LogRecord` when the logger only hands records to a processor. Report these as `review`, naming the missing factory, instead of as a violation.
- **Statically wired components** that are declared, not allocated, in production too: providers, tracers, loggers, processors, exporters, serializers, queues, resources, scopes, id generators and their test doubles.
- **Stack inputs that a factory copies.** Plain locals such as `traceId: FB_TraceId` or a header `STRING`, passed by `ADR` to a factory that copies them (`ContextFactory.buildContext`, `TraceStateFactory.parse`). The factory still builds the object.
- **Vendor and library types**, such as JSON parser values and TcUnit types.

## Preferred structures

- A comment in the style of `FB_TestTraceState` and `FB_TestSpanContext`: one or two sentences saying the behaviour and why it matters.
- Arrange through factories: `TraceStateFactory.parse(pDest:=pTraceState, pHeader:=ADR(text))`, `ContextFactory.buildContext(...)`, `tracer.startSpan(...).build(pDest:=pSpan)`, `ValueFactory.createString(...)`.
- A named helper for repeated setup, such as `_fillIds` or `_fillLongHeader`, with its own comment.
- When bypassing a factory is necessary, a `//` comment on that line: "built by hand because the factory refuses ...".

## Severity

- **violation:**
  - a test method with no doc comment
  - `__NEW` or a field write that fakes an object a listed factory or builder could produce, with no comment saying why
  - a `TcUnit.TEST` name that does not match its method
- **review:**
  - weak or step-by-step comments
  - generic assertion messages
  - unexplained magic numbers
  - long unstructured methods
  - raw instantiation where no factory can currently produce the object
  - a bypass whose comment is present but unconvincing
