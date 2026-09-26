---
type: research
domain: tracing
status: draft
---

**When to use links/children**
- Parent/Child relationships are for spans where the parent overlaps the child completely.
- Sequential children of the same parent are siblings. The parent already groups them and their timestamps already order them, so they are not linked to each other.
- Links are for causal relationships the tree cannot express, usually across traces: a span started by an upstream caller's request, or a batch span that gathers work from several traces.

In the example below, the "manufacturing-process" span is the parent of the other spans as it will begin before the child spans and end after the child spans.
The "step-a" span and "step-b" span are sibling children of it. step-b follows step-a, which their timestamps show, so no link joins them.

![[Pasted image 20260830061755.png]]

example code for tracing in the plc

```
=== VARS ===
VAR
	tracer: FB_Tracer(scope, tracerProvider);
	logger: FB_Logger(scope, loggerProvider); 
	rootSpan: POINTER TO FB_Span;
	ctx: POINTER TO FB_SpanContext;
	currentSpan := POINTER TO FB_Span;
	processInit: BOOL;
	currentStep: UINT := 0;
END_VAR

=== PROG ===


CASE currentStep OF
	0:
		IF processInit THEN
			IF tracer.startSpan('rootSpan', rootSpan, ctx:=0) THEN
				IF rootSpan.getContext(ctx) THEN
					// ctx would need to be VAR_IN_OUT so it could be zeroed out
					tracer.startSpan('step1Span', currentSpan, ctx=ctx);
				END_IF
			END_IF
			currentStep := currentStep + 1;
		END_IF
	1:
		IF step1Done THEN
			IF currentSpan <> 0 THEN
				currentSpan.setStatusOk();
				tracer.endSpan(currentSpan);
				// step2 is a sibling of step1 under the root span, not linked to it
				rootSpan.getContext(ctx);
				IF ctx <> 0 THEN
					tracer.startSpan('step2Span', currentSpan, ctx=ctx)
				END_IF
			END_IF
			currentStep := currentStep + 1;
		END_IF
	2:
		IF step2Done THEN
			IF currentSpan <> 0 THEN
				tracer.endSpan(currentSpan);
				tracer.endSpan(rootSpan);
			END_IF
			currentStep := 0;
		END_IF
		
END_CASE

IF motorTemp > motorTempLimit THEN
	processInit := FALSE;
	logger
		.startLogRecord(ERROR)
		.setEventName('motor.overTempError')
		.setBody('motor over temp limit, initiating auto shutdown')
	IF currentSpan <> 0 THEN
		span.setStatusError('Failed with motor over temp fault')
		logger.setSpanData(currentSpan);
		tracer.end(currentSpan);
		tracer.end(rootSpan);
	END_IF
	logger.emit()
	currentStep := 0;
END_IF

	
processInit := FALSE;



