import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Child, Quote
from app.schemas import QuoteCreate, QuotePage, QuoteRead

router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.post("", response_model=QuoteRead, status_code=status.HTTP_201_CREATED)
def create_quote(payload: QuoteCreate, db: Session = Depends(get_db)) -> Quote:
    if db.get(Child, payload.child_id) is None:
        raise HTTPException(status_code=404, detail="Child not found")

    quote = Quote(**payload.model_dump(exclude_none=True))
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote


@router.get("", response_model=QuotePage)
def list_quotes(
    child_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> QuotePage:
    filters = [Quote.deleted_at.is_(None)]
    if child_id is not None:
        filters.append(Quote.child_id == child_id)

    total = db.scalar(select(func.count()).select_from(Quote).where(*filters)) or 0
    rows = db.scalars(
        select(Quote)
        .where(*filters)
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
def get_quote(quote_id: uuid.UUID, db: Session = Depends(get_db)) -> Quote:
    quote = db.scalar(
        select(Quote).where(Quote.id == quote_id, Quote.deleted_at.is_(None))
    )
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quote(quote_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    quote = db.scalar(
        select(Quote).where(Quote.id == quote_id, Quote.deleted_at.is_(None))
    )
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    quote.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
