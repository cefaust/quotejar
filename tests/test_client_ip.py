"""Client IP extraction.

Every IP-keyed limit rests on this being right, and getting it wrong fails
quietly in one of two directions:

  - Key on something constant and every user in the world shares one bucket,
    so the first busy minute locks out everybody.
  - Key on something the caller controls and an attacker defeats the limit by
    incrementing a header, which is worse than having no limit at all --
    it looks like protection while providing none.

Neither shows up in ordinary use. Both need a test that specifically lies.
"""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from mangum import Mangum

from app.dependencies import client_ip

probe = FastAPI()


@probe.get("/whoami")
def whoami(request: Request) -> dict[str, str]:
    return {"ip": client_ip(request)}


handler = Mangum(probe, lifespan="off")


def _event(source_ip: str, headers: dict[str, str] | None = None) -> dict:
    """A Lambda Function URL invocation, in the payload format v2.0 shape."""
    return {
        "version": "2.0",
        "rawPath": "/whoami",
        "rawQueryString": "",
        "headers": headers or {"host": "example"},
        "requestContext": {
            "http": {
                "method": "GET",
                "path": "/whoami",
                "protocol": "HTTP/1.1",
                "sourceIp": source_ip,
            }
        },
        "isBase64Encoded": False,
    }


def _ip_seen_by_app(event: dict) -> str:
    import json

    return json.loads(handler(event, None)["body"])["ip"]


def test_the_caller_address_comes_from_the_request_context():
    assert _ip_seen_by_app(_event("203.0.113.10")) == "203.0.113.10"


def test_a_forged_x_forwarded_for_is_ignored():
    """The attack this requirement exists to prevent.

    Nothing sits in front of this Function URL, so X-Forwarded-For arrives
    exactly as the client typed it. Keying on it would let one attacker present
    as unlimited distinct clients by incrementing a number.
    """
    seen = _ip_seen_by_app(
        _event("203.0.113.10", {"host": "example", "x-forwarded-for": "1.2.3.4"})
    )

    assert seen == "203.0.113.10"
    assert seen != "1.2.3.4"


def test_a_forged_forwarding_chain_is_ignored():
    """Sending a chain is the usual way to defeat naive parsers, which take
    the leftmost entry as 'the real client'."""
    seen = _ip_seen_by_app(
        _event(
            "203.0.113.10",
            {"host": "example", "x-forwarded-for": "9.9.9.9, 8.8.8.8, 7.7.7.7"},
        )
    )

    assert seen == "203.0.113.10"
    for forged in ("9.9.9.9", "8.8.8.8", "7.7.7.7"):
        assert seen != forged


def test_other_forwarding_headers_are_ignored_too():
    """X-Forwarded-For is the famous one, not the only one."""
    seen = _ip_seen_by_app(
        _event(
            "203.0.113.10",
            {
                "host": "example",
                "x-real-ip": "5.5.5.5",
                "forwarded": "for=6.6.6.6",
                "cloudfront-viewer-address": "4.4.4.4:443",
                "true-client-ip": "3.3.3.3",
            },
        )
    )

    assert seen == "203.0.113.10"


def test_different_callers_are_distinguished():
    """The other failure direction: if this collapsed to a constant, every
    user would share one bucket and one busy client would throttle everyone."""
    assert _ip_seen_by_app(_event("198.51.100.1")) != _ip_seen_by_app(
        _event("198.51.100.2")
    )


def test_a_missing_client_does_not_raise():
    """Starlette's TestClient can produce a scope with no client, and an
    AttributeError inside a limiter would be a 500 on every request."""
    with TestClient(probe) as c:
        assert c.get("/whoami").status_code == 200
