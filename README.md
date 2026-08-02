# QuoteJar

Capture the funny things your kids say in under five seconds. At the end of
the year, the collection exports as a print-ready book.

Backend API: FastAPI + PostgreSQL 16.

## Requirements

- Python 3.11+
- Docker (for the PostgreSQL container)

## Setup

    git clone <repo-url>
    cd quotejar
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env

## Running

    uvicorn app.main:app --reload

The API is served at http://localhost:8000
Interactive docs: http://localhost:8000/docs

## Verifying it works

    curl http://localhost:8000/health
    # {"status":"ok"}
