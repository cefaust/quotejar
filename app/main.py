from fastapi import FastAPI

from app.routers import auth, children, health, quotes

app = FastAPI(title="QuoteJar API", version="0.3.0")

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(children.router)
app.include_router(quotes.router)


@app.get("/health", tags=["health"])
def health_legacy() -> dict[str, str]:
    """Kept as an alias for liveness.

    QJ-1 and QJ-2 documented `/health` and anything already pointed at it --
    a script, a bookmark, an old probe config -- keeps working. It maps to
    liveness rather than readiness because that is what it always was: it
    never checked the database, so callers relying on it are relying on
    liveness semantics whether they knew it or not. Silently upgrading it to
    check the database would change its meaning for every existing caller.

    New probes should use /health/live or /health/ready explicitly, which say
    what they mean.
    """
    return {"status": "ok"}
