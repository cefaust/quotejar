# QuoteJar

Capture the funny things your kids say in under five seconds. At the end of
the year, the collection exports as a print-ready book.

Backend API: FastAPI + PostgreSQL 16, schema managed by Alembic.

## Requirements

- **macOS with [Homebrew](https://brew.sh)**
- **Python 3.12** — the `python3` that ships with macOS is 3.9, which is too
  old. The pinned dependencies will not install on it.
- **Docker Desktop**, installed and running

Install the toolchain:

    brew install python@3.12
    brew install --cask docker

Then launch Docker Desktop once and leave it running — the `docker` CLI cannot
talk to anything until the daemon is up.

Confirm you have the right versions before going further:

    python3.12 --version    # Python 3.12.x
    docker info             # must succeed, not "Cannot connect to the Docker daemon"

## Setup

### 1. Clone and configure

    git clone <repo-url>
    cd quotejar
    cp .env.example .env

Creating `.env` is **required, not optional**. `docker-compose.yml` reads
`POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` from it, and Compose
will start a broken database container if they are empty.

The committed defaults are for local development only. `POSTGRES_PASSWORD` is
literally `changeme`, and the database is published on `localhost:5432` — fine
on your own machine, never in a shared environment.

### 2. Create the virtualenv

Use `python3.12` explicitly. Plain `python3` resolves to macOS's 3.9 and the
install will fail with `No matching distribution found for alembic`:

    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

Every command below assumes this virtualenv is active. If you open a new
terminal tab, run `source .venv/bin/activate` again.

### 3. Start PostgreSQL

    docker compose up -d db

Wait for the health check to pass — migrations will fail against a database
that is still starting up:

    docker compose ps

Look for `Up (healthy)`, not `Up (health: starting)`. It typically takes about
ten seconds.

### 4. Apply the migrations

    alembic upgrade head

This runs from the host, not from inside a container: the API image ships only
the `app/` package and has no copy of Alembic or the migration scripts.

### 5. Seed a user and two children

The API has no endpoints for creating users or children yet, but every quote
needs a valid `child_id`:

    python -m scripts.seed

It prints the child IDs, which you will need to create quotes:

    Ada: 0d6d3637-...
    Bo:  73cb062d-...

The script is idempotent — running it twice will not create duplicates.

## Running

The API on the host, against the containerised database (best for development,
since `--reload` picks up your edits):

    docker compose up -d db
    uvicorn app.main:app --reload

Or the whole stack in Docker:

    docker compose up -d

Run one or the other, **not both** — they each bind port 8000, and the second
one will fail. Stop the host process with Ctrl-C, or the container with
`docker compose stop api`.

Either way the API is at http://localhost:8000, with interactive docs at
http://localhost:8000/docs

    curl http://localhost:8000/health
    # {"status":"ok"}

Note that `/health` reports only that the web process is running; it does not
check the database connection.

## Endpoints

| Method | Path          | Notes                                     |
| ------ | ------------- | ----------------------------------------- |
| POST   | /quotes       | 201 on success, 404 unknown child          |
| GET    | /quotes       | filter by child_id, paginate limit/offset  |
| GET    | /quotes/{id}  | 404 if missing or soft-deleted             |
| DELETE | /quotes/{id}  | 204, soft delete                           |

Creating a quote, using a child ID printed by the seed script:

    curl -X POST http://localhost:8000/quotes \
      -H 'Content-Type: application/json' \
      -d '{"child_id":"<child-id>","text":"I am not tired"}'

`said_on` is optional and defaults to the current date on the database server.
`text` is trimmed of surrounding whitespace, and blank or whitespace-only text
is rejected with a 422. Listings are ordered newest first by `said_on`, and
`limit` must be between 1 and 100.

## Tests

Create the test database once — the `db` container must be running:

    docker compose exec db psql -U quotejar -d quotejar -c "CREATE DATABASE quotejar_test;"

Then:

    pytest

Tests run against real PostgreSQL. The suite rebuilds the schema by running
the Alembic migrations, and each test runs inside a transaction that is rolled
back afterwards.

**`TEST_DATABASE_URL` must point at a throwaway database.** The suite begins by
dropping and recreating the `public` schema, so aiming it at your development
database would erase your data. The default in `.env.example` correctly points
at `quotejar_test`.

## Troubleshooting

**`No matching distribution found for alembic==1.18.5`** — the virtualenv was
built with macOS's Python 3.9. Delete it and rebuild with 3.12:

    rm -rf .venv && python3.12 -m venv .venv
    source .venv/bin/activate && pip install -r requirements.txt

**`Cannot connect to the Docker daemon`** — Docker Desktop is not running.
Launch it and wait for the whale icon in the menu bar to stop animating.

**Database container starts but immediately errors, or `role "" does not
exist`** — you skipped `cp .env.example .env`.

**`Bind for 0.0.0.0:5432 failed: port is already allocated`** — another
PostgreSQL is running, often one installed via Homebrew. Stop it with
`brew services stop postgresql@16`, or change the host port in
`docker-compose.yml` to `"5433:5432"` and update the ports in `.env` to match.

**`address already in use` on port 8000** — you are running both the host
`uvicorn` and the `api` container. Stop one.

**`failed to solve: DeadlineExceeded` when building the api image** — Docker
could not fetch the `python:3.12-slim` base image metadata, usually a slow
network or Docker Hub rate limiting. Retry, or pull the base image first:

    docker pull python:3.12-slim

**Migrations fail with a connection error** — the database is not healthy yet.
Check `docker compose ps` and wait for `Up (healthy)`.

### Starting over

To wipe the database and start clean:

    docker compose down -v
    docker compose up -d db
    # wait for healthy, then:
    alembic upgrade head
    python -m scripts.seed

## Notes

- Quotes are soft-deleted via `deleted_at`; reads exclude them.
- Foreign keys, the not-blank check on quote text, and the unique constraint
  on user email are enforced in PostgreSQL, not only in Python.
- Auth, the frontend, and book export are out of scope for QJ-1.
