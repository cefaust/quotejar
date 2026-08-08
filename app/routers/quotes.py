"""Quote endpoints, scoped to the authenticated user.

This module is the fix for IDOR -- Insecure Direct Object Reference, item A01
(Broken Access Control) on the OWASP Top 10, and consistently the most common
category of real-world web vulnerability.

The name describes the bug exactly. An endpoint takes a *direct reference* to
an object -- here a UUID in the path -- looks it up, and returns it. The
reference is direct because it maps straight onto a database row with nothing
in between. It is insecure because the handler asks "does this row exist?"
without ever asking "is this caller allowed to see it?"

QJ-1's version had precisely this shape:

    quote = db.scalar(select(Quote).where(Quote.id == quote_id))

Authentication does not fix it. Once QJ-2 added login, every user got a valid
token -- and a valid token was enough to read every quote in the database,
because nothing tied the query to the caller. Knowing *who* someone is is
useless until you also check *what they may touch*. That gap between
authentication and authorisation is where IDOR lives.

UUIDs are not the fix either. They make ids impractical to enumerate, which
is worth having, but it is secrecy standing in for a permission check. Ids
leak -- through logs, referrer headers, screenshots, shared URLs, a previous
owner of a recycled account. The only durable fix is the one below: make
ownership part of the query itself, so an unowned row cannot be returned
even in principle.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import CurrentUser
from app.models import Child, Quote
from app.schemas import QuoteCreate, QuotePage, QuoteRead

router = APIRouter(prefix="/quotes", tags=["quotes"])


def _visible_quotes(user_id: uuid.UUID) -> Select:
    """Every quote this user may see, and no others.

    Ownership is expressed once, here, and every handler starts from it. That
    is deliberate: the failure mode for access control is not writing a wrong
    check, it is forgetting to write one at all on the fifth endpoint someone
    adds six months from now. A shared starting point makes the secure path
    the path of least resistance -- you would have to go out of your way to
    build an unscoped query.

    Quotes have no user_id of their own. Ownership runs quote -> child ->
    user, so scoping means joining through children. That join is the access
    check; it is not incidental.

    Worth being explicit about why quotes are not denormalised with their own
    user_id column, which would make these queries simpler. It would introduce
    a second copy of a fact the schema already records, and two copies can
    disagree -- reassign a child to a different parent and every quote row
    still points at the old one, silently, with the stale value being exactly
    the one the security check reads. The join costs an indexed lookup against
    children.id. Correctness that cannot drift is worth more than that.
    """
    return (
        select(Quote)
        .join(Child, Quote.child_id == Child.id)
        .where(Child.user_id == user_id, Quote.deleted_at.is_(None))
    )


def _not_found() -> HTTPException:
    """404 for a quote that exists but belongs to someone else.

    This looks like a lie, and choosing it over 403 Forbidden is deliberate.

    403 is the honest answer -- the resource is there, you may not have it.
    But honesty here is a disclosure. 403 and 404 are different answers to
    "does a quote with this id exist?", and an attacker holding a list of
    candidate ids learns which ones are real by reading status codes alone,
    without ever seeing content. On a system where ids are sequential that
    enumerates the whole table; even with UUIDs it confirms any id that leaks
    through a log or a shared link.

    Existence is itself information. "There is a quote you cannot see" tells
    someone the account is in use, and paired with a leaked id it confirms a
    specific relationship. The rule generalises: an unauthorised caller should
    not be able to distinguish "forbidden" from "absent", so both answer 404.

    The cost is real and worth naming: a legitimate user who mistypes their
    own quote id gets "not found" when "not yours" would have been clearer,
    and a developer debugging a permissions bug sees 404 instead of a pointer
    at the actual problem. That is the trade -- worse ergonomics for the
    handful of people with legitimate access, no oracle for everyone else.

    Note this is a different question from the 401-not-403 in dependencies.py.
    There the caller had no valid identity at all. Here they are a known,
    authenticated user who simply does not own this row.
    """
    return HTTPException(status_code=404, detail="Quote not found")


@router.post("", response_model=QuoteRead, status_code=status.HTTP_201_CREATED)
def create_quote(
    payload: QuoteCreate, user: CurrentUser, db: Session = Depends(get_db)
) -> Quote:
    # The child_id arrives in the request body, which makes it attacker-
    # controlled. Checking only that the child exists -- QJ-1's behaviour --
    # would let anyone attach quotes to anyone else's child by guessing or
    # reusing an id. That is a *write*-side IDOR, and it is the more damaging
    # direction: reads leak data, writes corrupt someone else's.
    #
    # The user_id predicate makes another user's child indistinguishable from
    # a nonexistent one, so the 404 below covers both without disclosing which.
    child = db.scalar(
        select(Child).where(
            Child.id == payload.child_id, Child.user_id == user.id
        )
    )
    if child is None:
        raise HTTPException(status_code=404, detail="Child not found")

    quote = Quote(**payload.model_dump(exclude_none=True))
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote


@router.get("", response_model=QuotePage)
def list_quotes(
    user: CurrentUser,
    child_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> QuotePage:
    filters = [Child.user_id == user.id, Quote.deleted_at.is_(None)]

    # A child_id filter narrows within what the caller already owns; it can
    # never widen it. Passing another user's child_id returns an empty page
    # rather than their quotes, because the ownership predicate above is
    # ANDed in regardless of what the query string asks for.
    if child_id is not None:
        filters.append(Quote.child_id == child_id)

    total = (
        db.scalar(
            select(func.count())
            .select_from(Quote)
            .join(Child, Quote.child_id == Child.id)
            .where(*filters)
        )
        or 0
    )

    # `total` is counted with the same ownership filter as the rows. If it
    # were not, a caller would learn the true size of everyone's collection
    # while being served only their own page -- a count is a small leak, but
    # it is still a leak, and it is the kind that survives review because the
    # visible items look correctly filtered.
    rows = db.scalars(
        _visible_quotes(user.id)
        .where(*([Quote.child_id == child_id] if child_id is not None else []))
        .order_by(Quote.said_on.desc(), Quote.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return QuotePage(
        items=[QuoteRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{quote_id}", response_model=QuoteRead)
def get_quote(
    quote_id: uuid.UUID, user: CurrentUser, db: Session = Depends(get_db)
) -> Quote:
    # Ownership is a WHERE clause, not an if-statement after the fetch.
    #
    # Fetching first and checking after works, but it leaves a window: the row
    # is in memory, and any later edit that returns early, logs the object, or
    # adds a branch can expose it. Putting the predicate in the query means an
    # unowned row is never loaded at all. There is nothing to leak.
    quote = db.scalar(_visible_quotes(user.id).where(Quote.id == quote_id))
    if quote is None:
        raise _not_found()
    return quote


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quote(
    quote_id: uuid.UUID, user: CurrentUser, db: Session = Depends(get_db)
) -> Response:
    quote = db.scalar(_visible_quotes(user.id).where(Quote.id == quote_id))
    if quote is None:
        raise _not_found()

    quote.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
