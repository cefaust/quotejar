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

## Rate limiting

### The problem it solves

bcrypt costs ~216 ms of CPU per verification, deliberately — that slowness is
what protects hashes against offline cracking. Pointed at a live endpoint the
property inverts: an attempt costs an attacker one cheap HTTP request and costs
us 216 ms of a reserved execution slot. With reserved concurrency of 5, five
concurrent attackers saturate the function and every real user is throttled.
No password has to be guessed for the service to go down.

What follows raises the cost of that attack by about three orders of magnitude.
It does not eliminate it — reserved concurrency of 5 remains the binding
constraint, and a distributed caller staying inside every published limit can
still saturate the function. See [What this does not
solve](#what-this-does-not-solve-reserved-concurrency-is-still-the-bottleneck).

### The limits

| Scope | Keyed on | Limit | Window |
| ----- | -------- | ----- | ------ |
| `/auth/login`, `/auth/register` | client IP | 10 | 15 min |
| failed logins | email address | 5 | 15 min |
| authenticated endpoints | user ID | 120 | 1 min |

**Why the first two are different limits rather than one.** They protect
different things and each is blind exactly where the other sees. The IP limit
protects the *service* from resource exhaustion; the email limit protects an
*account* from credential stuffing. An attacker with a botnet defeats the IP
limit while every attempt still lands on one address. Conversely a shared NAT —
an office, a university, a mobile carrier — puts thousands of innocent users
behind one address, where a per-IP limit punishes all of them for one. Neither
substitutes for the other.

**Why the third is keyed on user ID.** After authentication there is something
better than an address available. A user ID survives a phone moving between
wifi and cellular, cannot be changed by rotating IPs, and is unaffected by NAT.
IP is what you use when you do not yet know who is calling; once you do, using
it anyway throws information away.

**Why the email limit counts failures only.** A user who types their password
correctly has not attacked anything. Counting successes would penalise the
account's real owner for using their own account, and would hand an attacker a
way to throttle someone by deliberately failing at their address.

### Why IP is a weak key at all

Worth being honest that per-IP limiting is the least reliable of the three.
Carrier-grade NAT puts entire mobile networks behind a handful of addresses, so
one limit covers thousands of unrelated people. IPv6 privacy extensions rotate
a client's address regularly, and a residential /64 gives one attacker
18 quintillion addresses to cycle through. Cloud egress is rentable by the
hour.

It is used before authentication because there is nothing better — the caller
has not yet told us who they are. Everything after that point is keyed on
identity, which is the actual answer to "what would you key on instead".

### Store: DynamoDB, and why not the alternatives

In-process counters cannot work here. Lambda gives up to five execution
environments, each with its own memory, created and destroyed unpredictably, so
a per-process counter would grant 5x the intended limit and reset on every cold
start. The counter has to be shared.

| | Monthly | Why not chosen |
| --- | --- | --- |
| **DynamoDB** (chosen) | **~$0** | — |
| ElastiCache Redis | ~$9–12 | An always-on node for hobby traffic, plus something else to patch, monitor, and remember to tear down. `INCR`/`EXPIRE` is genuinely simpler than conditional writes, and sub-millisecond — it is the better tool, at a standing cost this project cannot justify. |
| CloudFront + AWS WAF | ~$6+ | **WAF cannot attach to a Lambda Function URL** — the supported targets are CloudFront, API Gateway, ALB, AppSync, Cognito, App Runner, Amplify, and Verified Access. It would mean adding CloudFront as a fronting origin. More decisively, WAF does not decode JWTs, so it cannot key on user ID and cannot satisfy the per-user limit at all — it would be an *additional* layer on top of one of the others, not an alternative. It would also require locking the Function URL to `AWS_IAM` behind Origin Access Control, since otherwise an attacker simply bypasses CloudFront and hits Lambda directly. |

DynamoDB's decisive advantage here is specific to this architecture: the Lambda
has no route to the internet, so any store must be reachable privately, and
DynamoDB offers a **Gateway** VPC endpoint, which is free. Compare the Secrets
Manager *Interface* endpoint at roughly $7/month. Pay-per-request pricing at
this traffic rounds to nothing, TTL reclaims old counters automatically, and
there is no instance to operate or tear down.

The honest cost of the choice: conditional-write logic is more code than
`INCR`, and single-digit-millisecond latency is slower than Redis. Neither
matters next to a 216 ms bcrypt call.

### Algorithm: sliding window counter

**Fixed window** — one counter per calendar window — is simplest and has a
specific flaw: an attacker gets *twice* the limit across a boundary. With 10
per minute they send 10 at 11:59:59 and 10 more at 12:00:00. Both windows are
individually legal; 20 requests land in two seconds. For a limiter whose job is
bounding a 216 ms operation, a 2x burst is the difference between bounded and
unbounded.

**Sliding window log** stores every request timestamp and is exact, but a limit
of N costs N stored timestamps per key — unbounded write amplification under
exactly the attack this exists to stop.

**Token bucket** handles bursts gracefully but needs two mutable fields
updated atomically, which is a read-modify-write rather than a single atomic
`ADD`.

**Sliding window counter** keeps a counter for the current window and the
previous one, weighting the previous by how much still overlaps:

    estimate = previous_count × (1 − elapsed_fraction) + current_count

Two small items per key, one atomic increment, no boundary burst. There is a
test that specifically fires across a window boundary and asserts the second
burst is rejected.

### Fail open, deliberately

If DynamoDB is unreachable, requests **proceed** and the failure is logged at
ERROR with a traceback.

The reasoning: a rate limiter is a control on abuse, not a dependency of the
product. Failing closed would mean a DynamoDB outage takes QuoteJar down
entirely — converting a partial degradation into a total one, and adding a new
single point of failure in the name of security. The blast radius of the wrong
choice is asymmetric: failing open during an outage means a window with no
limiting, while failing closed means a window with no service.

**The opposite choice is defensible and would be right elsewhere.** If this
guarded something whose abuse is worse than its unavailability — payment
authorisation, a password reset flow, anything where an unlimited attempt rate
is catastrophic — fail closed. The rule of thumb: fail open when the limiter
protects *capacity*, fail closed when it protects *correctness or money*. Here
it protects capacity.

What makes fail-open survivable is that the gap is loud. It logs at ERROR with
a traceback on every failed call, because a fail-open limiter that logs quietly
is indistinguishable from one that works, and you discover during an incident
that it has been open for a month. There is a test asserting the API returns
200 rather than 500 when the store is down — the single most important test in
the suite, because that behaviour is invisible in normal operation.

### Known limit: throttling is not distinguished from unavailability

`RateLimiter` catches a bare `Exception` around every store call and fails open
on all of them. That deliberately covers a partition, expired credentials, a
deleted table, a missing SDK — failures where proceeding is right.

**It also covers a `ThrottlingException`, and that one is different in kind.**
A throttling response is not DynamoDB being broken; it is DynamoDB working
correctly and telling us to slow down. The failure mode is self-reinforcing:
the attack this exists to stop is high request volume, high request volume
means high DynamoDB volume, and if that trips throttling then the limiter
disables itself at precisely the moment it is needed. Every throttled check
returns "allowed", so the counters stop advancing and the load that caused the
throttling is the load that is now unmetered.

**Why it is not reachable today.** Each limited request costs one `ADD` write
and two strongly-consistent reads — 1 WCU and 2 RCU. A rejected request skips
bcrypt and costs about three DynamoDB round trips, call it 20 ms, so reserved
concurrency of 5 tops the whole function out near 250 requests/second. All the
counters for one key in one window are a single item, so that is ~250 WCU/s
against one partition key, against an on-demand ceiling of 1,000 WCU/s and
3,000 RCU/s per partition key. Roughly 4x of headroom.

**4x is a margin, not a guarantee, and it is a margin that the concurrency cap
is holding up.** Raising reserved concurrency — or QJ-5's move to Fargate,
where nothing caps concurrency at 5 — spends that headroom directly. The two
limits are coupled: the bottleneck in the section below is the only reason this
one is theoretical.

**The fix when it matters** is to catch `ThrottlingException`,
`ProvisionedThroughputExceededException`, and `RequestLimitExceeded` separately
from the rest and fail *closed* on them — reject with 429 — while continuing to
fail open on genuine unavailability. Throttling means the store is up and
declining the write, so a 429 is the honest answer, and it is the one case
where the "protects capacity, so fail open" rule inverts: the capacity being
protected is what ran out. Not done here because it cannot currently trigger
and an untriggerable branch is an untested branch. It should be done as part of
QJ-5, in the same change that removes the concurrency cap.

### Client IP, and the way this is usually broken

The caller's address comes from `request.client.host`, which Mangum populates
from `requestContext.http.sourceIp` — set by AWS from the actual TCP
connection, and not influenceable by the caller.

**`X-Forwarded-For` is deliberately ignored.** Most rate-limiting guidance says
to prefer it, because most deployments sit behind a load balancer that sets it.
Nothing sits in front of this Function URL, so the header arrives exactly as
the client typed it. Verified directly: a request carrying
`X-Forwarded-For: 1.2.3.4` still reports its real `sourceIp`, and the header
passes through untouched. Keying on it would let one attacker present as
unlimited distinct clients by incrementing a number — worse than no limit,
because it looks like protection while providing none.

**This must change if anything is ever put in front.** Adding CloudFront makes
`sourceIp` CloudFront's address, collapsing every user in the world into a
handful of edge IPs and making the limit global. At that point the correct
source is the rightmost untrusted entry in `X-Forwarded-For`, or
`CloudFront-Viewer-Address` — but only once the origin is locked down so the
Function URL cannot be reached directly, since otherwise an attacker skips the
proxy and forges the header anyway.

### 429 responses

    HTTP/1.1 429 Too Many Requests
    Retry-After: 412
    RateLimit-Limit: 10
    RateLimit-Remaining: 0
    RateLimit-Reset: 412

`Retry-After` is RFC 9110 and almost universally understood; the `RateLimit-*`
fields follow the IETF draft and carry the full quota picture. Both are sent so
any client that understands either can back off correctly. `RateLimit-Reset` is
*seconds remaining* rather than a timestamp, because a duration cannot be
misread by a client whose clock disagrees with ours.

A 429 with no timing information is the thing worth avoiding: it tells a client
to stop without saying for how long, so well-behaved clients guess and the rest
hammer.

### Why not account lockout

Locking an account after N failed attempts is a real feature and deliberately
not built. It is a denial-of-service vector aimed at your own users: anyone who
knows an email address can lock its owner out by failing at it repeatedly, and
the attacker needs no credentials to do it. The per-email limit here throttles
rather than locks — it slows an attacker without giving them a button that
disables someone else's account, and it expires on its own.

### What this does not solve: reserved concurrency is still the bottleneck

The section at the top of this chapter says five concurrent attackers can
saturate the function. Rate limiting does not close that hole. It raises the
price of it, and the honest framing is a cost multiplier rather than a fix.

The arithmetic. Saturating 5 execution slots for a full 15-minute window at
216 ms per bcrypt call takes 5 × 900 / 0.216 ≈ **20,800 requests**. At 10 per
IP per window, that is about **2,080 distinct source addresses** — and every
one of them stays comfortably inside the limit the whole time. No limit is ever
tripped, no 429 is ever returned, and the service is fully saturated.

Two thousand addresses is not an exotic requirement. It is a small botnet, one
mid-sized cloud account, or a residential IPv6 /64 — which, as noted above,
hands one attacker 18 quintillion addresses to rotate through.

**The cheapest path is `/auth/register`, not `/auth/login`.** Registration
hashes the new password, so it costs the same 216 ms, but only the per-IP limit
applies to it — the per-email limit counts *failed logins* and never sees a
registration. An attacker submitting fresh addresses pays the IP limit and
nothing else. Login is marginally worse for them: an attacker hammering one
address hits the 5-failure email limit, so spreading across ~4,200 target
emails is required to match, which is more bookkeeping for the same effect.

**What the limiter actually bought.** Before QJ-6, saturation took 5 concurrent
attackers from a single machine. After, it takes ~2,080 coordinated addresses.
That is roughly three orders of magnitude, which moves the attack from
"anybody with a laptop and a for-loop" to "somebody who wants this specifically"
— genuinely worth having, and genuinely not the same as closed.

**What would actually close it**, none of which is in this ticket's scope:

- **Raise or remove reserved concurrency.** The cap is a *cost* control, not a
  security one — it exists so a runaway bill is impossible, and the account
  limit is now 1,000 after the quota increase in QJ-3. Removing it trades a
  service-availability DoS for a billing DoS. That is a real trade with a real
  answer, not an obvious win.
- **Get bcrypt off the request path for unauthenticated volume**, e.g. a proof
  of work or a CAPTCHA ahead of registration. This attacks the actual root
  cause, which is that an anonymous caller can spend 216 ms of our CPU for the
  cost of one HTTP request.
- **CloudFront + AWS WAF** for volumetric and reputation-based blocking at the
  edge, before a request ever reaches Lambda. Ruled out as the *store* for this
  ticket (see the table above — it cannot key on user ID, so it cannot satisfy
  the per-user limit), but it is the right tool for exactly this problem and
  would sit in front of, not instead of, what is built here.

### Resources created by hand (QJ-5 will import these)

| Resource | Identifier |
| -------- | ---------- |
| DynamoDB table | `quotejar-rate-limits`, PK `pk` (S), PAY_PER_REQUEST, TTL on `expires_at` |
| VPC endpoint | `vpce-08940f1ea5dae1a5c` — **Gateway**, DynamoDB, on route table `rtb-08a5b21d76235cd7f` |
| IAM inline policy | `quotejar-rate-limit-table` on role `quotejar-lambda-role` — `UpdateItem` and `GetItem`, scoped to that one table |

    aws dynamodb create-table --table-name quotejar-rate-limits \
      --attribute-definitions AttributeName=pk,AttributeType=S \
      --key-schema AttributeName=pk,KeyType=HASH \
      --billing-mode PAY_PER_REQUEST
    aws dynamodb update-time-to-live --table-name quotejar-rate-limits \
      --time-to-live-specification "Enabled=true,AttributeName=expires_at"
    aws ec2 create-vpc-endpoint --vpc-id vpc-0a7d500454d8fec5b \
      --vpc-endpoint-type Gateway \
      --service-name com.amazonaws.us-east-1.dynamodb \
      --route-table-ids rtb-08a5b21d76235cd7f

Teardown, in addition to the QJ-3 script:

    aws dynamodb delete-table --table-name quotejar-rate-limits
    aws ec2 delete-vpc-endpoints --vpc-endpoint-ids vpce-08940f1ea5dae1a5c
    aws iam delete-role-policy --role-name quotejar-lambda-role \
      --policy-name quotejar-rate-limit-table

### Testing the real store

The suite uses an in-memory store, so it never reaches AWS and needs no
credentials — `boto3` is deliberately absent from `requirements-dev.txt` so a
forgotten fixture cannot silently start writing to a real table. To exercise
the DynamoDB path by hand:

    pip install boto3 "botocore[crt]"    # crt is needed for `aws login` credentials

Then drive `RateLimiter(DynamoDBStore("quotejar-rate-limits"))` directly.

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

**~~Rate limiting.~~** Closed in QJ-6. Login and registration are limited per
IP, repeated login failures are limited per email address, and authenticated
endpoints are limited per user ID. See [Rate limiting](#rate-limiting).

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
