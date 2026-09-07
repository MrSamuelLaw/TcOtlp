---
type: user-story
audience: developer
status: draft
---

# Developer User Stories


## US-DEV-004: ADS Shell Exporter for Development

**As a** TcOtlp developer  
**I want to** a "shell" exporter (`FB_OtlpShellExporter`) that accepts raw `FB_Otlp*` structures, internally serializes them to Proto-JSON, converts to string, and writes to the TwinCAT ADS log  
**So that** I can inspect OTLP data in the TwinCAT terminal during development without needing a running collector backend

### Acceptance Criteria
- [ ] `FB_OtlpShellExporter` exposes export methods only for top-level OTLP types (e.g., `ExportLogRecord`, `ExportSpan`) — not nested sub-structures
- [ ] Each export method accepts a pointer to the corresponding `FB_Otlp*`, calls its `F_Otlp*ToProtoJson` serializer, converts the JSON DOM to a string, and writes it to the ADS logger via `ADSLOGSTR`
- [ ] The exporter frees the dynamically allocated `FB_JsonDynDomParser` after writing so callers only pass the raw structure
- [ ] The exporter follows existing naming conventions (`FB_Otlp*`) and code structure
- [ ] Output is readable in the TwinCAT terminal (handles `ADSLOGSTR` length constraints)

## US-DEV-005: Nested and Composite Type Generation

**As a** TcOtlp developer  
**I want to** generate Structured Text types for nested OTLP messages (e.g., `Resource`, `InstrumentationScope`, `AnyValue`)  
**So that** top-level types like `FB_OtlpLogRecord` can reference fully generated sub-structures instead of leaving fields as TODOs

### Acceptance Criteria
- [ ] The code generator produces `FB_Otlp*` or `ST_Otlp*` types for nested protobuf messages referenced by top-level types
- [ ] Generated nested types follow the same naming conventions and field-mapping rules as top-level types (US-DEV-001)
- [ ] The corresponding `F_Otlp*ToProtoJson` serializer is generated for each nested type (US-DEV-003)
- [ ] Top-level types compose nested types as `VAR_INPUT` members, enabling recursive serialization

## US-DEV-006: Serialization Test Suite Generator

**As a** TcOtlp developer  
**I want to** generate TcUnit test suites for each `F_Otlp*ToProtoJson` serializer  
**So that** I can validate serialization correctness automatically instead of hand-writing round-trip tests for every type

### Acceptance Criteria
- [ ] For each generated serializer function, a corresponding `FB_<Name>SerializationTestSuite` is generated
- [ ] Each test suite populates an `FB_Otlp*` instance with known values, serializes it, and asserts the JSON DOM contains the expected fields and values
- [ ] Generated tests follow the existing TcUnit pattern (`EXTENDS FB_TestSuite`, `TcUnit.TEST` / `TcUnit.TEST_FINISHED`)
- [ ] Generated test suites are wired into `MAIN` so they run automatically with `TcUnit.RUN()`
