- Hooking into update life cycles is difficult because loggers cannot own processors and the update functions most occur asynchronously of the twincat RPC
- Devices such as allen bradly PLC's cannot pass data via opc RPC calls.
- It's likely better to provide both methods for updating a PLC value.
	- Option A: Update a packed array of fixed length.
		- Pros: 
			- This would also work with cyclical data.
			- A simple library would enable users to write values and log what happens to them pretty easily.
		- Cons:
			- One way, no feedback to the client if/why a failure occured.
	- Option B: Update using an OPC remote procedure call (RPC).
		- Pros:
			- Would work as part of a standard OPC standard.
			- Gives users the opportunity to provide feedback to the client.
		- Cons:
			- Does not work with cyclical data.

I'm thinking long term there can be two methods:

`updateFromBytes(bytes: ARRAY[0..24] OF BYTES) -> (success: BOOL, failureReason: E_FailureReason)`
This method would be used to update the value using cyclical data.

`updateFromOpc(value: T, traceId: ARRAY[0..16] OF BYTES) -> (success: BOOL, failureReason: E_FailureReason)
This method would be used to update the value using an opc RPC and could directly return the failure reason to the client.

Both methods would need a mechanism to persist the failure reason until the next time the control var body was called, then a log record could be emitted automatically.
