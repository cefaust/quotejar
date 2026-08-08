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

`JWT_SECRET` is the same story, only worse. It signs every access token, so
anyone who knows it can forge a token for any account — one stolen secret
compromises every user at once, where a stolen password compromises one.
Generate your own before this runs anywhere real:

    python -c "import secrets; print(secrets.token_urlsafe(32))"

It has no default and must be at least 32 characters, so the app refuses to
start rather than booting with a weak or missing one.

### 2. Create the virtualenv

Use `python3.12` explicitly. Plain `python3` resolves to macOS's 3.9 and the
install will fail with `No matching distribution found for alembic`:

    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements-dev.txt

Note `requirements-dev.txt`, not `requirements.txt`. The two are split
because the production image installs `requirements.txt` only:

| File | Contents | Used by |
| ---- | -------- | ------- |
| `requirements.txt` | what the running app imports | the Docker image, and pulled in by the dev file |
| `requirements-dev.txt` | the above plus pytest and the httpx test client | you, locally |

Installing `requirements.txt` alone leaves you without pytest. Shipping
`requirements-dev.txt` would put a test runner in production, which is code an
attacker can reach and no user benefits from.

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

### 5. Seed a user and two children (optional)

The API creates everything it needs on its own — `POST /auth/register` for an
account, `POST /children` for a child. This script is a shortcut: it hands you
a ready-made account with two children already attached, so you can start
exercising the authenticated endpoints immediately instead of making three
calls first.

    python -m scripts.seed

It prints the child IDs, which you need in order to create quotes:

    Ada: 0d6d3637-...
    Bo:  73cb062d-...

The seeded account is `parent@example.com`, password `seed-password-dev-only`.
The script is idempotent — running it twice will not create duplicates.

If you seeded *before* applying the QJ-2 migration, that account cannot log
in: the migration backfilled pre-existing users with an unusable credential,
and there is no password reset. Wipe and re-seed — see [Starting
over](#starting-over).

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

Everything except `/health`, `/auth/register`, and `/auth/login` requires a
bearer token.

| Method | Path            | Auth | Notes                                       |
| ------ | --------------- | ---- | ------------------------------------------- |
| POST   | /auth/register  | —    | 201, JSON body, 409 if the email is taken   |
| POST   | /auth/login     | —    | 200 + token, **form-encoded**, 401 on failure |
| GET    | /auth/me        | ✓    | the authenticated user                       |
| POST   | /children       | ✓    | 201, owned by the caller                     |
| GET    | /children       | ✓    | the caller's children only                   |
| GET    | /children/{id}  | ✓    | 404 if missing **or not yours**              |
| POST   | /quotes         | ✓    | 201, 404 if the child isn't yours            |
| GET    | /quotes         | ✓    | filter by child_id, paginate limit/offset    |
| GET    | /quotes/{id}    | ✓    | 404 if missing, soft-deleted, or not yours   |
| DELETE | /quotes/{id}    | ✓    | 204, soft delete                             |

### Getting a token

Register, then log in. Note that login takes
`application/x-www-form-urlencoded` and the email goes in a field named
`username` — both inherited from `OAuth2PasswordRequestForm`, and neither
renameable. It is the only endpoint in the API that is not JSON.

    curl -X POST http://localhost:8000/auth/register \
      -H 'Content-Type: application/json' \
      -d '{"email":"you@example.com","password":"correct-horse-battery"}'

    curl -X POST http://localhost:8000/auth/login \
      -d 'username=you@example.com&password=correct-horse-battery'
    # {"access_token":"eyJhbGci...","token_type":"bearer"}

Then create a child and a quote:

    TOKEN=<paste access_token>

    curl -X POST http://localhost:8000/children \
      -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' -d '{"name":"Ada"}'

    curl -X POST http://localhost:8000/quotes \
      -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' \
      -d '{"child_id":"<child-id>","text":"I am not tired"}'

In Swagger at `/docs`, the **Authorize** button does all of this for you.

`said_on` is optional and defaults to the current date on the database server.
`text` is trimmed of surrounding whitespace, and blank or whitespace-only text
is rejected with a 422. Listings are ordered newest first by `said_on`, and
`limit` must be between 1 and 100. Passwords are 8 to 72 **bytes** — accented
characters and emoji count as more than one, because that is bcrypt's limit.

### Why another user's resource returns 404

Requesting a quote or child that exists but belongs to someone else returns
`404 Not Found`, not `403 Forbidden`. 403 is the more honest answer, but the
two statuses are different answers to "does this id exist?", which lets an
unauthorised caller confirm real ids from status codes alone without ever
seeing content. Both cases answer 404 so they cannot be told apart.

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
    source .venv/bin/activate && pip install -r requirements-dev.txt

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
- Passwords are hashed with bcrypt, which is deliberately slow — roughly
  305,000× slower than SHA-256 on the same machine. That is the point: the
  threat is offline cracking after a database dump, where no rate limit
  applies, and slowness turns an afternoon's work into months.
- Ownership runs quote → child → user. Quotes carry no `user_id` of their own,
  so scoping is a join, and every quote query starts from one shared
  ownership-filtered select rather than each handler remembering to add the
  check.
- The frontend and book export remain out of scope.

## Known gaps

Deliberately not built. Each is a real omission rather than an oversight, and
the reasoning matters more than the list.

**Refresh tokens.** Access tokens live 30 minutes and cannot be revoked —
logging out, changing a password, or deleting an account does not invalidate
a token already issued. Expiry is the only revocation mechanism, which is why
the window is short. The standard fix pairs a short access token with a
long-lived refresh token stored server-side, which *can* be revoked. That
requires token storage and a rotation scheme.

**Password reset.** There is no way back into an account whose password is
lost. This also means the accounts that predate QJ-2 — anything the seed
script created before the migration — are permanently locked out, since the
migration backfilled them with an unusable credential. Acceptable for a
fixture, not for real users.

**Email verification.** Registration accepts any well-formed address without
confirming the registrant controls it. This is also why registration leaks:
`409` on a duplicate confirms an address is registered, which is a
user-enumeration oracle. Closing it means accepting every signup and sending
either a welcome or a "someone tried to register your address" notice, so the
browser learns nothing — which needs email delivery first. Login does not
have this excuse and does not leak: both failure modes return byte-identical
responses, and login runs bcrypt even for unknown addresses so response
timing cannot distinguish them either.

**Rate limiting.** Nothing throttles `/auth/login`, so online password
guessing is bounded only by bcrypt's ~230 ms per attempt. That is a real
speed bump — a few hundred guesses a minute rather than millions — but it is
a side effect of the hashing cost, not a deliberate control. Registration is
likewise unthrottled, so the endpoint can be used to create accounts in bulk.

**OAuth / social login.** No third-party identity providers. Worth being
precise here, because the code uses `OAuth2PasswordRequestForm` and that
invites overclaiming: this borrows the OAuth2 password-grant *request shape*
so FastAPI's tooling works — the Authorize button, `OAuth2PasswordBearer`,
the documented dependency path. There is no authorisation server, no client
registration, no consent screen, no delegation. The password grant is in fact
deprecated in OAuth 2.1. This is not an OAuth2 implementation.

Two more, noted while building:

**No denormalised `quotes.user_id`.** Scoping joins through `children`, which
is correct and cannot drift, but the list query's `ORDER BY said_on DESC
LIMIT 20` still sorts every matching row before discarding all but 20. A
`user_id` column with a composite index on `(user_id, said_on DESC)` would
let the index supply the ordering. Deferred deliberately: at this scale the
sort is free, and a second copy of ownership can disagree with the first —
with the stale copy being exactly what the security check reads.

**`/health` does not check the database.** It reports only that the web
process is answering, so an instance with a dead connection still looks
healthy to a load balancer.
