"""Lambda entry point.

Mangum adapts the ASGI application to Lambda's event model. FastAPI speaks
ASGI: it expects a scope dict, a receive callable, and a send callable. Lambda
speaks JSON: it hands a function an event dict and a context object. Mangum
sits between them, translating a Function URL event into an ASGI scope,
running the app, and converting the ASGI response back into the JSON shape
Lambda returns.

No application code changes to accommodate this. app/main.py is the same
FastAPI instance that uvicorn serves locally and that the container served
before this ticket -- which is the point of ASGI being an interface rather
than a framework detail. The same app object can run under uvicorn, under
Mangum, under hypercorn, or in tests via TestClient, and none of them require
it to know which.

Everything at module scope in this file and its imports runs once per cold
start. `from app.main import app` transitively imports app.config -- which
fetches secrets from Secrets Manager -- and app.db, which builds the
SQLAlchemy engine. Both therefore happen once per container, not once per
request. That placement is deliberate; see the comments in those modules.
"""

from mangum import Mangum

from app.main import app

# lifespan="off" rather than Mangum's "auto" default.
#
# ASGI lifespan is the startup/shutdown protocol -- the hook where a server
# would open connection pools on boot and drain them on exit. That model does
# not fit Lambda. There is no clean shutdown signal: an idle container is
# frozen and later discarded without notice, so a shutdown handler is not
# reliably called and anything depending on it is a leak waiting to happen.
#
# QuoteJar registers no lifespan handlers, so running the protocol would only
# add work to every cold start. Turning it off also avoids a class of
# confusing failure where an exception inside a lifespan handler surfaces as
# an opaque Lambda error rather than a stack trace.
#
# The engine is created at import instead, which achieves what a startup hook
# would have, at the same moment, without the protocol.
handler = Mangum(app, lifespan="off")
