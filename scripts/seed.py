"""Insert one user and two children so the quote endpoints have something to reference.

Not part of QJ-1's acceptance criteria -- added because the ticket defines no
endpoints for creating users or children, but quotes require a valid child_id.
"""

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Child, User
from app.security import hash_password

SEED_EMAIL = "parent@example.com"

# A known password is the whole point for a development fixture: it makes the
# seeded account loggable-in so you can exercise the authenticated endpoints
# by hand. That is also exactly why this script must never run anywhere real.
SEED_PASSWORD = "seed-password-dev-only"


def main() -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == SEED_EMAIL))
        if user is None:
            user = User(
                email=SEED_EMAIL,
                display_name="Example Parent",
                password_hash=hash_password(SEED_PASSWORD),
            )
            db.add(user)
            db.flush()
            db.add_all([Child(user_id=user.id, name="Ada"),
                        Child(user_id=user.id, name="Bo")])
            db.commit()

        for child in db.scalars(select(Child).where(Child.user_id == user.id)):
            print(f"{child.name}: {child.id}")


if __name__ == "__main__":
    main()
