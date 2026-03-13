# Engineering User Stories

## US-ENG-001: Ask AI Why My Loop Won't Tune

**As a** controls engineer  
**I want to** see PLC-level trace data (setpoints, process variables, output signals, and timing) for a control loop collected automatically and sent to an OTLP backend  
**So that** I can point an AI agent at the trace data and ask "why won't this loop hold setpoint?" instead of manually sifting through trend logs and guessing

## US-ENG-002: Understand What Happened Before a Trip

**As a** controls engineer  
**I want to** get an ordered trace of every span and event leading up to a fault or safety trip  
**So that** I can ask an AI agent "what caused this trip?" and get a clear causal chain instead of correlating timestamps across multiple SCADA screens

## US-ENG-003: Compare Equipment Performance

**As a** mechanical engineer  
**I want to** query trace data across identical equipment (e.g., "compare pump A and pump B run profiles over the last week")  
**So that** I can spot the one that's degrading and schedule maintenance before it fails, without standing in front of each unit with a clipboard

## US-ENG-004: Validate Commissioning Against Design Intent

**As a** controls engineer  
**I want to** capture trace data during commissioning of new equipment (valve stroke times, motor ramp profiles, sensor response)  
**So that** I can hand the traces to an AI agent and ask "does this match the design spec?" instead of manually checking each parameter against a spreadsheet

## US-ENG-005: Get a Plain-English Shift Summary

**As a** a facility engineer  
**I want to** ask an AI agent "what happened on night shift?" and get a summary built from OTLP trace and log data  
**So that** I don't have to rely solely on operator notes or dig through alarm histories to understand what the plant did overnight
