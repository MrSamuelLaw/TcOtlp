---
name: writing-tests
description: "Writes TcUnit test suites for the TcOtlp TwinCAT project. Use when asked to create tests, add test methods, or write test suites for Structured Text function blocks."
---

# Writing TcUnit Tests

Creates TcUnit test suites as TwinCAT Structured Text `.TcPOU` files for the TcOtlp project.

## Key Architecture Rules

### 1. MAIN Must Call `TcUnit.RUN()`

The test MAIN program (`TcOtlp/test/MAIN.TcPOU`) **must** contain `TcUnit.RUN();` in its Implementation body.
```xml
<Implementation>
  <ST><![CDATA[TcUnit.RUN_IN_SEQUENCE();]]></ST>
</Implementation>
```

### 2. Test Suites Extend `FB_TestSuite`

Every test suite is a `FUNCTION_BLOCK` that `EXTENDS FB_TestSuite`. The suite's Implementation block calls each test method:

```iec
THIS^.TestMyFirstTest();
THIS^.TestMySecondTest();
```

### 3. MAIN Declares Test Suite Instances

Each test suite must be instantiated as a variable in MAIN's `VAR` block. TcUnit auto-discovers `FB_TestSuite` instances — no explicit calls needed beyond the declaration:

```iec
PROGRAM MAIN
VAR
    myTestSuite: FB_MyTestSuite();
END_VAR
```

### 4. Every Test Method Uses the `TEST` Guard Pattern

Each test method **must** wrap its body in the `TcUnit.TEST('uniqueTestName') ... TcUnit.TEST_FINISHED();` guard. This is required by `RUN()` mode:

```iec
METHOD TestSomething
VAR
    // locals
END_VAR
---
IF TcUnit.TEST_ORDERED('Descriptive Test Name') THEN

// ... test logic and assertions ...

TcUnit.TEST_FINISHED();
```


## Test File Structure (`.TcPOU` XML)

Test suites live under `TcOtlp/test/TEST_OTEL/` in subdirectories matching the area under test. The file format is TwinCAT POU XML:

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_MyTestSuite" Id="{generate-a-guid}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_MyTestSuite EXTENDS FB_TestSuite
VAR_INPUT
END_VAR
VAR_OUTPUT
END_VAR
VAR
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[THIS^.TestFirst();
THIS^.TestSecond();]]></ST>
    </Implementation>
    <Method Name="TestFirst" Id="{generate-a-guid}">
      <Declaration><![CDATA[METHOD TestFirst
VAR
    // local variables for the test
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[IF TcUnit.TEST_ORDERED('Test First Thing') THEN

// arrange, act, assert

TcUnit.TEST_FINISHED();
END_IF]]></ST>
      </Implementation>
    </Method>
  </POU>
</TcPlcObject>
```

Each `<Method>` and `<POU>` `Id` attribute must be a unique GUID in `{xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}` format.

## Assertion Methods

Test methods call assertions via `THIS^.` (inherited from `FB_TestSuite`):

| Method | Usage |
|---|---|
| `AssertTrue(condition, 'message')` | Assert a BOOL is TRUE |
| `AssertFalse(condition, 'message')` | Assert a BOOL is FALSE |
| `AssertEquals_STRING(expected, actual, 'message')` | Compare two STRINGs |
| `AssertEquals_DINT(expected, actual, 'message')` | Compare two DINTs |
| `AssertEquals_UDINT(expected, actual, 'message')` | Compare two UDINTs |
| `AssertEquals_INT(expected, actual, 'message')` | Compare two INTs |
| `AssertEquals_BOOL(expected, actual, 'message')` | Compare two BOOLs |

## JSON Serialization Tests

For testing OTLP serialization, use `FB_JsonDynDomParser` from the Beckhoff JSON library:

1. Create the data model objects (e.g., `FB_OtlpLogsData`, `FB_OtlpLogRecord`).
2. Serialize via `SerializeToProtoJson(jsonDoc, root)`.
3. Navigate the JSON DOM with `FindMember`, `GetArrayValueByIdx`, `IsArray`, `IsObject`.
4. Assert field values with `GetString`, `GetInt`, `GetUint`, `GetUint64`.

### Memory Management Pattern

When test methods use pointer-based fields (e.g., `pBody`, `pValue`) that point to local stack variables, null them before the method exits to prevent `FB_exit` from calling `__DELETE` on stack addresses:

```iec
// Clean up: null out pointers to local stack vars
pLogRecord^.pBody := 0;
pAttr^.pValue := 0;
```

## Registering a New Test Suite

After creating a new test suite `.TcPOU` file:

1. **Add the instance to MAIN** — add a VAR declaration in `TcOtlp/test/MAIN.TcPOU`:
   ```iec
   myNewSuite: FB_MyNewTestSuite();
   ```
2. **Add the file to the project** — use the `importing-generated-code` skill or manually add a `<Compile>` entry in the `.plcproj` file.

## Checklist

- [ ] Test suite `EXTENDS FB_TestSuite`
- [ ] Each test method uses `IF TcUnit.TEST_ORDERED('...') THEN ... TcUnit.TEST_FINISHED(); END_IF`
- [ ] MAIN contains `TcUnit.RUN_IN_SEQUENCE();`
- [ ] Test suite instance declared in MAIN's VAR block
- [ ] Each XML element has a unique GUID `Id`
- [ ] Pointer-to-local-stack fields nulled before method exit
