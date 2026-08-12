"""Cross-user access control -- the IDOR tests.

The most important file in the suite, because it is the only one asserting a
property that has no visible symptom when it breaks. Every test here passes
just as happily against a completely unscoped API: the requests succeed, the
data comes back, nothing errors. The bug is that they succeed *for the wrong
person*, which no amount of exercising your own account will ever surface.

Convention throughout: `client` is the owner, `other_client` is the attacker.
Every test asks the same question -- can the attacker reach something that is
not theirs -- and the answer must always be 404.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models import Quote

QUOTES = "/quotes"
CHILDREN = "/children"


@pytest.fixture
def owned_quote(client, child):
    """A quote created by the owner, for the attacker to fail against."""
    return client.post(
        QUOTES, json={"child_id": str(child.id), "text": "I am not tired"}
    ).json()


# --- reads ----------------------------------------------------------------


def test_another_user_cannot_read_your_quote(other_client, owned_quote):
    r = other_client.get(f"{QUOTES}/{owned_quote['id']}")
    assert r.status_code == 404


def test_the_refusal_is_404_and_not_403(other_client, owned_quote):
    """403 would confirm the id names a real quote.

    An attacker holding candidate ids could then separate real from imaginary
    on status codes alone, never seeing any content. Existence is itself
    information, so "forbidden" and "absent" must be indistinguishable.
    """
    forbidden = other_client.get(f"{QUOTES}/{owned_quote['id']}")
    nonexistent = other_client.get(f"{QUOTES}/{uuid.uuid4()}")

    assert forbidden.status_code == nonexistent.status_code == 404
    assert forbidden.json() == nonexistent.json()


def test_listing_excludes_other_users_quotes(other_client, owned_quote):
    r = other_client.get(QUOTES)

    assert r.status_code == 200
    assert r.json()["items"] == []


def test_the_total_count_also_excludes_them(other_client, owned_quote):
    """A count is a small leak that survives review, because the visible page
    looks correctly filtered while the number quietly describes everyone."""
    assert other_client.get(QUOTES).json()["total"] == 0


def test_filtering_by_someone_elses_child_id_returns_nothing(
    other_client, child, owned_quote
):
    """The child_id filter narrows within what you own; it cannot widen it.

    This is the query-parameter version of the same attack, and it is easy to
    get wrong -- a handler that treats child_id as the whole filter rather
    than as an extra condition hands over the other account's quotes.
    """
    r = other_client.get(QUOTES, params={"child_id": str(child.id)})

    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0


def test_another_user_cannot_read_your_child(other_client, child):
    assert other_client.get(f"{CHILDREN}/{child.id}").status_code == 404


def test_listing_children_excludes_other_users(other_client, child):
    assert other_client.get(CHILDREN).json() == []


# --- writes ---------------------------------------------------------------


def test_another_user_cannot_delete_your_quote(other_client, owned_quote):
    assert other_client.delete(f"{QUOTES}/{owned_quote['id']}").status_code == 404


def test_a_rejected_delete_does_not_soft_delete_the_row(
    other_client, client, owned_quote, db
):
    """404 must mean nothing happened, not "refused after acting".

    Checked at the database rather than through the API: a handler that sets
    deleted_at and *then* raises would return an identical 404 while having
    destroyed the row, and no HTTP-level assertion would catch it.
    """
    other_client.delete(f"{QUOTES}/{owned_quote['id']}")

    row = db.scalar(select(Quote).where(Quote.id == uuid.UUID(owned_quote["id"])))
    assert row.deleted_at is None
    assert client.get(f"{QUOTES}/{owned_quote['id']}").status_code == 200


def test_another_user_cannot_attach_a_quote_to_your_child(other_client, child):
    """Write-side IDOR, and the more damaging direction -- a read leaks data,
    a write puts an attacker's content inside someone else's account.

    child_id arrives in the request body, so it is entirely attacker-
    controlled. Checking only that the child exists is not enough.
    """
    r = other_client.post(QUOTES, json={"child_id": str(child.id), "text": "not yours"})
    assert r.status_code == 404


def test_a_rejected_write_creates_nothing(other_client, child, db):
    other_client.post(QUOTES, json={"child_id": str(child.id), "text": "not yours"})

    assert db.scalar(select(Quote).where(Quote.text == "not yours")) is None


def test_creating_a_child_ignores_a_client_supplied_user_id(
    other_client, other_user, user
):
    """Mass assignment: the classic one-field privilege escalation.

    ChildCreate has no user_id, so a client that sends one has it dropped and
    the value is taken from the token instead. If it were accepted, anyone
    could plant records in any account by editing a single field -- and the
    request would look entirely ordinary in the logs.
    """
    r = other_client.post(CHILDREN, json={"name": "Injected", "user_id": str(user.id)})

    assert r.status_code == 201
    child_id = r.json()["id"]

    # It landed in the attacker's own account, not the victim's.
    assert other_client.get(f"{CHILDREN}/{child_id}").status_code == 200


# --- the owner is unaffected ----------------------------------------------


def test_the_owner_still_sees_their_own_quote(client, owned_quote):
    r = client.get(f"{QUOTES}/{owned_quote['id']}")

    assert r.status_code == 200
    assert r.json()["id"] == owned_quote["id"]


def test_the_owner_still_lists_their_own_quotes(client, owned_quote):
    body = client.get(QUOTES).json()

    assert body["total"] == 1
    assert body["items"][0]["id"] == owned_quote["id"]


# --- anonymity ------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", QUOTES),
        ("post", QUOTES),
        ("get", f"{QUOTES}/{uuid.uuid4()}"),
        ("delete", f"{QUOTES}/{uuid.uuid4()}"),
        ("get", CHILDREN),
        ("post", CHILDREN),
        ("get", f"{CHILDREN}/{uuid.uuid4()}"),
        ("get", "/auth/me"),
    ],
)
def test_every_protected_route_rejects_anonymous_callers(anon_client, method, path):
    r = getattr(anon_client, method)(path, **({"json": {}} if method == "post" else {}))
    assert r.status_code == 401


def test_health_stays_public(anon_client):
    """The one route that must not require a token: a load balancer polling it
    has no credentials, and a 401 would read as an unhealthy instance."""
    assert anon_client.get("/health").status_code == 200
