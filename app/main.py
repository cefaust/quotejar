from fastapi import FastAPI

from app.routers import quotes

app = FastAPI(title="QuoteJar API", version="0.1.0")

app.include_router(quotes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
