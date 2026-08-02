The `FB_LoggerProvider` is the root entity used to access all other entities for the logging domain aggregate. The Logger Provider must maintain a lookup table of names and loggers so as to perform the following functions.
- Create a Logger - Creating a logger with a valid instrumentation scope. If the logger instantiation fails the provider MUST provide a way to inform the caller of the failure.  
- Get Loggers - Get a logger using same name used to create the logger. If the name does not exist in the lookup table the provider MUST return a no-op logger instance that has "dummy methods" that don't have any effect but implement the logger interface.
- Remove Loggers - Remove loggers from the lookup table by name. If the logger does not exist the method SHOULD return a status indicating success. 


## The FB_LoggerProvider methods:

### createLogger
parameters:
- `name: T_MaxString` - The name of the logger. IFF the name IS NOT already associated with a logger FB_LoggerProvider MUST instantiate a new `FB_Logger` instance and append it to the lookup table using the `name` attribute. IFF the name IS already associated with a logger the FB_LoggerProvider MUST return a status indicating that the operation failed due to an attempted duplicate entry
- `version: T_MaxString` - The version of the logger

### getLogger
parameters:
- `name: T_MaxString` - The name of the logger. IFF the name IS NOT already in the lookup table the singleton no-op logger MUST be returned.

### destroyLogger
parameters:
- `name: T_MaxString` - The name of the logger to remove. IFF the name IS NOT already in the lookup table return a status indicating success. 