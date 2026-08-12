# QuoteJar

[![CI](https://github.com/cefaust/quotejar/actions/workflows/ci.yml/badge.svg)](https://github.com/cefaust/quotejar/actions/workflows/ci.yml)

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
| GET    | /               | —    | service name, version, and a pointer to /docs |
| GET    | /health/live    | —    | liveness — checks nothing, deliberately      |
| GET    | /health/ready   | —    | readiness — 503 if the database is unreachable |
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

## Deployment

Live: **https://oqpao4he6pspve4xea76u7ikra0nzodi.lambda-url.us-east-1.on.aws/**

### Architecture

```
        internet
           │  HTTPS
           ▼
   ┌──────────────────┐
   │ Lambda Function  │   auth type NONE — public by design;
   │      URL         │   authorisation is the app's own JWT layer
   └────────┬─────────┘
            ▼
   ┌──────────────────────────────────────────────┐
   │ Lambda: quotejar-api                         │
   │   container image from ECR                   │
   │   FastAPI ── Mangum ── Runtime Interface     │
   │   reserved concurrency 5                     │
   │   inside VPC, sg-…ed25f                      │
   └───┬──────────────────────────────┬───────────┘
       │ 5432 (SG reference)          │ 443 (SG reference)
       ▼                              ▼
   ┌──────────────┐            ┌────────────────────┐
   │ RDS Postgres │            │ Secrets Manager    │
   │ db.t4g.micro │            │ VPC endpoint       │
   │ 16.14        │            │ (no internet path) │
   └──────────────┘            └────────────────────┘
```

Request path: a caller hits the Function URL over HTTPS. Lambda invokes the
container, whose entrypoint is AWS's Runtime Interface Client. Mangum
translates the Function URL event into an ASGI scope and hands it to the same
FastAPI application that runs under uvicorn locally. The response makes the
return trip.

**The function has no route to the internet.** It sits in a private subnet
with no NAT gateway, which is why Secrets Manager is reached through a VPC
interface endpoint rather than a public API call. That is a deliberate
tradeoff: the endpoint costs roughly $7/month, a NAT gateway would cost about
$32, and giving the function internet access to save either would widen its
blast radius for no benefit — it needs to talk to exactly two things.

**What runs where:**

| Component | Identifier | Notes |
| --------- | ---------- | ----- |
| Lambda | `quotejar-api` | container image, 1024 MB, 30 s timeout, x86_64 |
| Function URL | `oqpao4he6…on.aws` | auth `NONE`, `BUFFERED` |
| ECR | `quotejar` | tags `lambda`, `latest`; scan-on-push |
| RDS | `quotejar-db` | PostgreSQL 16.14, `db.t4g.micro`, 20 GB gp3 |
| Secrets | `quotejar/database-url`, `quotejar/jwt-secret` | values never in env vars |
| VPC endpoint | `vpce-063ee61683bd56442` | Secrets Manager, interface type |
| Execution role | `quotejar-lambda-role` | basic + VPC access + those two secret ARNs |
| Security groups | `sg-0956a5f7b9950e1b2` (RDS), `sg-0c47444c43f3ed25f` (Lambda), `sg-04efb90f045da68c7` (endpoint) | |
| Budget | `quotejar-monthly-10usd` | 50/80/100% actual, 100% forecast |
| Alarms | `quotejar-estimated-charges-5usd`, `-10usd` | via SNS `quotejar-billing-alerts` |

### Configuration and secrets

Nothing sensitive is in the image or in Lambda environment variables. The
environment holds only *identifiers*:

    DATABASE_URL_SECRET_ID = quotejar/database-url
    JWT_SECRET_SECRET_ID   = quotejar/jwt-secret

Environment variables are readable by anyone with
`lambda:GetFunctionConfiguration` and are displayed in the console, so a
password in one is a password shared with every reader of that page. The
values are fetched over an authenticated API call, governed by IAM, at
**module scope** — once per cold start, never per request. See `app/config.py`.

### Connection pool sizing

Reserved concurrency is 5, and that number is only half the control:

| | |
| --- | --- |
| RDS `max_connections` | 79 |
| less `superuser_reserved_connections` | 3 |
| less baseline in use | ~9 |
| **usable** | **~67** |

Pools are per-process and each warm Lambda is a process, so total connections
are `instances x (pool_size + max_overflow)`. SQLAlchemy's defaults are
`5 + 10 = 15`, which at 5 instances is **75 — more than the database allows**.
Capping concurrency alone does not bound the problem. The pool is therefore
set to `1 + 1`, giving a worst case of `5 x 2 = 10` and leaving 66 spare.

When the database refuses connections it refuses *everyone*, including `psql`
from your laptop — so the outage locks you out of the box you need to diagnose
it from. RDS Proxy solves this at larger scale for about $20/month; capping
concurrency and sizing the pool is the same protection for free.

### CI/CD

Two workflows, in `.github/workflows/`.

**`ci.yml`** runs on every push and every pull request: `ruff check`,
`ruff format --check`, migrations against a PostgreSQL 16 service container,
then the full suite. A failing test fails the build. `main` is protected and
requires this check to pass, so it is not advisory.

**`cd.yml`** runs only on push to `main`. It builds the image, pushes it to
ECR tagged with the commit SHA, updates the Lambda, waits for the update to
complete, and smoke-tests the live endpoint. **Manual deploys are no longer
necessary**; the runbook below is kept for disaster recovery and for the
initial provisioning a pipeline cannot do for itself.

**No AWS credentials are stored in GitHub.** There is no `AWS_ACCESS_KEY_ID`
secret in this repository. The deploy job requests a short-lived OIDC token
from GitHub describing that specific workflow run, and exchanges it with AWS
STS for credentials valid for one hour, via the role
`quotejar-github-actions`.

The trust policy is the security boundary:

```json
"Condition": {
  "StringEquals": {
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
    "token.actions.githubusercontent.com:sub":
      "repo:cefaust@101376746/quotejar@1322374978:ref:refs/heads/main"
  }
}
```

**Note the numeric IDs, and expect this to cost you an hour if you have not
seen it.** AWS's documentation, GitHub's documentation, and essentially every
tutorial show the subject as `repo:OWNER/REPO:ref:refs/heads/BRANCH`. The token
this repository actually receives embeds the immutable owner and repository
database IDs instead:

    repo:cefaust@101376746/quotejar@1322374978:ref:refs/heads/main

A trust policy written to the documented format never matches. STS fails with
`Not authorized to perform sts:AssumeRoleWithWebIdentity` and deliberately does
not say *which* condition failed — telling you that would let an attacker probe
the policy — so it presents as a permissions or thumbprint problem and sends
you looking in the wrong place.

The IDs are a security improvement, not an inconvenience: names can be released
and re-registered by someone else, while a database ID cannot, so pinning to
the ID closes a rename-and-impersonate hole.

**Do not guess at the value — read it.** A step with `id-token: write` can
print the non-secret claims:

```yaml
- run: |
    TOKEN=$(curl -sS -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
      "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=sts.amazonaws.com" | jq -r '.value')
    PAYLOAD=$(echo "$TOKEN" | cut -d. -f2)
    PAD=$(( (4 - ${#PAYLOAD} % 4) % 4 ))
    PAYLOAD="${PAYLOAD}$(printf '=%.0s' $(seq 1 $PAD))"
    echo "$PAYLOAD" | tr '_-' '/+' | base64 -d | jq '{sub, aud, repository, ref}'
```

Print claims only, never the token.

`sub` identifies *which workflow context* is asking. Scoped as above, only a
run on `main` in this repository can assume the role. Scoping it to
`repo:cefaust/quotejar:*` instead would look nearly identical and be much
weaker: `*` also matches `ref:refs/heads/anything`, and — worse —
`pull_request`. Anyone who opens a pull request from a fork could then edit
the workflow to assume your deployment role and push whatever image they
liked. The wildcard turns "code that reached main" into "anyone who can open
a PR".

The role's permissions are scoped too: push only to the `quotejar` ECR
repository, update only the `quotejar-api` function. It cannot read secrets,
touch RDS, or modify IAM.

### Rolling back

Every deploy pushes an image tagged with its commit SHA, so every previously
deployed version is still in ECR and addressable. Rolling back is pointing the
function at an older tag — no rebuild, no revert commit, no waiting on CI.

```bash
# What is running right now
aws lambda get-function --function-name quotejar-api \
  --query 'Code.ImageUri' --output text

# What is available, newest first
aws ecr describe-images --repository-name quotejar \
  --query 'reverse(sort_by(imageDetails,&imagePushedAt))[].{Tags:imageTags,Pushed:imagePushedAt}' \
  --output table

# Roll back to a specific commit
ACCT=782747473074
aws lambda update-function-code --function-name quotejar-api \
  --image-uri "${ACCT}.dkr.ecr.us-east-1.amazonaws.com/quotejar:<sha>" --publish
aws lambda wait function-updated-v2 --function-name quotejar-api

# Verify
URL=$(aws lambda get-function-url-config --function-name quotejar-api --query FunctionUrl --output text)
curl -s "${URL}health/ready"
```

**This is why `latest` is not deployed.** `latest` is a mutable pointer: it
means "whatever was pushed most recently", so a function deployed from it
cannot tell you which commit it is running, and two deploys of `latest`
minutes apart can ship different code with no record of the difference. There
is also no *earlier* `latest` to return to — rolling back requires rebuilding
the old commit and hoping the build is reproducible. A SHA tag is immutable
and traceable in both directions. `latest` is kept only for humans pulling by
hand; nothing automated reads it.

**Rolling back code does not roll back the database.** If the version you are
returning to predates a migration, it runs against a schema it does not know.
Additive migrations — new nullable columns, new tables — are safe in both
directions. A migration that renames or drops is not, and rolling back across
one needs a forward fix instead.

### Where migrations run, and why

**They run from an operator's laptop, before the PR is merged. Not in CI, not
in the Lambda.**

#### The options that were considered

| | Automated | Ordering guaranteed | RDS stays locked | Extra infrastructure |
| --- | --- | --- | --- | --- |
| **Manual, pre-merge** (chosen) | no | no | **yes** | none |
| Migration Lambda in the VPC | yes | yes | **yes** | second function + role |
| `alembic upgrade` in CI | yes | yes | **no** | none |
| Self-hosted runner in the VPC | yes | yes | **yes** | an EC2 instance to operate |
| On Lambda cold start | yes | no | yes | none |

**Running it in CI** requires allowing GitHub's runners into the database.
They come from a large, frequently-changing set of published Azure ranges, so
in practice that is indistinguishable from opening the database to the
internet, and it dissolves the control QJ-3 exists to demonstrate.

**Running it on Lambda cold start** is the intuitive answer and the worst one.
Every cold start would run it concurrently against one database; Alembic takes
no distributed lock, so two containers read the same revision, both decide a
migration is pending, and the loser dies on "column already exists." It also
couples "can this instance serve traffic" to "did a schema change succeed."

**A self-hosted runner** would work, but it means operating an EC2 instance —
and self-hosted runners on a *public* repository are a known risk, since a
pull request from a fork can execute code on a runner that sits inside the
VPC.

#### Why manual was chosen

**A human should watch the one irreversible step.** Everything else in this
pipeline is reversible: a bad deploy rolls back by pointing the function at an
older SHA tag. A dropped column does not come back. Migrations are the single
deploy step that can destroy data permanently, and automating the irreversible
step optimises for convenience exactly where convenience is worth least.

**It is the only option that neither weakens nor works around the security
boundary.** This database is publicly reachable; the security group is the
whole control. Two of the alternatives preserve it by building infrastructure
to tunnel around it, and one dissolves it.

**Automating it would not remove the manual path anyway.** Lambda's hard
900-second ceiling is below what real migrations take. The `password_hash`
backfill already in this repository hashes per row with bcrypt at ~216 ms, so
it would time out at roughly **4,000 users** — and index builds, table
rewrites, and constraint validation on a burstable `db.t4g.micro` are all
candidates too. A migration Lambda would automate the easy migrations while
the hard ones still ran by hand, leaving two paths to maintain and a judgement
call about which to use each time.

**The scale does not justify the machinery.** One developer, one environment,
deploys measured per week. Automation earns its cost by removing repeated
human error across many people and many runs.

#### The cost, and when this decision flips

Nothing enforces the ordering. Merging a PR whose code expects a column that
does not exist yet deploys a function that errors on every request touching
that table. The smoke test catches the gross case — readiness failing turns
the pipeline red — but readiness only runs `SELECT 1`, so a missing column in
one table would pass it and fail in production.

**This becomes a migration Lambda the moment either of these is true:** a
second person can merge to `main`, or a migration is written that is not
backward-compatible. Until then the manual step is a deliberate trade, not an
omission.

#### The part no pipeline can solve

Choosing where migrations run is a *build* decision. Whether a migration is
safe to deploy is a *design* decision, and it is the one that determines
whether the deploy actually breaks.

A pipeline controls **ordering**. It cannot remove the **window** in which two
versions of the code run against one schema. `update-function-code` does not
swap atomically: warm Lambda instances keep serving the previous image until
they recycle, so old and new code run side by side against a single schema on
every deploy. Rolling back makes it worse — the code returns to an older SHA
and the schema stays where it is.

The control for that is **expand/contract**: never change a thing in place.
Add the new alongside the old, migrate across several releases, remove the old
only once nothing reads it. A rename becomes three releases rather than one:

1. **Expand** — add the new column nullable; write both, read the old
2. **Migrate** — backfill; read the new, still write both
3. **Contract** — stop writing the old; drop it in a later release

Every step is safe with both versions running, which is what makes deploy
order stop mattering. The QJ-2 `password_hash` migration already follows this
shape: added nullable, backfilled, then constrained.

### Deploy runbook

Deploys are automatic on merge to `main`. This section is for disaster
recovery, for the initial provisioning, and for running migrations.

Assumes `aws login` is current and Docker is running.

**1. Build and push the image.**

    cd /path/to/quotejar
    ACCT=782747473074
    REPO="${ACCT}.dkr.ecr.us-east-1.amazonaws.com/quotejar"

    aws ecr get-login-password --region us-east-1 \
      | docker login --username AWS --password-stdin "${ACCT}.dkr.ecr.us-east-1.amazonaws.com"

    docker buildx build --platform linux/amd64 \
      --provenance=false --sbom=false \
      --output "type=image,name=${REPO}:lambda,oci-mediatypes=false,push=true" .

The three flags are not optional. Buildx defaults to OCI media types and
attaches provenance/SBOM attestations, which produce a manifest **Lambda
rejects** with `The image manifest, config or layer media type for the source
image is not supported`. Verify with:

    aws ecr batch-get-image --repository-name quotejar --image-ids imageTag=lambda \
      --query 'images[0].imageManifestMediaType' --output text
    # must be application/vnd.docker.distribution.manifest.v2+json

**2. Run migrations — from your laptop, before deploying the code that needs
them.**

**There is no standing rule allowing your laptop into the database.** Access is
granted just before the migration and revoked immediately after, so the
exposure window is minutes rather than months. Run all three steps together.

*Open access:*

    MYIP=$(curl -s https://checkip.amazonaws.com)
    aws ec2 authorize-security-group-ingress --group-id sg-0956a5f7b9950e1b2 \
      --ip-permissions "IpProtocol=tcp,FromPort=5432,ToPort=5432,IpRanges=[{CidrIp=${MYIP}/32,Description='jit migration access'}]"

*Migrate:*

    export DATABASE_URL=$(aws secretsmanager get-secret-value \
      --secret-id quotejar/database-url --query SecretString --output text)
    export JWT_SECRET=$(aws secretsmanager get-secret-value \
      --secret-id quotejar/jwt-secret --query SecretString --output text)

    source .venv/bin/activate
    alembic upgrade head

*Close it again — do not skip this:*

    aws ec2 revoke-security-group-ingress --group-id sg-0956a5f7b9950e1b2 \
      --ip-permissions "IpProtocol=tcp,FromPort=5432,ToPort=5432,IpRanges=[{CidrIp=${MYIP}/32}]"

*Confirm only the Lambda reference remains:*

    aws ec2 describe-security-group-rules \
      --filters Name=group-id,Values=sg-0956a5f7b9950e1b2 \
      --query 'SecurityGroupRules[?IsEgress==`false`].{Cidr:CidrIpv4,Group:ReferencedGroupInfo.GroupId}' \
      --output table

#### Why just-in-time rather than a standing rule

A `/32` is narrow at the instant you write it. It is a snapshot, not a
guarantee — a residential IP changes on a DHCP lease renewal, a router reboot,
ISP maintenance, or the moment you work from a café, a hotspot, or a VPN.

The failure is asymmetric, and that is what makes a standing rule worse than
it looks:

- **You losing access is loud.** The next migration hangs and times out.
- **A stranger gaining it is silent.** The rule still reads
  `67.183.227.35/32` and still says "admin laptop", but that address now
  belongs to whoever the ISP handed it to.

The natural fix makes it accumulate. You hit the timeout, add your new IP, and
move on — leaving the stale rule behind. Four times in a year and the group
allows five residential addresses, four belonging to strangers, every one of
them labelled "admin laptop". "Restricted to one `/32`" then describes a
moment rather than a steady state.

Granting access only for the minutes a migration takes removes the drift
entirely: there is no long-lived rule to go stale, and forgetting to re-add it
next time is self-correcting, because the migration simply fails until you do.

#### The database is not defended by the security group alone

Worth being accurate about, since the security group is only the network
layer:

| Layer | Control |
| ----- | ------- |
| Network | one temporary `/32` during migrations, plus the Lambda's SG reference |
| Transport | `rds.force_ssl = 1` — the **server refuses** non-TLS connections; verified, `sslmode=disable` is rejected |
| Authentication | 40-character random master password, stored in Secrets Manager, never committed |

Someone who inherited the IP would still need the password, over TLS. The
security group is the outermost layer, not the only one.

**What would remove the inbound rule entirely:** SSM Session Manager port
forwarding. RDS becomes private with no CIDR rule at all, and administrative
access is authenticated by IAM rather than by IP address. That is the
production answer; just-in-time is the cheap approximation of it.

**3. Point the function at the new image.**

    aws lambda update-function-code --function-name quotejar-api \
      --image-uri "${REPO}:lambda" --publish
    aws lambda wait function-updated-v2 --function-name quotejar-api

**4. Verify.**

    URL=$(aws lambda get-function-url-config --function-name quotejar-api \
      --query FunctionUrl --output text)
    curl -s "${URL}health/live"    # {"status":"alive"}
    curl -s "${URL}health/ready"   # {"status":"ready"}

If readiness fails but liveness passes, the function is up and the database is
not reachable — check the RDS security group and that the function is still
attached to `subnet-05ea50db0fd8c9ab0`.

### Why migrations do not run on container start

The tempting one-liner is `alembic upgrade head && uvicorn ...`. It is a race
the moment there is more than one instance, and Lambda routinely runs several.

Every cold start would run it concurrently against the same database. Alembic
takes no distributed lock. Two instances read the same current revision, both
conclude the same migration is pending, and both apply it — so an `ADD COLUMN`
succeeds once and fails on the rest with "column already exists". Those
containers die, get replaced, and fail again.

It is also wrong in a quieter way: it couples "can this instance serve
traffic" to "did a schema change succeed", so one bad migration takes down the
entire service instead of failing a single controlled step. And migrations
often need a lock; a hundred cold starts contending for one is a stampede
against the database you are trying to change.

Migrations are an operator action with a human watching. That is why Alembic
is in `requirements-dev.txt` and not in the image at all — the capability is
absent, not merely unused.

### Teardown

Run this when the sprint ends. Everything except the VPC endpoint is
free-tier eligible, but free tier expires and an idle RDS instance is the
classic surprise bill.

    # Most expensive first — the endpoint is the only always-billing component
    aws ec2 delete-vpc-endpoints --vpc-endpoint-ids vpce-063ee61683bd56442

    aws rds delete-db-instance --db-instance-identifier quotejar-db \
      --skip-final-snapshot --delete-automated-backups
    aws rds wait db-instance-deleted --db-instance-identifier quotejar-db

    aws lambda delete-function-url-config --function-name quotejar-api
    aws lambda delete-function --function-name quotejar-api

    aws ecr delete-repository --repository-name quotejar --force

    aws secretsmanager delete-secret --secret-id quotejar/database-url --force-delete-without-recovery
    aws secretsmanager delete-secret --secret-id quotejar/jwt-secret  --force-delete-without-recovery

    # Security groups must go after the resources using them
    aws ec2 delete-security-group --group-id sg-04efb90f045da68c7   # endpoint
    aws ec2 delete-security-group --group-id sg-0c47444c43f3ed25f   # lambda
    aws ec2 delete-security-group --group-id sg-0956a5f7b9950e1b2   # rds

    aws iam delete-role-policy --role-name quotejar-lambda-role --policy-name quotejar-read-own-secrets
    aws iam detach-role-policy --role-name quotejar-lambda-role \
      --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole
    aws iam detach-role-policy --role-name quotejar-lambda-role \
      --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    aws iam delete-role --role-name quotejar-lambda-role

    aws logs delete-log-group --log-group-name /aws/lambda/quotejar-api

**Keep the budget and alarms.** They cost nothing and they are what tells you
if something was missed:

    aws budgets describe-budgets --account-id 782747473074
    aws ec2 describe-security-groups --filters Name=group-name,Values=quotejar-*
    aws rds describe-db-instances --query 'DBInstances[].DBInstanceIdentifier'

`--skip-final-snapshot` on RDS is deliberate: a retained snapshot keeps
billing for storage after the instance is gone, which is exactly the forgotten
charge teardown is meant to prevent. It also destroys the data irrecoverably,
which is correct here and would be catastrophic anywhere real.

### Not production-grade, and what would change

**The database is publicly reachable.** `PubliclyAccessible` is true so
migrations can run from a laptop.

In steady state the security group has **no CIDR rules at all** — only a
reference to the Lambda's security group. A `/32` for an operator is added
just before a migration and revoked immediately after, so there is no
long-lived allowance to go stale (see the runbook). Two further layers sit
behind it: `rds.force_ssl = 1`, so the server refuses non-TLS connections, and
a 40-character random master password held in Secrets Manager.

What remains true regardless: the instance has a public DNS name and is
resolvable from anywhere, so the network layer is doing work that a private
subnet would make unnecessary. Properly: private subnets with no public IP,
administrative access through SSM Session Manager port forwarding —
authenticated by IAM rather than by IP address — and migrations run as a
one-off task inside the VPC.

**Everything was provisioned as the account root user.** Root cannot be
scoped, cannot be revoked without disrupting the account, and is constrained
by no IAM policy, permission boundary, or SCP. Properly: an IAM user or role
with only the permissions the deployment needs, and root locked behind MFA and
used for nothing.

**The image runs as root.** The App Runner build created an unprivileged
`appuser`; the Lambda base image does not, and adding a `USER` directive risks
breaking the Runtime Interface Client. Lambda's execution model substitutes
for it — each invocation gets a dedicated Firecracker microVM with a read-only
filesystem outside `/tmp` — but it is a real difference between the two
targets rather than an equivalent.

**The master database user is the application user.** The app connects as the
RDS master account, which can create and drop anything. Properly: a separate
least-privilege role with `SELECT/INSERT/UPDATE/DELETE` on the application
tables and nothing else, so a SQL-injection foothold cannot reach the schema.

**Secrets do not rotate.** Both are static. Secrets Manager supports automatic
rotation with a Lambda rotation function; wiring it up means the application
must tolerate a credential changing under it, which is its own ticket.

**Cold starts are 1–3 seconds.** Measured around 1.0–1.6 s on a container
image of this size. Nobody notices at this traffic level, and it is the
explicit tradeoff for paying nothing while idle. Provisioned concurrency
removes it and reintroduces a constant bill.

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

**~~`/health` does not check the database.~~** Closed in QJ-3. `/health/ready`
checks database reachability and returns 503 when it fails; `/health/live`
deliberately still checks nothing, because a failing liveness probe means
"restart me" and restarting does not fix a down database.
