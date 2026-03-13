# Developer User Stories

## US-DEV-001: Proto-to-Structured-Text Code Generation

**As a** TcOtlp developer  
**I want to** run a tool against `.proto` files that automatically generates the corresponding Structured Text function blocks, structs, and enums  
**So that** I don't have to manually translate protobuf definitions into ST code every time the spec changes

### Acceptance Criteria
- [ ] Protobuf `message` types generate `FUNCTION_BLOCK` declarations with `VAR_INPUT` members matching proto fields
- [ ] Protobuf `enum` types generate TwinCAT enum definitions
- [ ] Protobuf scalar types map to IEC 61131-3 types (e.g., `fixed64` → `ULINT`, `string` → `T_MaxString`, `uint32` → `UDINT`)
- [ ] Generated code follows existing naming conventions (`FB_Otlp*`, `E_Otlp*`)
- [ ] The tool can be re-run after a proto spec update to regenerate code

## US-DEV-002: Protobuf Parser and AST

**As a** TcOtlp developer  
**I want to** parse `.proto` files into an abstract syntax tree (AST)  
**So that** downstream code generators can consume a structured representation to produce Structured Text types and any serialization format (e.g., Proto-JSON, binary protobuf)

### Acceptance Criteria
- [ ] The parser reads `.proto` files and resolves `import` statements across the `opentelemetry-proto/` tree
- [ ] The AST captures `message` definitions including field name, field number, scalar type, and cardinality (`repeated`, `optional`)
- [ ] The AST captures `enum` definitions including variant names and integer values
- [ ] Cross-message references (e.g., `opentelemetry.proto.common.v1.AnyValue`) are resolved to their target AST node
- [ ] `reserved` field numbers and names are recorded so generators can skip them
- [ ] The AST is serialization-format-agnostic — it contains no Proto-JSON or ST-specific logic

## US-DEV-003: Proto-JSON Serializer Function Generator

**As a** TcOtlp developer  
**I want to** generate `F_Otlp*ToProtoJson` serializer functions from the protobuf AST  
**So that** every message type gets a correct Proto-JSON serializer automatically instead of being hand-written

### Acceptance Criteria
- [ ] For each `message` in the AST, the generator emits an `F_Otlp<Name>ToProtoJson` function that takes a `POINTER TO FB_Otlp<Name>` and returns `POINTER TO FB_JsonDynDomParser`
- [ ] Scalar fields serialize with the correct Proto-JSON encoding (e.g., `fixed64`/`uint64` as quoted strings via `AddUint64Member`, `uint32` as integer via `AddIntMember`, `string` via `AddStringMember`)
- [ ] Enum fields serialize as their string name (Proto-JSON enum representation)
- [ ] Nested message fields recurse by calling the corresponding generated `F_Otlp*ToProtoJson` function and embedding the result
- [ ] `repeated` fields serialize as JSON arrays, applying the correct element encoding (scalar, enum, or nested message)

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
