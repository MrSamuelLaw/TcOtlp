# Proto Parser & AST Specification

**Relates to**: [US-DEV-002](../user_stories/developer_userstories.md#us-dev-002-protobuf-parser-and-ast)  
**Consumers**: Structure Generator (US-DEV-001), Serializer Generator (US-DEV-003), Test Generator (US-DEV-006)

---

## 1. Overview

The parser reads `.proto` files from the `opentelemetry-proto/` tree, resolves imports, and produces a **format-agnostic AST** that downstream generators consume to emit Structured Text code. The AST contains no ST- or Proto-JSON-specific logic.

## 2. Scope

### In Scope

| Proto Feature | Notes |
|---|---|
| `syntax` declaration | Must be `"proto3"` — parser rejects proto2 files |
| `package` declaration | Stored on the file node; used to build fully-qualified names |
| `import` statements | Resolved relative to the `opentelemetry-proto/` root |
| `message` definitions | Including nested messages |
| `enum` definitions | Including nested enums inside messages |
| `oneof` groups | Captured as a distinct node grouping child fields |
| `repeated` fields | Cardinality recorded on the field node |
| `optional` fields | Cardinality recorded on the field node |
| `reserved` declarations | Field numbers and names recorded for generators to skip |
| Scalar types | `double`, `float`, `int32`, `int64`, `uint32`, `uint64`, `sint32`, `sint64`, `fixed32`, `fixed64`, `sfixed32`, `sfixed64`, `bool`, `string`, `bytes` |
| Message-typed fields | Cross-file references resolved to their target AST node |
| Field numbers | Stored on each field node |
| Comments | Leading doc-comments captured on the parent node (optional, for future use) |

### Out of Scope

| Proto Feature | Reason |
|---|---|
| `service` / `rpc` definitions | TcOtlp uses HTTP export, not gRPC |
| `option` declarations | Language-specific options (`java_package`, `go_package`, etc.) are irrelevant to ST generation |
| `extend` / `extensions` | Not used in the OTLP proto tree |
| `map<K,V>` fields | Not used in the OTLP proto tree |
| Proto2 `required` / `group` | Only proto3 files are in scope |

## 3. AST Node Types

### 3.1 `ProtoFile`

Root node produced per `.proto` file.

```
ProtoFile
├── syntax: string                  // "proto3"
├── package: string                 // e.g. "opentelemetry.proto.logs.v1"
├── imports: string[]               // relative paths, e.g. "opentelemetry/proto/common/v1/common.proto"
├── messages: MessageNode[]
└── enums: EnumNode[]
```

### 3.2 `MessageNode`

Represents a `message` definition.

```
MessageNode
├── name: string                    // e.g. "LogRecord"
├── fullName: string                // e.g. "opentelemetry.proto.logs.v1.LogRecord"
├── fields: FieldNode[]
├── oneofs: OneofNode[]
├── nestedMessages: MessageNode[]   // messages declared inside this message
├── nestedEnums: EnumNode[]         // enums declared inside this message
├── reservedNumbers: int[]          // e.g. [4, 1000]
├── reservedNames: string[]         // e.g. ["old_field"]
└── comment: string | null          // leading doc-comment
```

### 3.3 `FieldNode`

Represents a single field inside a message or oneof.

```
FieldNode
├── name: string                    // proto field name, e.g. "severity_number"
├── number: int                     // field number, e.g. 2
├── type: FieldType                 // see §3.6
├── cardinality: Cardinality        // SINGULAR | REPEATED | OPTIONAL
└── comment: string | null
```

### 3.4 `OneofNode`

Groups mutually-exclusive fields (e.g., `AnyValue.value`).

```
OneofNode
├── name: string                    // e.g. "value"
└── fields: FieldNode[]             // the choices
```

### 3.5 `EnumNode`

Represents an `enum` definition.

```
EnumNode
├── name: string                    // e.g. "SeverityNumber"
├── fullName: string                // e.g. "opentelemetry.proto.logs.v1.SeverityNumber"
├── values: EnumValueNode[]
└── comment: string | null
```

```
EnumValueNode
├── name: string                    // e.g. "SEVERITY_NUMBER_INFO"
├── number: int                     // e.g. 9
└── comment: string | null
```

### 3.6 `FieldType` (Discriminated Union)

A field's type is one of:

| Variant | Data | Example |
|---|---|---|
| `Scalar` | `scalarType: ScalarType` | `string`, `fixed64`, `uint32` |
| `MessageRef` | `fullName: string`, `resolvedNode: MessageNode` | `"opentelemetry.proto.common.v1.AnyValue"` |
| `EnumRef` | `fullName: string`, `resolvedNode: EnumNode` | `"opentelemetry.proto.logs.v1.SeverityNumber"` |

`ScalarType` is an enum of all proto3 scalar types:
`double | float | int32 | int64 | uint32 | uint64 | sint32 | sint64 | fixed32 | fixed64 | sfixed32 | sfixed64 | bool | string | bytes`

### 3.7 `Cardinality` Enum

```
SINGULAR    // default proto3 field (implicit presence in proto3)
REPEATED    // "repeated" keyword
OPTIONAL    // "optional" keyword (explicit presence)
```

## 4. Parsing Pipeline

```
  ┌──────────────┐     ┌───────────────┐     ┌────────────────┐     ┌──────────────┐
  │  Discover    │     │  Lex + Parse   │     │  Resolve       │     │  Validated   │
  │  .proto      │────▶│  each file     │────▶│  cross-file    │────▶│  AST         │
  │  files       │     │  into AST      │     │  references    │     │              │
  └──────────────┘     └───────────────┘     └────────────────┘     └──────────────┘
```

### 4.1 Discovery

- Input: a root `.proto` file path (or list of paths)
- The parser follows `import` statements transitively, resolving paths relative to a configurable import root (defaults to `opentelemetry-proto/`)
- Each file is parsed at most once (tracked by resolved path)

### 4.2 Lexing & Parsing

The parser reads each `.proto` file and produces an unresolved AST:

1. Validate `syntax = "proto3";` — reject anything else
2. Extract `package` declaration
3. Collect `import` paths
4. Parse `message` definitions (recursively for nested messages/enums)
   - For each field: extract name, number, type name (as raw string), cardinality
   - For `oneof` blocks: group fields under a `OneofNode`
   - For `reserved` statements: collect numbers and names
5. Parse `enum` definitions — extract name, values with numbers

At this stage, `MessageRef` and `EnumRef` field types store only the raw type string (e.g. `"opentelemetry.proto.common.v1.AnyValue"` or `"SeverityNumber"`), with `resolvedNode` unset.

### 4.3 Reference Resolution

After all files are parsed, a resolution pass links every unresolved type reference to its target node:

1. Build a global symbol table: `fullName → MessageNode | EnumNode`
2. For each `FieldNode` whose type is a raw string:
   - Look up the string in the symbol table (try fully-qualified first, then relative to the current package)
   - Determine whether the target is a `MessageNode` or `EnumNode`
   - Replace the raw string with the appropriate `MessageRef` or `EnumRef` variant, setting `resolvedNode`
3. Any unresolved reference is a **fatal error** — the parser reports the field location and the missing type name

### 4.4 Validation

After resolution, the parser performs final checks:

- No duplicate field numbers within a message (including across `oneof` groups)
- No duplicate enum value numbers within an enum (proto3 allows aliases with `allow_alias`, but OTLP doesn't use this — warn if encountered)
- All `reserved` numbers/names are not reused by active fields
- All files parsed successfully (no I/O or syntax errors)

## 5. Error Handling

| Error Class | Behavior |
|---|---|
| File not found (import) | Fatal — report missing path and the importing file |
| Syntax error | Fatal — report file, line number, and context |
| Unresolved type reference | Fatal — report field location and missing type name |
| Duplicate field number | Fatal — report both fields |
| Proto2 syntax | Fatal — report file |
| Out-of-scope features (`service`, `map`, etc.) | Warning — skip and continue |

## 6. Example Walkthrough

Given `logs.proto` as input:

1. **Discover**: `logs.proto` imports `common.proto` and `resource.proto`; `resource.proto` imports `common.proto` (already seen — skip)
2. **Parse `common.proto`**: produces `MessageNode("AnyValue")` with `OneofNode("value")` containing 8 fields, `MessageNode("KeyValue")`, `MessageNode("InstrumentationScope")`, `EnumNode` (none in common.proto)
3. **Parse `resource.proto`**: produces `MessageNode("Resource")` with a `repeated` field typed as raw string `"opentelemetry.proto.common.v1.KeyValue"`
4. **Parse `logs.proto`**: produces `MessageNode("LogRecord")` with fields including `severity_number` typed as raw string `"SeverityNumber"`, `body` typed as `"opentelemetry.proto.common.v1.AnyValue"`, and `EnumNode("SeverityNumber")`, `EnumNode("LogRecordFlags")`
5. **Resolve**: `"SeverityNumber"` → resolves within same package to `EnumRef(opentelemetry.proto.logs.v1.SeverityNumber)`. `"opentelemetry.proto.common.v1.AnyValue"` → resolves to `MessageRef` pointing at the `AnyValue` node from `common.proto`.
6. **Validate**: `LogRecord` has `reserved 4` — confirm no active field uses number 4. `ResourceLogs` has `reserved 1000` — confirm no active field uses number 1000. Pass.

## 7. Open Questions

1. **Implementation language** — Python? PowerShell? Node.js? Should align with the structure generator tooling choice.
2. **Serialization of the AST** — Should the parser output a JSON representation of the AST for generator consumption, or should generators import the parser as a library?
3. **Incremental parsing** — Is full re-parse acceptable on every run, or do we need caching? (Likely full re-parse is fine given the small proto tree.)
4. **`oneof` handling in ST** — How should `oneof` map to Structured Text? This is a generator concern but may influence what metadata the AST captures.
