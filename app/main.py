from fastapi import FastAPI

from app.routers import auth, children, health, quotes

app = FastAPI(title="QuoteJar API", version="0.3.0")

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(children.router)
app.include_router(quotes.router)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    """A signpost for anyone who opens the bare URL.

    Every route in this API is namespaced -- /auth, /children, /quotes,
    /health -- so before this existed the root path returned 404. That is
    technically correct and reads as broken: a stranger handed the deployment
    URL sees {"detail":"Not Found"} and reasonably concludes the service is
    down rather than that they need a deeper path.

    Returns JSON rather than redirecting to /docs. A redirect would be
    friendlier to a browser and worse for everything else: API clients do not
    expect the root of an API to 302, health-checkers and uptime monitors
    follow redirects inconsistently, and a redirect gives a script no way to
    read the version. This payload is useful to both a human and a program.

    `version` reads from the FastAPI app rather than repeating the literal, so
    it cannot drift from the version reported in /openapi.json.
    """
    return {
        "name": app.title,
        "version": app.version,
        "docs": "/docs",
        "health": "/health/live",
    }


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
