from fastapi import FastAPI

from app.routers import auth, children, quotes

app = FastAPI(title="QuoteJar API", version="0.2.0")

app.include_router(auth.router)
app.include_router(children.router)
app.include_router(quotes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
