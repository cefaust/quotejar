# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: builder
#
# Everything needed to *produce* the dependency tree lives here and is thrown
# away. pip, its wheel cache, setuptools, and any compiler a package needed to
# build itself never reach the running container.
#
# That is not only about size. A production image containing pip is an image
# where anyone who achieves code execution can install their own tooling from
# the network. Removing the toolchain removes that step.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Dependencies go into their own virtualenv rather than the system site-
# packages, so the runtime stage can copy one self-contained directory instead
# of picking paths out of the base image.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copied before the application code on purpose. Docker caches layers by their
# inputs, so as long as this file is unchanged the (slow) install below is
# reused and only the (fast) code copy re-runs. Copying the source first would
# invalidate the install on every edit.
COPY requirements.txt .

# requirements.txt only -- never requirements-dev.txt. pytest and the httpx
# test client are code an attacker can reach and no user benefits from.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 # Then remove the installer itself. `python -m venv` puts pip inside the
 # virtualenv, so copying the venv would carry pip into the runtime stage --
 # exactly the package manager this multi-stage build exists to leave behind.
 # Verified: before this line, `which pip` in the final image returned
 # /opt/venv/bin/pip.
 && rm -rf /opt/venv/lib/python3.12/site-packages/pip* \
           /opt/venv/lib/python3.12/site-packages/setuptools* \
           /opt/venv/lib/python3.12/site-packages/pkg_resources \
           /opt/venv/bin/pip*


# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# PYTHONDONTWRITEBYTECODE: no .pyc files. The container is cattle -- it is
#   replaced, never repaired -- so anything written to its local filesystem is
#   discarded at the next deploy and exists only to make the layer dirty.
# PYTHONUNBUFFERED: stdout unbuffered, so logs appear when they happen rather
#   than when a 4 KB buffer fills. Without it, the logs from a container that
#   crashes are the ones you never see.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# A dedicated unprivileged account. What running as root would actually cost:
#
#   - Root inside the container maps to root on the host under the default
#     runtime. Combined with a container escape -- a kernel bug, a careless
#     bind mount -- that is host compromise rather than container compromise.
#   - Root can write anywhere in the filesystem, so an attacker with code
#     execution can overwrite application code, install a persistent backdoor,
#     or replace a binary on PATH. As appuser, the application's own files are
#     read-only to it: it can execute them and cannot modify them.
#   - Root can bind ports below 1024. Nothing here needs to, and the inability
#     to is a small barrier to a payload that wants to listen somewhere
#     unexpected.
#   - It defeats defence in depth. Every other control assumes an attacker who
#     lands here is constrained; as root, they are not.
#
# --system: no password, no home directory, no login shell.
RUN groupadd --system --gid 1001 appuser \
 && useradd --system --uid 1001 --gid appuser --no-create-home appuser \
 # The base image ships its own pip in /usr/local, independent of the venv.
 # Removing only the venv's copy would leave `python -m pip` working, so both
 # have to go for the claim above to be true.
 && rm -rf /usr/local/lib/python3.12/site-packages/pip* \
           /usr/local/lib/python3.12/site-packages/setuptools* \
           /usr/local/lib/python3.12/site-packages/pkg_resources \
           /usr/local/bin/pip*

WORKDIR /code

# The dependency tree, already built, with none of the tooling that built it.
COPY --from=builder /opt/venv /opt/venv

# Application code, owned by root and merely readable by appuser. The running
# process therefore cannot modify its own source.
#
# alembic/ and alembic.ini are included deliberately, even though migrations
# do NOT run at startup (see CMD). Shipping them means a migration can be run
# from this exact image -- same code, same Alembic version, same revision
# graph as the deployment it is migrating for. The alternative, running
# migrations from a laptop, works right up until the laptop's checkout differs
# from what is deployed.
#
# tests/ and scripts/ are absent. Tests have no business in production, and
# scripts/seed.py inserts a user with a hardcoded password.
COPY --chown=root:root ./app ./app
COPY --chown=root:root ./alembic ./alembic
COPY --chown=root:root ./alembic.ini ./alembic.ini

USER appuser

# App Runner's default. Overridable so the same image runs anywhere.
ENV PORT=8080
EXPOSE 8080

# Readiness, not liveness. A container that cannot reach its database should
# be pulled from rotation, and this is the signal Docker and Compose surface.
#
# Uses the interpreter already present rather than installing curl, keeping
# one fewer binary in the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,sys,urllib.request; p=os.environ.get('PORT','8080'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+p+'/health/ready', timeout=4).status==200 else 1)"

# Serve only. Migrations are deliberately NOT run here.
#
# `alembic upgrade head && uvicorn ...` is the tempting one-liner and it is a
# race as soon as there is more than one instance: every container runs it on
# boot, concurrently, against the same database. Alembic takes no distributed
# lock. Two instances read the same current revision, both decide the same
# migration is pending, and both apply it -- so an ADD COLUMN fails on the
# second with "column already exists", that container dies, the platform
# restarts it, and it fails again. A rolling deploy can also leave old and new
# code running against a schema only one of them understands.
#
# It is also wrong in a subtler way: it couples "can this instance serve
# traffic" to "did a schema change succeed", so a bad migration takes the
# whole service down rather than failing one controlled step.
#
# Migrations are a separate, deliberate action. See the runbook in README.md.
#
# A shell is needed to expand ${PORT}; exec form alone cannot do variable
# substitution. `exec` is what makes that safe: it *replaces* the shell
# process with uvicorn rather than spawning it as a child, so uvicorn ends up
# as PID 1 and receives SIGTERM directly.
#
# Without `exec`, /bin/sh stays PID 1 with uvicorn beneath it, and sh does not
# forward signals to its children. The platform's graceful-shutdown request
# would go to the shell and be ignored, uvicorn would never drain, and the
# container would be SIGKILLed after the timeout -- dropping every in-flight
# request on each deploy.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
