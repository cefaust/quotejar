"""Rate limiting, backed by DynamoDB.

Why this exists, concretely. bcrypt costs ~216 ms of CPU per verification --
deliberately, because that slowness is what protects hashes against offline
cracking. Against a live endpoint the same property inverts: each login attempt
costs an attacker one cheap HTTP request and costs us 216 ms of a reserved
execution slot. With reserved concurrency of 5, five concurrent attackers
saturate the function and every real user gets throttled. No password needs to
be guessed for the service to go down.

## Why a shared store rather than an in-process counter

Lambda gives up to five execution environments, each with its own memory,
created and destroyed unpredictably. A per-process counter would give an
attacker 5x the intended limit and reset whenever a container recycled. The
counter has to live somewhere all invocations can see.

## The algorithm: sliding window counter

Three candidates, and the trade is accuracy against storage.

**Fixed window** -- one counter per calendar window -- is the simplest and has
a specific flaw: an attacker gets *twice* the limit across a boundary. With a
limit of 10 per minute they send 10 at 11:59:59 and 10 more at 12:00:00. Both
windows are individually legal; 20 requests land in two seconds. For a limiter
whose job is bounding a 216 ms operation, a 2x burst is the difference between
bounded and unbounded.

**Sliding window log** stores every request timestamp and is exact, but a
limit of N costs N stored timestamps per key. Under the attack this exists to
stop, that is unbounded write amplification -- the defence becomes the cost.

**Token bucket** models a refilling allowance and handles bursts gracefully,
but needs two mutable fields (tokens and last-refill time) updated atomically,
which is a read-modify-write against DynamoDB rather than a single atomic ADD.

**Sliding window counter** is the middle: keep a counter for the current
window and the previous one, then weight the previous by how much of it still
overlaps the trailing window.

    estimate = previous_count * (1 - elapsed_fraction) + current_count

Two small items per key, one atomic increment, and no boundary burst -- at
11:59:59 the previous window still counts almost fully, so the attacker above
is rejected. It assumes traffic was evenly spread inside the previous window,
which is an approximation, but it errs on the side of counting requests that
have partially aged out rather than forgetting them.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Decision:
    """The outcome of one limit check."""

    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int

    def headers(self) -> dict[str, str]:
        """Headers describing the caller's remaining quota.

        Names follow the IETF draft for RateLimit header fields
        (draft-ietf-httpapi-ratelimit-headers), which is the de facto
        convention: a quota, what is left of it, and when it refills.

        `reset` is *seconds remaining*, not a timestamp. A client cannot
        misread a duration; an epoch timestamp requires it to agree with us
        about the current time, and clients with skewed clocks then retry
        early and get another 429.

        Retry-After is sent as well, on 429 only. It is the older, far more
        widely implemented header (RFC 9110), and honouring both means clients
        that understand either can back off correctly. Returning a bare 429
        with no timing at all is the thing worth avoiding -- it tells a client
        to stop without telling it for how long, so well-behaved clients guess
        and badly-behaved ones hammer.
        """
        return {
            "RateLimit-Limit": str(self.limit),
            "RateLimit-Remaining": str(max(0, self.remaining)),
            "RateLimit-Reset": str(self.reset_seconds),
        }


class Store(Protocol):
    """Somewhere counters live.

    A protocol rather than a concrete class so tests can substitute an
    in-memory implementation and a deliberately broken one. The fail-open path
    is the hardest behaviour to test against a real store -- you would have to
    break DynamoDB on purpose -- and it is the one that must not regress,
    because getting it wrong turns a store outage into a total outage.
    """

    def increment(self, key: str, window_seconds: int) -> int:
        """Add one to `key` and return the new count."""
        ...

    def get(self, key: str) -> int:
        """Read `key` without changing it. Zero if absent."""
        ...


class DynamoDBStore:
    """Counters in DynamoDB, one item per (limit key, window).

    Reached over a **Gateway** VPC endpoint, which costs nothing -- unlike the
    Interface endpoint Secrets Manager requires at roughly $7/month. That is
    part of why DynamoDB was chosen over ElastiCache: the Lambda has no route
    to the internet, so any store has to be reachable privately, and this one
    is reachable privately for free.
    """

    def __init__(self, table_name: str, client=None) -> None:
        self._table_name = table_name
        self._client = client

    @property
    def client(self):
        # Imported lazily and built once. The Lambda runtime bundles boto3, so
        # pinning it in requirements.txt would duplicate ~70 MB into the image
        # for nothing. Constructing the client is not free -- it loads service
        # models from disk -- so it is cached on the instance and reused across
        # warm invocations, the same reasoning as the SQLAlchemy engine.
        if self._client is None:
            import boto3

            self._client = boto3.client("dynamodb")
        return self._client

    def increment(self, key: str, window_seconds: int) -> int:
        # ADD is atomic server-side: DynamoDB applies it without us reading
        # first, so two concurrent Lambdas incrementing the same counter both
        # land. A read-then-write would lose updates under exactly the
        # concurrent load this exists to limit.
        #
        # expires_at lets DynamoDB reclaim old counters for free. TTL deletion
        # is best-effort and can lag by up to 48 hours, which is why window
        # expiry is computed from timestamps in the key rather than relying on
        # the row being gone. TTL is housekeeping, not correctness.
        response = self.client.update_item(
            TableName=self._table_name,
            Key={"pk": {"S": key}},
            UpdateExpression="ADD #c :one SET expires_at = :exp",
            ExpressionAttributeNames={"#c": "count"},
            ExpressionAttributeValues={
                ":one": {"N": "1"},
                ":exp": {"N": str(int(time.time()) + window_seconds * 2 + 60)},
            },
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["count"]["N"])

    def get(self, key: str) -> int:
        response = self.client.get_item(
            TableName=self._table_name,
            Key={"pk": {"S": key}},
            # Strongly consistent. The default eventually-consistent read is
            # cheaper and can return a stale count, and a stale count in a
            # limiter reads as extra allowance -- precisely what an attacker
            # would exploit by firing requests faster than replication.
            ConsistentRead=True,
            ProjectionExpression="#c",
            ExpressionAttributeNames={"#c": "count"},
        )
        item = response.get("Item")
        return int(item["count"]["N"]) if item else 0


class RateLimiter:
    def __init__(self, store: Store) -> None:
        # Public and reassignable on purpose. Tests replace it with an
        # in-memory implementation, and with a deliberately broken one to
        # exercise the fail-open path -- which is otherwise untestable without
        # breaking DynamoDB, and is the behaviour that most needs a test,
        # because if it regresses a store outage becomes a total outage.
        self.store = store

    # Three operations rather than one, because the two kinds of limit here
    # count different things.
    #
    # An IP limit counts *requests*: every attempt is a unit of load, so every
    # attempt is counted and checked together -- that is `check`.
    #
    # An email limit counts *failures*: it exists to slow brute force against
    # one account, and a user who types their password correctly has not
    # attacked anything. Counting their successful logins would penalise the
    # legitimate owner for using their own account, and worse, it would let an
    # attacker lock someone out by simply logging in wrongly at them. So the
    # check (`peek`) happens before the attempt and the increment (`record`)
    # only after one fails.

    def check(
        self, scope: str, identifier: str, limit: int, window_seconds: int
    ) -> Decision:
        """Count this request, then decide. Used where every request is load."""
        try:
            self._increment(scope, identifier, window_seconds)
        except Exception:
            return self._fail_open(scope, limit, window_seconds)
        return self.peek(scope, identifier, limit, window_seconds)

    def peek(
        self, scope: str, identifier: str, limit: int, window_seconds: int
    ) -> Decision:
        """Decide without counting. Used before an attempt that may not count."""
        now = time.time()
        current_start = int(now // window_seconds) * window_seconds
        previous_start = current_start - window_seconds
        elapsed_fraction = (now - current_start) / window_seconds

        try:
            current = self.store.get(f"{scope}:{identifier}:{current_start}")
            previous = self.store.get(f"{scope}:{identifier}:{previous_start}")
        except Exception:
            return self._fail_open(scope, limit, window_seconds)

        estimate = previous * (1 - elapsed_fraction) + current
        return Decision(
            allowed=estimate <= limit,
            limit=limit,
            remaining=int(max(0, limit - estimate)),
            reset_seconds=max(1, int(current_start + window_seconds - now)),
        )

    def record(self, scope: str, identifier: str, window_seconds: int) -> None:
        """Count an event without deciding. Used to record a failed attempt."""
        try:
            self._increment(scope, identifier, window_seconds)
        except Exception:
            # Swallowed on purpose. This is called *after* a request has been
            # handled, so raising here would turn a successful 401 into a 500
            # -- failing the user's request because bookkeeping failed.
            logger.error(
                "could not record rate limit event: scope=%s", scope, exc_info=True
            )

    def _increment(self, scope: str, identifier: str, window_seconds: int) -> int:
        now = time.time()
        current_start = int(now // window_seconds) * window_seconds
        return self.store.increment(
            f"{scope}:{identifier}:{current_start}", window_seconds
        )

    def _fail_open(self, scope: str, limit: int, window_seconds: int) -> Decision:
        """Allow the request when the store is unreachable.

        Deliberately broad exception handling upstream. Any failure to reach
        the store -- throttling, a partition, expired credentials, a missing
        table -- has the same correct response, and enumerating boto3's
        exception hierarchy would mean a new failure mode raising a 500 instead
        of failing open.

        The full reasoning is in README.md. In short: a rate limiter is a
        control on abuse, not a dependency of the product, and letting it take
        the service down converts a partial outage into a total one. The cost
        is real -- during a store outage there is no limiting at all -- which
        is why this logs at ERROR with a traceback. A fail-open limiter that
        logs quietly is indistinguishable from one that works, and you find out
        during the incident that it has been open for a month.
        """
        logger.error(
            "rate limit store unavailable, failing open: scope=%s", scope, exc_info=True
        )
        return Decision(
            allowed=True, limit=limit, remaining=limit, reset_seconds=window_seconds
        )
