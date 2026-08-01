# Agent User Stories

## US-AGT-001: Local Trace-Guided Root Cause Analysis

**As a** coding agent with access to a developer's local workstation  
**I want to** ingest OTLP traces and logs exported from a running Beckhoff PLC (e.g., ADS shell exports, local log files, or Proto-JSON files on disk), correlate spans by `trace_id`, and identify the span or log record where an error or abnormal duration first appeared  
**So that** I can pinpoint the root cause of a process failure and suggest a fix in the Structured Text source code without the operator manually sifting through logs

### Acceptance Criteria
- [ ] The agent can parse Proto-JSON OTLP trace and log exports from the local filesystem (the same format produced by `F_Otlp*ToProtoJson`)
- [ ] Given a `trace_id`, the agent reconstructs the full span tree and highlights the span whose `status` is `ERROR` or whose duration exceeds a caller-defined threshold
- [ ] The agent maps `InstrumentationScope.name` back to the originating ST `PROGRAM` or `FUNCTION_BLOCK` in the codebase
- [ ] The agent produces a summary containing: faulting span name, duration, error status/message, relevant log records attached to that span, and a link to the source ST file
- [ ] The agent proposes at least one candidate code change (diff) in the identified ST source to address the failure

## US-AGT-002: System-Wide Trace Diagnostics via MCP

**As a** coding agent with MCP access to a system-wide OTLP backend (e.g., SigNoz)  
**I want to** actively query traces, logs, and metrics across all reporting PLCs, filter by error status or duration anomalies, and correlate failures across the full system  
**So that** I can proactively diagnose issues, identify cross-PLC dependencies, and suggest targeted fixes without anyone needing to export or hand me data

### Acceptance Criteria
- [ ] The agent can query the OTLP backend via MCP to retrieve traces by time range, service name, error status, or duration threshold
- [ ] The agent correlates spans across multiple PLCs reporting to the same backend to identify upstream/downstream failure relationships
- [ ] The agent detects recurring error patterns or performance degradation trends across a caller-defined time window
- [ ] The agent maps faulting spans back to source ST files and proposes candidate code changes (diffs) for each identified issue
- [ ] The agent produces a system-level summary distinguishing per-PLC issues from cross-PLC correlated failures

## US-AGT-003: Trace-Driven Automated Test Generation

**As a** coding agent with access to production OTLP trace and log data  
**I want to** analyze traces that captured real fault scenarios, extract the sequence of span inputs/outputs and error conditions, and generate TcUnit test cases that reproduce those scenarios  
**So that** regression test coverage grows automatically from real incidents without a developer manually writing each test

### Acceptance Criteria
- [ ] The agent can parse a trace containing an error or anomaly and extract the relevant span sequence, input values, and fault conditions
- [ ] The agent generates a valid TcUnit test case in Structured Text that sets up the identified preconditions and asserts the expected fault behavior
- [ ] The generated test case references the originating `trace_id` in a comment for traceability back to the production incident
- [ ] The agent avoids generating duplicate tests when the same fault pattern has already been covered by an existing test

## US-AGT-004: Operator Natural-Language Fault Query

**As a** coding agent accessible to plant operators via a chat interface  
**I want to** receive plain-English questions about process failures (e.g., "why did conveyor 3 stop?"), query the relevant OTLP traces and logs, and return a human-readable explanation with a timeline of events  
**So that** operators who are not programmers can diagnose issues without reading raw trace data or Structured Text source code

### Acceptance Criteria
- [ ] The agent accepts a natural-language question and maps it to the relevant service name, resource attributes, or span names in the OTLP data
- [ ] The agent returns a plain-English summary including: what happened, when it happened, what triggered it, and what was affected
- [ ] The agent presents a chronological timeline of the key spans and log records leading to the failure
- [ ] The agent avoids exposing raw Proto-JSON, span IDs, or source code details unless the operator explicitly asks for technical detail

## US-AGT-005: Predictive Maintenance from Span Duration Trends

**As a** coding agent with access to historical OTLP trace data  
**I want to** monitor span duration distributions over time, detect gradual degradation trends (e.g., a valve actuator span duration steadily increasing), and alert engineers before a hard failure occurs  
**So that** maintenance can be scheduled proactively instead of reactively after a process fault

### Acceptance Criteria
- [ ] The agent can query span durations for a given span name or service over a configurable historical time window
- [ ] The agent detects statistically significant upward trends in span duration that indicate mechanical or process degradation
- [ ] The agent generates an alert that includes: the degrading span name, the service/PLC it belongs to, the trend data, and a projected time-to-failure estimate if the trend continues
- [ ] The agent distinguishes genuine degradation from normal operational variance (e.g., load-dependent duration changes)

## US-AGT-006: Automatic Common-Cause Fault Resolution

**As a** coding agent with access to a knowledge base of past trace-to-fix mappings  
**I want to** identify a fault pattern that matches a previously diagnosed and successfully resolved incident, apply the known fix automatically, and log the intervention as its own OTLP span for auditability  
**So that** recurring common-cause failures are resolved without human intervention, reducing downtime

### Acceptance Criteria
- [ ] The agent maintains or queries a knowledge base that maps fault signatures (error status, span name, log message patterns) to verified fixes
- [ ] When a matching fault pattern is detected, the agent applies the fix (e.g., parameter adjustment, code patch) without waiting for human approval
- [ ] The agent emits an OTLP span recording its own intervention, including: the matched fault signature, the fix applied, and a before/after status
- [ ] The agent falls back to human notification when confidence in the match is below a configurable threshold

## US-AGT-007: Change Impact Analysis via Trace Comparison

**As a** coding agent with access to OTLP trace data from before and after a Structured Text code deployment  
**I want to** compare trace shapes (span trees, durations, error rates) across the two periods and flag behavioral regressions or unexpected side effects  
**So that** engineers can validate deployments with data-driven evidence and catch regressions before they cause production incidents

### Acceptance Criteria
- [ ] The agent accepts a deployment timestamp or version tag and partitions trace data into "before" and "after" windows
- [ ] The agent compares span tree structures and flags new, removed, or reordered spans introduced by the deployment
- [ ] The agent compares span duration distributions and error rates, flagging statistically significant changes
- [ ] The agent produces a deployment impact report summarizing: what changed, what regressed, what improved, and a recommendation to keep or roll back

## US-AGT-008: Cross-System Architecture Discovery

**As a** coding agent with access to a system-wide OTLP backend  
**I want to** build a live system topology map from observed trace data — identifying which PLCs communicate, shared resources, timing dependencies, and call hierarchies  
**So that** engineers always have an accurate, up-to-date architecture diagram without maintaining documentation manually

### Acceptance Criteria
- [ ] The agent constructs a directed graph of service-to-service relationships from parent/child span links across PLCs
- [ ] The agent identifies shared resources (e.g., common downstream equipment or databases) referenced by multiple services
- [ ] The agent detects timing dependencies where one PLC's span consistently follows another's, indicating a sequential process relationship
- [ ] The agent outputs the topology as a Mermaid diagram or equivalent visual format that can be embedded in project documentation
