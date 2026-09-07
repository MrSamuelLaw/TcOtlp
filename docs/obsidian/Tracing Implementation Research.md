---
type: research
domain: tracing
status: draft
---

**When to use links/children**
- Links are used to communicate spans that occur sequentially
- Parent/Child relation ships are for spans where the parent overlaps the child completely.

In the example below we see both. The "manufacturing-process" span is the parent of the other spans as it will begin before the child spans and end after the child spans.
The "step-a" span and "step-b" span use a link because they occur sequentially and step-a has no overlap with step-b.

![[Pasted image 20260830061755.png]]

example code for tracing in the plc

```
=== VARS ===
VAR
	tracer: FB_Tracer(scope, tracerProvider);
	logger: FB_Logger(scope, loggerProvider); 
	rootSpan: POINTER TO FB_Span;
	ctx: POINTER TO FB_SpanContext;
	link: POINTER TO FB_Link;
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
			// this is a ton of code for the simple act of starting a subsequent span. I'm thinking that there should be a utility method like tracer.handoffSpan('next-span-name', currentSpan)
			IF currentSpan <> 0 THEN
				currentSpan.setStatusOk();
				currentSpan.getContext(ctx);
				IF ctx <> 0 THEN 
					LinkFactory.fromContext(ctx, link)
				END_IF
				tracer.endSpan(currentSpan);
				IF link <> 0 THEN
					tracer.startSpan('step2Span', currentSpan, ctx=ctx)
					currentSpan.addLink(link)
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



