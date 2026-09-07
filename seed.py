from sqlalchemy.orm import Session

from app.auth import get_password_hash
from database import SessionLocal, User, init_db


def seed_users() -> None:
    init_db()
    db: Session = SessionLocal()
    try:
        existing = db.query(User).count()
        if existing:
            print("Los usuarios ya existen.")
            return

        users = [
            User(username="manufacturer", password_hash=get_password_hash("manufacturer123"), role="manufacturer"),
            User(username="distributor", password_hash=get_password_hash("distributor123"), role="distributor"),
            User(username="consumer", password_hash=get_password_hash("consumer123"), role="consumer"),
        ]
        db.add_all(users)
        db.commit()
        print("Usuarios de prueba creados.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_users()
