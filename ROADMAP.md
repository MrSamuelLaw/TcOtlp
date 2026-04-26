# Burn away the dross
The current step is to burn away the dross, which is another way of saying take what's good from the initial prototype and start working towards something production ready.
Now that I've had some time to think about it, the AI generated pipeline of taking a .proto file and auto generating structured text code is not opinionated enough for production.
One of the nice things about the OTLP specification is that it is flexible, however, that's only good for data, not developers.
Good design for end users makes it obvious how to hold the thing, so I'm going to reprogram this implementation from scratch and bake in my preferences because as a human with experience programming rather complex control loops and with a bit of experience in other programming languages, I know what feels natural. Building this by hand from scratch will give me a chance to confirm that what I'm building is easy to hold and its obvious how to use it. 
One of the things I want to do is make certain fields required, for example, service name, that way it will be obvious how to hold the thing.
Another thing I want to do is figure out how to get the attempt to free non-allocated memory to stop.

# Integrate with Ignition via OPCUA
Once the system is working at a basic level I want to establish control using function blocks that act as endpoints for ignition that will accept an optional trace id and a value.

# Start monitoring a real process
Once the software is ready for testing, find a potential incubator that will let me work on this in a non-critical production environment.