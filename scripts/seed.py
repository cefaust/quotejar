"""Insert one user and two children so the quote endpoints have something to reference.

Not part of QJ-1's acceptance criteria -- added because the ticket defines no
endpoints for creating users or children, but quotes require a valid child_id.
"""

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Child, User

SEED_EMAIL = "parent@example.com"


def main() -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == SEED_EMAIL))
        if user is None:
            user = User(email=SEED_EMAIL, display_name="Example Parent")
            db.add(user)
            db.flush()
            db.add_all([Child(user_id=user.id, name="Ada"),
                        Child(user_id=user.id, name="Bo")])
            db.commit()

        for child in db.scalars(select(Child).where(Child.user_id == user.id)):
            print(f"{child.name}: {child.id}")


if __name__ == "__main__":
    main()
