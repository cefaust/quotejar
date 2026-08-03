# QuoteJar

Capture the funny things your kids say in under five seconds. At the end of
the year, the collection exports as a print-ready book.

Backend API: FastAPI + PostgreSQL 16, schema managed by Alembic.

## Requirements

- Python 3.11+
- Docker

## Setup

    git clone <repo-url>
    cd quotejar
    cp .env.example .env

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

Start PostgreSQL and wait for it to report healthy:

    docker compose up -d db
    docker compose ps

Apply the migrations:

    alembic upgrade head

Insert a user and two children so the quote endpoints have something to
reference (the API does not yet create these):

    python -m scripts.seed

## Running

Whole stack in Docker:

    docker compose up -d

Or the API on the host against the containerised database:

    docker compose up -d db
    uvicorn app.main:app --reload

Either way: http://localhost:8000 — interactive docs at /docs

    curl http://localhost:8000/health
    # {"status":"ok"}

## Endpoints

| Method | Path          | Notes                                    |
| ------ | ------------- | ---------------------------------------- |
| POST   | /quotes       | 201 on success, 404 unknown child        |
| GET    | /quotes       | filter by child_id, paginate limit/offset|
| GET    | /quotes/{id}  | 404 if missing or soft-deleted           |
| DELETE | /quotes/{id}  | 204, soft delete                         |

## Tests

Create the test database once:

    docker compose exec db psql -U quotejar -d quotejar -c "CREATE DATABASE quotejar_test;"

Then:

    pytest

Tests run against real PostgreSQL. The suite rebuilds the schema by running
the Alembic migrations, and each test runs inside a transaction that is rolled
back afterwards.

## Notes

- Quotes are soft-deleted via `deleted_at`; reads exclude them.
- Foreign keys, the not-blank check on quote text, and the unique constraint
  on user email are enforced in PostgreSQL, not only in Python.
- Auth, the frontend, and book export are out of scope for QJ-1.
