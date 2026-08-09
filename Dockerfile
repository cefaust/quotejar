# syntax=docker/dockerfile:1
#
# QuoteJar as a Lambda container image.
#
# The base image is AWS's, and that is not cosmetic. public.ecr.aws/lambda/*
# ships the Runtime Interface Client -- the loop that long-polls the Lambda
# Runtime API for an event, invokes your handler, and posts the response back.
# Without it a container has no way to receive an invocation. It also provides
# the Runtime Interface Emulator, which is what makes the image runnable
# locally on port 9000 for testing.
#
# Everything below the base image is the same application that runs under
# uvicorn locally. Mangum adapts ASGI to Lambda's event shape; no FastAPI code
# changes. See app/lambda_handler.py.

# ---------------------------------------------------------------------------
# Stage 1: builder
#
# Dependencies are installed here and copied forward, so pip's cache and
# metadata never reach the published image. Same base image as the runtime
# stage, so wheels resolve against the identical platform, Python version, and
# C library -- building on a different base risks a manylinux wheel that
# imports locally and fails at cold start.
# ---------------------------------------------------------------------------
FROM public.ecr.aws/lambda/python:3.12 AS builder

COPY requirements.txt .

# --target rather than a virtualenv: Lambda expects dependencies importable
# from LAMBDA_TASK_ROOT, and there is no interpreter-activation step in which
# a venv could be enabled.
#
# requirements.txt only -- never requirements-dev.txt. That file carries
# pytest, the httpx test client, and Alembic. None belong in a function that
# serves user traffic, and Alembic in particular would imply migrations could
# run here, which is exactly the thing requirement 6 forbids.
RUN pip install --no-cache-dir -r requirements.txt --target /deps


# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM public.ecr.aws/lambda/python:3.12

# Lambda's execution environment is read-only apart from /tmp, so bytecode
# would fail to write anyway. Being explicit avoids the attempt.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /deps ${LAMBDA_TASK_ROOT}

# Application code only. No tests, no scripts/ (seed.py inserts a user with a
# hardcoded password), no alembic/ -- migrations run from a laptop against
# RDS, never from inside the function.
COPY app ${LAMBDA_TASK_ROOT}/app

# The handler, as module.path.attribute. Mangum's callable, not FastAPI's app
# object -- Lambda invokes this with (event, context), which `app` would not
# understand.
#
# No ENTRYPOINT: the base image already sets it to the Runtime Interface
# Client, and overriding it would break the invocation loop.
CMD ["app.lambda_handler.handler"]

# ---------------------------------------------------------------------------
# On running as a non-root user
#
# The previous App Runner image created an unprivileged appuser and ran as it.
# That is not carried over here, and the reason is worth stating rather than
# leaving as a silent regression.
#
# Lambda does not expose the container's user as a security boundary the way a
# long-lived server does. Each execution environment is a dedicated Firecracker
# microVM with its own kernel, torn down after use and never shared between
# accounts or functions. There is no host to escape onto that is shared with
# anyone else, no neighbouring workload in the same kernel, and no persistence
# across invocations for a foothold to survive in. The filesystem is read-only
# except /tmp, so the "attacker overwrites application code" scenario that
# motivates non-root elsewhere cannot happen: the code is not writable by any
# user, root included.
#
# The isolation that non-root provided under App Runner is provided here by the
# execution model instead. Adding a USER directive to a Lambda base image also
# risks breaking the Runtime Interface Client, which expects to own its
# directories -- a real failure traded for a theoretical gain.
#
# This is a genuine difference between the two deployment targets and belongs
# in the PR discussion, not buried in a Dockerfile. It is in README.md too.
# ---------------------------------------------------------------------------
