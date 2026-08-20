A control variable is used as the access point for users to manipulate values of data type REAL from SCADA systems.

The function block must constrain the value between a min and max value (inclusive) and MUST log failed write attempts IF a logger is associated with the control variable.

## Properties
`bytes: ARRAY [0..23] OF BYTE` The point where data is packed and written to from SCADA. the first for bytes is to be interpreted as a __bit__ array used for flags, with the least significant bit being true on the scan that the data is processed in and then reset on the following scan. All other bits or reserved. The second for bytes are to be interpreted as the REAL value, and the last 16 bytes are reserved for the traceId.

`cv: REFERENCE TO REAL` the control variable to be updated when the internal buffer changes. This variable should be passed in as a reference.