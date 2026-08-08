"""Child endpoints, scoped to the authenticated user.

QJ-1 shipped no endpoints here at all -- children existed only as rows the
seed script inserted, which was fine when quotes were the whole product and
the fixture supplied a child_id.

Authentication changes that. A user who registers now owns nothing, and
without a way to create a child there is no valid child_id to attach a quote
to, so the API is unusable the moment it is secured. These two endpoints are
the minimum that keeps a registered account functional.

Ownership is enforced the same way as in quotes.py: as a predicate inside the
query rather than a check after the fetch.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import CurrentUser
from app.models import Child
from app.schemas import ChildCreate, ChildRead

router = APIRouter(prefix="/children", tags=["children"])


@router.post("", response_model=ChildRead, status_code=status.HTTP_201_CREATED)
def create_child(
    payload: ChildCreate, user: CurrentUser, db: Session = Depends(get_db)
) -> Child:
    # user_id comes from the token, never from the request body.
    #
    # This is the whole ballgame for write-side access control. If the client
    # supplied user_id, anyone could create children under any account by
    # changing one field -- and it would look like a perfectly ordinary
    # successful request in the logs. Taking it from the authenticated
    # identity means the field simply is not attacker-reachable. ChildCreate
    # has no user_id, so even a client that sends one has it ignored.
    child = Child(user_id=user.id, name=payload.name)
    db.add(child)
    db.commit()
    db.refresh(child)
    return child


@router.get("", response_model=list[ChildRead])
def list_children(user: CurrentUser, db: Session = Depends(get_db)) -> list[Child]:
    return list(
        db.scalars(
            select(Child)
            .where(Child.user_id == user.id)
            .order_by(Child.created_at)
        ).all()
    )


@router.get("/{child_id}", response_model=ChildRead)
def get_child(
    child_id: uuid.UUID, user: CurrentUser, db: Session = Depends(get_db)
) -> Child:
    child = db.scalar(
        select(Child).where(Child.id == child_id, Child.user_id == user.id)
    )
    if child is None:
        # 404 rather than 403, for the same reason as quotes: a distinct
        # status for "exists but not yours" is an existence oracle. See the
        # long note on _not_found in app/routers/quotes.py.
        raise HTTPException(status_code=404, detail="Child not found")
    return child
